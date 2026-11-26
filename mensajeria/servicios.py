from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Count, F, Q

from crear_cuenta.models import Usuario
from mensajeria.models import Mensaje
from mensajeria.permisos import pacientes_conversables


def texto_mensaje_para_usuario(texto, tipo, user):
    if user.role != Usuario.ROLE_DOCTOR or tipo != Mensaje.TIPO_SISTEMA:
        return texto
    if texto.startswith('Tu médico ha cambiado. Ahora te atiende '):
        return texto.replace(
            'Tu médico ha cambiado. Ahora te atiende ',
            'Cambio de médico: el paciente ahora es atendido por ',
            1,
        )
    if texto.startswith('Ahora te atiende '):
        return texto.replace(
            'Ahora te atiende ',
            'Asignación inicial: el paciente ahora es atendido por ',
            1,
        )
    return texto


def mensajes_no_leidos(user, paciente=None):
    queryset = Mensaje.objects.filter(
        paciente__in=pacientes_conversables(user),
        leido_en__isnull=True,
    ).filter(Q(autor_id__isnull=True) | ~Q(autor_id=user.pk))
    if user.role == Usuario.ROLE_DOCTOR:
        queryset = queryset.filter(
            Q(paciente__asignaciones__chat_visible_desde__isnull=True)
            | Q(creado_en__gte=F('paciente__asignaciones__chat_visible_desde')),
            paciente__asignaciones__doctor_id=user.pk,
            paciente__asignaciones__fin__isnull=True,
        )
    if paciente is not None:
        queryset = queryset.filter(paciente=paciente)
    return queryset


def resumen_no_leidos(user):
    por_conversacion = {
        row['paciente_id']: row['total']
        for row in mensajes_no_leidos(user).values('paciente_id').annotate(total=Count('pk'))
    }
    return {
        'tipo': 'no_leidos',
        'total': sum(por_conversacion.values()),
        'por_conversacion': por_conversacion,
    }


def publicar_a_participantes(paciente, payload):
    channel_layer = get_channel_layer()
    for user_id in {paciente.usuario_id, paciente.doctor_id}:
        if user_id:
            async_to_sync(channel_layer.group_send)(
                f'usuario_{user_id}',
                {'type': 'mensajeria.evento', 'payload': payload},
            )


def publicar_contadores_a_participantes(paciente):
    channel_layer = get_channel_layer()
    for user_id in {paciente.usuario_id, paciente.doctor_id}:
        if user_id:
            user = Usuario.objects.filter(pk=user_id, is_active=True).first()
            if user:
                async_to_sync(channel_layer.group_send)(
                    f'usuario_{user_id}',
                    {
                        'type': 'mensajeria.evento',
                        'payload': resumen_no_leidos(user),
                    },
                )


def publicar_contador_a_usuario(user_id):
    user = Usuario.objects.filter(pk=user_id, is_active=True).first()
    if not user:
        return
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'usuario_{user.pk}',
        {
            'type': 'mensajeria.evento',
            'payload': resumen_no_leidos(user),
        },
    )


def registrar_mensaje_sistema_llamada(paciente, texto):
    mensaje = Mensaje.objects.create(
        paciente=paciente,
        autor=None,
        tipo=Mensaje.TIPO_SISTEMA,
        texto=texto,
    )
    payload = {
        'tipo': 'mensaje',
        'paciente_id': paciente.pk,
        'id': mensaje.pk,
        'autor_id': None,
        'tipo_mensaje': Mensaje.TIPO_SISTEMA,
        'texto': mensaje.texto,
        'creado_en': mensaje.creado_en.isoformat(),
        'leido_en': None,
    }
    def notificar():
        publicar_a_participantes(paciente, payload)
        publicar_contadores_a_participantes(paciente)

    transaction.on_commit(notificar)
    return mensaje
