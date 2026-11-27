import logging
from datetime import date, datetime, time, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone

from princpal.models import (
    EvaluacionClinica,
    ObjetivoTerapeutico,
    OcurrenciaRutina,
    RutinaAsignada,
    Sesion,
)
from .models import (
    AlertaDolor,
    EnvioResumenSemanal,
    RegistroRecordatorio,
)


logger = logging.getLogger(__name__)
RECORDATORIO_VENTANA = timedelta(minutes=10)
RECORDATORIO_PROCESAMIENTO_LEASE = timedelta(seconds=60)


def enviar_correo(destinatario, asunto, plantilla, contexto):
    try:
        template_base = f'notificaciones/email/{plantilla}'
        contenido_texto = render_to_string(f'{template_base}.txt', contexto)
        contenido_html = render_to_string(f'{template_base}.html', contexto)

        mensaje = EmailMultiAlternatives(
            subject=asunto,
            body=contenido_texto,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinatario],
        )
        mensaje.attach_alternative(contenido_html, 'text/html')
        enviados = mensaje.send(fail_silently=False)
        if not enviados:
            return False, 'El backend de correo no envió el mensaje.'
        return True, ''
    except Exception as error:
        logger.exception('Error al enviar correo con la plantilla %s.', plantilla)
        return False, str(error) or 'No se pudo enviar el correo.'


def evaluar_alerta_dolor(ocurrencia):
    if not ocurrencia.pk or ocurrencia.completada_en is None or ocurrencia.nivel_dolor is None:
        return None

    ocurrencias_anteriores = OcurrenciaRutina.objects.filter(
        asignacion__paciente_id=ocurrencia.asignacion.paciente_id,
        completada_en__isnull=False,
    ).filter(
        Q(completada_en__lt=ocurrencia.completada_en)
        | Q(completada_en=ocurrencia.completada_en, pk__lt=ocurrencia.pk)
    ).order_by('-completada_en', '-pk')

    if ocurrencia.nivel_dolor >= settings.ALERTA_DOLOR_UMBRAL:
        return AlertaDolor.REGLA_UMBRAL

    dolor_anterior = ocurrencias_anteriores.filter(
        nivel_dolor__isnull=False,
    ).values_list('nivel_dolor', flat=True).first()
    if (
        dolor_anterior is not None
        and ocurrencia.nivel_dolor - dolor_anterior >= settings.ALERTA_DOLOR_SUBIDA
    ):
        return AlertaDolor.REGLA_SUBIDA

    cantidad_racha = settings.ALERTA_DOLOR_RACHA_CANTIDAD
    if cantidad_racha <= 0:
        return None

    dolores_recientes = [ocurrencia.nivel_dolor]
    dolores_recientes.extend(
        ocurrencias_anteriores.values_list('nivel_dolor', flat=True)[:cantidad_racha - 1]
    )
    if (
        len(dolores_recientes) == cantidad_racha
        and all(
            dolor is not None and dolor >= settings.ALERTA_DOLOR_RACHA_UMBRAL
            for dolor in dolores_recientes
        )
    ):
        return AlertaDolor.REGLA_RACHA

    return None


def crear_alerta_dolor(ocurrencia):
    regla = evaluar_alerta_dolor(ocurrencia)
    if regla is None:
        return None

    alerta, _ = AlertaDolor.objects.get_or_create(
        ocurrencia=ocurrencia,
        defaults={
            'paciente_id': ocurrencia.asignacion.paciente_id,
            'nivel_dolor': ocurrencia.nivel_dolor,
            'regla': regla,
        },
    )
    return alerta


def enviar_correo_alerta(alerta):
    alerta = AlertaDolor.objects.select_related('doctor', 'paciente').get(pk=alerta.pk)
    if alerta.correo_enviado_en:
        return

    if not alerta.doctor:
        alerta.correo_error = 'No se envió el correo: la alerta no tiene un médico asignado.'
        alerta.save(update_fields=['correo_error'])
        logger.warning('No se envió correo para la alerta %s: no tiene médico asignado.', alerta.pk)
        return

    if not alerta.doctor.is_active:
        alerta.correo_error = 'No se envió el correo: el médico asignado está inactivo.'
        alerta.save(update_fields=['correo_error'])
        logger.warning('No se envió correo para la alerta %s: el médico está inactivo.', alerta.pk)
        return

    try:
        fecha_local = timezone.localtime(
            alerta.creada_en,
            ZoneInfo(alerta.doctor.zona_horaria),
        ).strftime('%d/%m/%Y %H:%M')
        enviado, error = enviar_correo(
            alerta.doctor.email,
            'Alerta de dolor - Nexo ReV',
            'alerta_dolor',
            {
                'doctor_nombre': alerta.doctor.nombre,
                'paciente_nombre': alerta.paciente.nombre,
                'nivel_dolor': alerta.nivel_dolor,
                'regla': alerta.get_regla_display(),
                'fecha_local': fecha_local,
                'enlace_dashboard': '/principal/#dashboard',
            },
        )
    except Exception as error_envio:
        logger.exception('No se pudo preparar el correo para la alerta %s.', alerta.pk)
        enviado = False
        error = str(error_envio) or 'No se pudo preparar el correo de alerta.'

    alerta.correo_intentos += 1
    if enviado:
        alerta.correo_enviado_en = timezone.now()
        alerta.correo_error = ''
    else:
        alerta.correo_error = error
        logger.error('No se pudo enviar correo para la alerta %s: %s', alerta.pk, error)
    alerta.save(update_fields=['correo_enviado_en', 'correo_error', 'correo_intentos'])


def _instantes_hora_local(fecha_local, hora, zona):
    hora_local = datetime.combine(fecha_local, hora)
    instantes_validos = set()
    instantes_mapeados = []

    for fold in (0, 1):
        candidato = hora_local.replace(tzinfo=zona, fold=fold)
        instante_utc = candidato.astimezone(datetime_timezone.utc)
        vuelta_local = instante_utc.astimezone(zona)
        instantes_mapeados.append(instante_utc)
        if vuelta_local.replace(tzinfo=None) == hora_local:
            instantes_validos.add(instante_utc)

    if instantes_validos:
        return sorted(instantes_validos)

    inicio, fin = sorted(instantes_mapeados)
    offset_anterior = inicio.astimezone(zona).utcoffset()
    offset_nuevo = fin.astimezone(zona).utcoffset()
    if offset_anterior == offset_nuevo:
        logger.warning(
            'No se pudo resolver la hora local %s en la zona %s.',
            hora_local,
            zona.key,
        )
        return []

    inicio_segundos = int(inicio.timestamp())
    fin_segundos = int(fin.timestamp())
    while fin_segundos - inicio_segundos > 1:
        medio = (inicio_segundos + fin_segundos) // 2
        instante_medio = datetime.fromtimestamp(medio, datetime_timezone.utc)
        if instante_medio.astimezone(zona).utcoffset() == offset_anterior:
            inicio_segundos = medio
        else:
            fin_segundos = medio
    primer_instante_valido = datetime.fromtimestamp(fin_segundos, datetime_timezone.utc)
    return [primer_instante_valido]


def _fecha_local_recordatorio(recordatorio, ahora_utc, zona):
    fecha_hoy_local = ahora_utc.astimezone(zona).date()
    dias_recordatorio = recordatorio.dias_semana
    for fecha_programada in (
        fecha_hoy_local,
        fecha_hoy_local - timedelta(days=1),
    ):
        if fecha_programada.weekday() not in dias_recordatorio:
            continue
        instantes = _instantes_hora_local(fecha_programada, recordatorio.hora, zona)
        for instante_programado in instantes:
            transcurrido = ahora_utc - instante_programado
            if timedelta(0) <= transcurrido < RECORDATORIO_VENTANA:
                return fecha_programada
    return None


def _ocurrencias_pendientes(paciente_id, fecha_local):
    return list(
        OcurrenciaRutina.objects.filter(
            asignacion__paciente_id=paciente_id,
            fecha=fecha_local,
            completada_en__isnull=True,
        ).select_related(
            'asignacion',
        ).prefetch_related(
            'asignacion__ejercicios',
        ).order_by(
            'asignacion__titulo',
            'pk',
        )
    )


def _reclamar_registro(recordatorio, fecha_local, solo_consultar=False):
    if solo_consultar:
        registro = RegistroRecordatorio.objects.filter(
            recordatorio=recordatorio,
            fecha=fecha_local,
        ).first()
        if registro is None:
            return True
        if registro.enviado_en:
            return False
        if (
            registro.procesando_en
            and timezone.now() - registro.procesando_en < RECORDATORIO_PROCESAMIENTO_LEASE
        ):
            return False
        return True

    with transaction.atomic():
        registro, _ = RegistroRecordatorio.objects.get_or_create(
            recordatorio=recordatorio,
            fecha=fecha_local,
        )
        registro = RegistroRecordatorio.objects.select_for_update().get(pk=registro.pk)
        if registro.enviado_en:
            return None

        ahora = timezone.now()
        if (
            registro.procesando_en
            and ahora - registro.procesando_en < RECORDATORIO_PROCESAMIENTO_LEASE
        ):
            return None

        registro.procesando_en = ahora
        registro.error = ''
        registro.save(update_fields=['procesando_en', 'error'])
        return registro.pk


def _guardar_resultado_recordatorio(registro_id, enviado, error):
    with transaction.atomic():
        registro = RegistroRecordatorio.objects.select_for_update().get(pk=registro_id)
        registro.procesando_en = None
        if enviado:
            registro.enviado_en = timezone.now()
            registro.error = ''
        else:
            registro.error = error or 'No se pudo enviar el recordatorio.'
        registro.save(update_fields=['enviado_en', 'error', 'procesando_en'])


def enviar_recordatorio(recordatorio, ocurrencias, fecha_local):
    rutinas_pendientes = []
    for ocurrencia in ocurrencias:
        ejercicios = [
            ejercicio.titulo
            for ejercicio in ocurrencia.asignacion.ejercicios.all()
        ]
        if not ejercicios:
            ejercicios = [ocurrencia.asignacion.titulo]
        rutinas_pendientes.append({
            'nombre': ocurrencia.asignacion.titulo,
            'ejercicios': ejercicios,
        })

    return enviar_correo(
        recordatorio.paciente.usuario.email,
        'Recordatorio de ejercicios pendientes - Nexo ReV',
        'recordatorio',
        {
            'paciente_nombre': recordatorio.paciente.nombre,
            'fecha_recordatorio': fecha_local.strftime('%d/%m/%Y'),
            'rutinas_pendientes': rutinas_pendientes,
            'enlace_principal': '/principal/',
        },
    )


def procesar_recordatorio(recordatorio, ahora_utc, dry_run=False):
    paciente = recordatorio.paciente
    usuario = paciente.usuario
    if usuario is None:
        logger.warning(
            'Se omite el recordatorio %s: el paciente %s no tiene usuario asociado.',
            recordatorio.pk,
            paciente.pk,
        )
        return False
    if not usuario.is_active or not usuario.recordatorios_activos:
        return False

    try:
        zona = ZoneInfo(usuario.zona_horaria)
    except ZoneInfoNotFoundError:
        logger.exception(
            'Se omite el recordatorio %s por una zona horaria inválida (%s).',
            recordatorio.pk,
            usuario.zona_horaria,
        )
        return False

    fecha_local = _fecha_local_recordatorio(recordatorio, ahora_utc, zona)
    if fecha_local is None:
        return False
    ocurrencias = _ocurrencias_pendientes(paciente.pk, fecha_local)
    if not ocurrencias:
        return False

    registro_id = _reclamar_registro(
        recordatorio,
        fecha_local,
        solo_consultar=dry_run,
    )
    if dry_run:
        return registro_id is True
    if registro_id is None:
        return False

    ocurrencias = _ocurrencias_pendientes(paciente.pk, fecha_local)
    if not ocurrencias:
        _guardar_resultado_recordatorio(
            registro_id,
            False,
            'No hay ejercicios pendientes para la fecha del recordatorio.',
        )
        return True

    try:
        enviado, error = enviar_recordatorio(recordatorio, ocurrencias, fecha_local)
    except Exception as error_envio:
        logger.exception(
            'Error inesperado al preparar el recordatorio %s.',
            recordatorio.pk,
        )
        enviado = False
        error = str(error_envio) or 'No se pudo preparar el correo del recordatorio.'

    _guardar_resultado_recordatorio(registro_id, enviado, error)
    if not enviado:
        logger.error(
            'No se pudo enviar el recordatorio %s para el %s: %s',
            recordatorio.pk,
            fecha_local,
            error,
        )
    return True


def _coerce_zone(zona):
    return zona if isinstance(zona, ZoneInfo) else ZoneInfo(zona)


def inicio_de_semana(fecha, zona):
    zona = _coerce_zone(zona)
    if isinstance(fecha, datetime):
        fecha_local = (
            timezone.localtime(fecha, zona)
            if timezone.is_aware(fecha)
            else fecha
        ).date()
    elif isinstance(fecha, date):
        fecha_local = fecha
    else:
        raise TypeError('fecha debe ser date o datetime.')
    return fecha_local - timedelta(days=fecha_local.weekday())


def _zona_resumen_paciente(paciente, zona):
    if zona is not None:
        return _coerce_zone(zona), False

    usuario = paciente.usuario
    if usuario is None:
        return _coerce_zone(settings.TIME_ZONE), True

    try:
        return ZoneInfo(usuario.zona_horaria), False
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        logger.warning(
            'Zona horaria inválida para paciente_id=%s (%s); se usará settings.TIME_ZONE.',
            paciente.pk,
            usuario.zona_horaria,
        )
        return _coerce_zone(settings.TIME_ZONE), True


def _promedio_eva(valores):
    valores = list(valores)
    if not valores:
        return None
    return round(sum(valores) / len(valores), 2)


def _metrica_key(metrica, unidad):
    if not metrica:
        return None
    return (metrica.strip().casefold(), unidad.strip().casefold())


def resumen_semanal(paciente, semana_inicio, zona=None):
    zona, zona_es_respaldo = _zona_resumen_paciente(paciente, zona)
    inicio = inicio_de_semana(semana_inicio, zona)
    fin = inicio + timedelta(days=6)
    inicio_local = datetime.combine(inicio, time.min, tzinfo=zona)
    fin_local = datetime.combine(fin, time.max, tzinfo=zona)
    inicio_utc = inicio_local.astimezone(datetime_timezone.utc)
    fin_utc = fin_local.astimezone(datetime_timezone.utc)

    ocurrencias = list(
        OcurrenciaRutina.objects.filter(
            asignacion__paciente_id=paciente.pk,
            fecha__gte=inicio,
            fecha__lte=fin,
        ).order_by('fecha', 'pk')
    )
    asignaciones_con_ocurrencias = OcurrenciaRutina.objects.filter(
        asignacion__paciente_id=paciente.pk,
    ).values_list('asignacion_id', flat=True)
    asignaciones_legacy = RutinaAsignada.objects.filter(
        paciente_id=paciente.pk,
        fecha_programada__gte=inicio,
        fecha_programada__lte=fin,
    ).exclude(
        pk__in=asignaciones_con_ocurrencias,
    )
    legacy_count = asignaciones_legacy.count()
    legacy_completed = asignaciones_legacy.filter(
        completada_en__isnull=False,
    ).count()

    rutinas_programadas = len(ocurrencias) + legacy_count
    rutinas_completadas = sum(
        ocurrencia.completada_en is not None
        for ocurrencia in ocurrencias
    ) + legacy_completed
    adherencia = (
        round(rutinas_completadas * 100 / rutinas_programadas, 2)
        if rutinas_programadas
        else None
    )

    eva_actual = _promedio_eva(
        ocurrencia.nivel_dolor
        for ocurrencia in ocurrencias
        if ocurrencia.completada_en is not None and ocurrencia.nivel_dolor is not None
    )
    semana_anterior_inicio = inicio - timedelta(days=7)
    semana_anterior_fin = inicio - timedelta(days=1)
    eva_anterior = _promedio_eva(
        OcurrenciaRutina.objects.filter(
            asignacion__paciente_id=paciente.pk,
            fecha__gte=semana_anterior_inicio,
            fecha__lte=semana_anterior_fin,
            completada_en__isnull=False,
            nivel_dolor__isnull=False,
        ).values_list('nivel_dolor', flat=True)
    )
    variacion_eva = (
        round(eva_actual - eva_anterior, 2)
        if eva_actual is not None and eva_anterior is not None
        else None
    )

    evaluacion_reciente = EvaluacionClinica.objects.filter(
        paciente_id=paciente.pk,
        fecha__gte=inicio_utc,
        fecha__lte=fin_utc,
    ).order_by('-fecha', '-pk').first()
    ultima_evaluacion = None
    if evaluacion_reciente:
        ultima_evaluacion = {
            'fecha_local': timezone.localtime(evaluacion_reciente.fecha, zona).isoformat(),
            'nivel_dolor': evaluacion_reciente.nivel_dolor,
        }

    estados_sesion = {
        Sesion.ESTADO_PROGRAMADA: 0,
        Sesion.ESTADO_COMPLETADA: 0,
        Sesion.ESTADO_CANCELADA: 0,
        Sesion.ESTADO_NO_ASISTIO: 0,
    }
    conteos_sesion = Sesion.objects.filter(
        paciente_id=paciente.pk,
        fecha__gte=inicio_utc,
        fecha__lte=fin_utc,
        estado__in=estados_sesion,
    ).values('estado').annotate(total=Count('pk'))
    for conteo in conteos_sesion:
        estados_sesion[conteo['estado']] = conteo['total']

    ocurrencias_activas = OcurrenciaRutina.objects.filter(
        asignacion__paciente_id=paciente.pk,
        completada_en__gte=inicio_utc,
        completada_en__lte=fin_utc,
    ).values_list('completada_en', flat=True)
    dias_actividad = {
        timezone.localtime(completada_en, zona).date()
        for completada_en in ocurrencias_activas
    }
    asignaciones_completadas_legacy = RutinaAsignada.objects.filter(
        paciente_id=paciente.pk,
        completada_en__gte=inicio_utc,
        completada_en__lte=fin_utc,
    ).exclude(pk__in=asignaciones_con_ocurrencias).values_list(
        'completada_en',
        flat=True,
    )
    dias_actividad.update(
        timezone.localtime(completada_en, zona).date()
        for completada_en in asignaciones_completadas_legacy
    )

    alertas = list(
        AlertaDolor.objects.filter(
            paciente_id=paciente.pk,
            creada_en__gte=inicio_utc,
            creada_en__lte=fin_utc,
        ).order_by('creada_en', 'pk')
    )
    alertas_dolor = [
        {
            'fecha_local': timezone.localtime(alerta.creada_en, zona).isoformat(),
            'nivel_dolor': alerta.nivel_dolor,
            'regla': alerta.regla,
            'estado': alerta.estado,
        }
        for alerta in alertas
    ]

    objetivos = list(
        ObjetivoTerapeutico.objects.filter(
            paciente_id=paciente.pk,
            creado_en__lte=fin_utc,
        ).order_by('pk')
    )
    metricas_objetivo = {
        key
        for key in (
            _metrica_key(objetivo.metrica, objetivo.unidad)
            for objetivo in objetivos
        )
        if key is not None
    }
    evaluaciones_objetivo = EvaluacionClinica.objects.filter(
        paciente_id=paciente.pk,
        fecha__lte=fin_utc,
        valor_actual__isnull=False,
    ).order_by('fecha', 'pk')
    evaluaciones_por_metrica = {}
    if metricas_objetivo:
        for evaluacion in evaluaciones_objetivo:
            key = _metrica_key(evaluacion.metrica, evaluacion.unidad)
            if key in metricas_objetivo:
                evaluaciones_por_metrica[key] = evaluacion

    detalle_objetivos = []
    for objetivo in objetivos:
        evaluacion = evaluaciones_por_metrica.get(
            _metrica_key(objetivo.metrica, objetivo.unidad),
        )
        cumplido = bool(evaluacion and (
            evaluacion.valor_actual <= objetivo.valor_objetivo
            if objetivo.direccion == ObjetivoTerapeutico.DIRECCION_MENOR
            else evaluacion.valor_actual >= objetivo.valor_objetivo
        ))
        detalle_objetivos.append({
            'nombre': objetivo.nombre,
            'cumplido': cumplido,
        })

    return {
        'semana': {
            'inicio': inicio.isoformat(),
            'fin': fin.isoformat(),
        },
        'zona_usada': zona.key,
        'zona_es_respaldo': zona_es_respaldo,
        'rutinas': {
            'programadas': rutinas_programadas,
            'completadas': rutinas_completadas,
            'adherencia_pct': adherencia,
        },
        'eva': {
            'promedio': eva_actual,
            'promedio_semana_anterior': eva_anterior,
            'variacion': variacion_eva,
        },
        'ultima_evaluacion': ultima_evaluacion,
        'sesiones': {'por_estado': estados_sesion},
        'dias_con_actividad': len(dias_actividad),
        'alertas_dolor': {
            'total': len(alertas_dolor),
            'items': alertas_dolor,
        },
        'objetivos_cumplidos': sum(
            objetivo['cumplido'] for objetivo in detalle_objetivos
        ),
        'objetivos_total': len(detalle_objetivos),
        'objetivos_detalle': detalle_objetivos,
    }


def semana_resumen_pendiente(paciente, ahora_utc):
    if timezone.is_naive(ahora_utc):
        raise ValueError('ahora_utc debe incluir zona horaria.')

    zona, _ = _zona_resumen_paciente(paciente, None)
    ahora_local = ahora_utc.astimezone(zona)
    dia_corte = settings.RESUMEN_SEMANAL_DIA
    fecha_corte = ahora_local.date() - timedelta(
        days=(ahora_local.weekday() - dia_corte) % 7,
    )
    hora_corte = time(hour=settings.RESUMEN_SEMANAL_HORA)
    instante_corte = datetime.combine(fecha_corte, hora_corte, tzinfo=zona)

    if ahora_local < instante_corte:
        fecha_corte -= timedelta(days=7)

    semana_corte = inicio_de_semana(fecha_corte, zona)
    if dia_corte < 6:
        semana_corte -= timedelta(days=7)
    return semana_corte


def enviar_resumen_semanal(paciente, semana_inicio):
    if paciente.usuario is None:
        logger.warning(
            'No se envió resumen semanal para paciente_id=%s: no tiene usuario asociado.',
            paciente.pk,
        )
        return False

    zona, _ = _zona_resumen_paciente(paciente, None)
    semana_inicio = inicio_de_semana(semana_inicio, zona)
    with transaction.atomic():
        envio, _ = EnvioResumenSemanal.objects.get_or_create(
            paciente=paciente,
            semana_inicio=semana_inicio,
        )
        envio = EnvioResumenSemanal.objects.select_for_update().get(pk=envio.pk)
        if envio.enviado_en:
            return False

        resumen = resumen_semanal(paciente, semana_inicio, zona=zona)
        enviado, error = enviar_correo(
            paciente.usuario.email,
            'Tu resumen semanal - Nexo ReV',
            'resumen_semanal',
            {
                'paciente_nombre': paciente.nombre,
                'semana_inicio': resumen['semana']['inicio'],
                'semana_fin': resumen['semana']['fin'],
                'resumen': resumen,
                'enlace_principal': '/principal/',
            },
        )
        if enviado:
            envio.enviado_en = timezone.now()
            envio.error = ''
        else:
            envio.enviado_en = None
            envio.error = error or 'No se pudo enviar el resumen semanal.'
            logger.error(
                'No se pudo enviar el resumen semanal de paciente_id=%s '
                'para la semana %s: %s',
                paciente.pk,
                semana_inicio,
                envio.error,
            )
        envio.save(update_fields=['enviado_en', 'error'])
    return True