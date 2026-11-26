from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from crear_cuenta.models import Usuario
from mensajeria.models import Mensaje
from mensajeria.servicios import (
    publicar_a_participantes,
    publicar_contadores_a_participantes,
    texto_mensaje_para_usuario,
)
from princpal.models import AsignacionMedico, Paciente


def _notificar_cambio(paciente_id, mensaje, doctor_id):
    paciente = Paciente.objects.select_related('usuario', 'doctor').get(pk=paciente_id)
    mensaje_payload = {
        'id': mensaje.pk,
        'paciente_id': paciente_id,
        'autor_id': None,
        'tipo_mensaje': Mensaje.TIPO_SISTEMA,
        'texto': mensaje.texto,
        'creado_en': mensaje.creado_en.isoformat(),
        'leido_en': None,
    }
    mensaje_medico_payload = {
        **mensaje_payload,
        'texto': texto_mensaje_para_usuario(
            mensaje.texto,
            Mensaje.TIPO_SISTEMA,
            paciente.doctor,
        ),
    }
    publicar_a_participantes(
        paciente,
        {
            'tipo': 'cambio_medico',
            'paciente_id': paciente_id,
            'doctor_id': doctor_id,
            'doctor_nombre': paciente.doctor.nombre,
            'mensaje': mensaje_payload,
            'mensaje_medico': mensaje_medico_payload,
        },
    )
    publicar_contadores_a_participantes(paciente)


def _guardar_medico_en_paciente(paciente, doctor):
    paciente.doctor = doctor
    paciente._cambio_medico_por_servicio = True
    try:
        paciente.save(update_fields=['doctor'])
    finally:
        del paciente._cambio_medico_por_servicio


def _crear_mensaje_sistema_y_notificar(paciente, doctor, ahora, texto):
    mensaje = Mensaje.objects.create(
        paciente=paciente,
        autor=None,
        tipo=Mensaje.TIPO_SISTEMA,
        texto=texto,
    )
    Mensaje.objects.filter(pk=mensaje.pk).update(creado_en=ahora)
    mensaje.creado_en = ahora
    transaction.on_commit(
        lambda patient_id=paciente.pk, saved_message=mensaje, new_doctor_id=doctor.pk:
            _notificar_cambio(patient_id, saved_message, new_doctor_id)
    )


def asignar_paciente_inicial(paciente, nuevo_doctor):
    with transaction.atomic():
        paciente = Paciente.objects.select_for_update().get(pk=paciente.pk)
        if paciente.doctor_id:
            raise ValidationError('El paciente ya tiene un médico asignado.')
        if AsignacionMedico.objects.filter(paciente=paciente).exists():
            raise ValidationError(
                'Este paciente ya tuvo asignaciones. Solo un administrador puede reasignarlo.'
            )

        doctor = Usuario.objects.select_for_update().filter(
            pk=getattr(nuevo_doctor, 'pk', None),
            role=Usuario.ROLE_DOCTOR,
            is_active=True,
        ).first()
        if not doctor:
            raise ValidationError('El médico debe tener el rol doctor y estar activo.')

        ahora = timezone.now()
        asignacion = AsignacionMedico.objects.create(
            paciente=paciente,
            doctor=doctor,
            tipo=AsignacionMedico.TIPO_INICIAL,
            inicio=ahora,
            motivo='Asignación inicial realizada por el médico.',
            creada_por_medico=doctor,
        )
        _guardar_medico_en_paciente(paciente, doctor)
        _crear_mensaje_sistema_y_notificar(
            paciente,
            doctor,
            ahora,
            f'Ahora te atiende Dr. {doctor.nombre}.',
        )
        return asignacion


def reasignar_medico(
    paciente,
    nuevo_doctor,
    tipo,
    motivo,
    compartir_historial_clinico,
    paciente_autorizo,
    admin,
):
    if (
        not getattr(admin, 'is_authenticated', False)
        or not getattr(admin, 'is_active', False)
        or not getattr(admin, 'is_staff', False)
    ):
        raise ValidationError('Solo un administrador puede asignar o reasignar médicos.')

    motivo = (motivo or '').strip()
    if len(motivo) < 10:
        raise ValidationError('El motivo debe tener al menos 10 caracteres.')
    if tipo not in {
        AsignacionMedico.TIPO_INICIAL,
        AsignacionMedico.TIPO_CONTINUIDAD,
        AsignacionMedico.TIPO_NUEVO_CASO,
    }:
        raise ValidationError('Selecciona un tipo de asignación válido.')
    if tipo == AsignacionMedico.TIPO_NUEVO_CASO and compartir_historial_clinico and not paciente_autorizo:
        raise ValidationError(
            'Confirma que el paciente autorizó compartir su historial clínico previo.'
        )

    ahora = timezone.now()
    with transaction.atomic():
        paciente = Paciente.objects.select_for_update().get(pk=paciente.pk)
        if not paciente.usuario_id:
            raise ValidationError('El paciente debe tener una cuenta vinculada.')

        doctor = Usuario.objects.select_for_update().filter(
            pk=getattr(nuevo_doctor, 'pk', None),
            role=Usuario.ROLE_DOCTOR,
            is_active=True,
        ).first()
        if not doctor:
            raise ValidationError('Selecciona un médico activo.')
        if paciente.doctor_id == doctor.pk:
            raise ValidationError('El nuevo médico debe ser distinto al médico actual.')

        vigente = AsignacionMedico.objects.select_for_update().filter(
            paciente=paciente,
            fin__isnull=True,
        ).first()
        asignacion_previa = (
            vigente
            or AsignacionMedico.objects.select_for_update()
            .filter(paciente=paciente)
            .order_by('-inicio', '-pk')
            .first()
        )
        if paciente.doctor_id and (
            not vigente or vigente.doctor_id != paciente.doctor_id
        ):
            raise ValidationError(
                'La asignación vigente no coincide con el médico del paciente. '
                'Solicita la revisión de un administrador.'
            )
        if not paciente.doctor_id and vigente:
            raise ValidationError(
                'El paciente no tiene médico pero conserva una asignación vigente; '
                'solicita la revisión de un administrador.'
            )
        if tipo == AsignacionMedico.TIPO_INICIAL and (
            paciente.doctor_id or asignacion_previa
        ):
            raise ValidationError('La asignación inicial solo se usa si el paciente no tiene médico.')
        if tipo != AsignacionMedico.TIPO_INICIAL and not asignacion_previa:
            raise ValidationError('Un paciente sin médico debe recibir una asignación inicial.')
        if tipo == AsignacionMedico.TIPO_INICIAL and compartir_historial_clinico:
            raise ValidationError('La asignación inicial no requiere compartir un historial previo.')

        chat_visible_desde = None
        historial_visible_desde = None
        autorizo = False
        if vigente:
            vigente.fin = ahora
            vigente.save(update_fields=['fin'])
        if tipo == AsignacionMedico.TIPO_CONTINUIDAD:
            chat_visible_desde = asignacion_previa.chat_visible_desde
            historial_visible_desde = asignacion_previa.historial_clinico_visible_desde
        elif tipo == AsignacionMedico.TIPO_NUEVO_CASO:
            chat_visible_desde = ahora
            historial_visible_desde = (
                asignacion_previa.historial_clinico_visible_desde
                if compartir_historial_clinico and asignacion_previa
                else ahora
            )
            autorizo = bool(compartir_historial_clinico and paciente_autorizo)

        asignacion = AsignacionMedico.objects.create(
            paciente=paciente,
            doctor=doctor,
            tipo=tipo,
            inicio=ahora,
            chat_visible_desde=chat_visible_desde,
            historial_clinico_visible_desde=historial_visible_desde,
            paciente_autorizo_historial=autorizo,
            motivo=motivo,
            creada_por=admin,
        )
        _guardar_medico_en_paciente(paciente, doctor)

        texto = f'Tu médico ha cambiado. Ahora te atiende Dr. {doctor.nombre}.'
        if tipo == AsignacionMedico.TIPO_INICIAL:
            texto = f'Ahora te atiende Dr. {doctor.nombre}.'
        _crear_mensaje_sistema_y_notificar(paciente, doctor, ahora, texto)
        return asignacion
