import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone

from crear_cuenta.models import Usuario
from princpal.models import Paciente, Sesion
from .forms import RecordatorioForm
from .exports import exportar_reporte_pdf, exportar_reporte_xlsx
from .models import AlertaDolor, Recordatorio
from .services import inicio_de_semana, resumen_semanal


PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100
REPORTE_PACIENTES_MAX = 200


def _error(message, status):
    return JsonResponse({'success': False, 'error': message}, status=status)


def _active_doctor(request):
    email = request.session.get('current_user')
    if not email:
        return None, _error('Tu sesión expiró. Inicia sesión nuevamente.', 401)

    if request.session.get('current_user_role') != Usuario.ROLE_DOCTOR:
        return None, _error('Esta acción requiere una cuenta de médico.', 403)

    doctor = Usuario.objects.filter(
        email=email,
        role=Usuario.ROLE_DOCTOR,
        is_active=True,
    ).first()
    if doctor is None:
        return None, _error('No se encontró un médico activo para esta sesión.', 403)
    return doctor, None


def _parse_positive_int(value, label):
    if value is None or not value.isdecimal():
        return None, _error(f'El parámetro {label} debe ser un entero positivo.', 400)
    number = int(value)
    if number < 1:
        return None, _error(f'El parámetro {label} debe ser un entero positivo.', 400)
    return number, None


def _parse_page_number(value):
    normalized = value.strip()
    sign = 1
    if normalized[:1] in ('+', '-'):
        if normalized[0] == '-':
            sign = -1
        normalized = normalized[1:]
    if not normalized.isdecimal():
        return None, _error('El parámetro page debe ser un entero.', 400)

    digits = normalized.lstrip('0') or '0'
    if len(digits) > 18:
        return sign * (10 ** 18), None
    return sign * int(digits), None


def _parse_date(value, label):
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, _error(f'El parámetro {label} debe tener formato AAAA-MM-DD.', 400)
    if parsed.isoformat() != value:
        return None, _error(f'El parámetro {label} debe tener formato AAAA-MM-DD.', 400)
    return parsed, None


def _local_iso(value, zone):
    return timezone.localtime(value, zone).isoformat() if value else None


def _serialize_alert(alerta, zone):
    return {
        'id': alerta.pk,
        'paciente_id': alerta.paciente_id,
        'paciente_nombre': alerta.paciente.nombre,
        'creada_en': _local_iso(alerta.creada_en, zone),
        'nivel_dolor': alerta.nivel_dolor,
        'regla': alerta.regla,
        'regla_display': alerta.get_regla_display(),
        'estado': alerta.estado,
        'estado_display': alerta.get_estado_display(),
        'vista_en': _local_iso(alerta.vista_en, zone),
        'atendida_por': alerta.atendida_por.nombre if alerta.atendida_por else None,
        'atendida_en': _local_iso(alerta.atendida_en, zone),
        'nota_atencion': alerta.nota_atencion,
    }


def _owned_alerts(doctor):
    return AlertaDolor.objects.select_related(
        'paciente',
        'atendida_por',
    ).filter(
        doctor=doctor,
        paciente__doctor=doctor,
    )


def _owned_alert(doctor, alerta_id, lock=False):
    queryset = _owned_alerts(doctor)
    if lock:
        queryset = queryset.select_for_update(of=('self',))
    return queryset.filter(pk=alerta_id).first()


def alertas_dolor(request):
    doctor, error = _active_doctor(request)
    if error:
        return error
    if request.method != 'GET':
        return _error('Método no permitido.', 405)

    estado = request.GET.get('estado')
    if estado is not None:
        estados_validos = {choice[0] for choice in AlertaDolor.ESTADO_CHOICES}
        if estado not in estados_validos:
            return _error('El filtro estado no es válido.', 400)

    paciente_id = None
    paciente_param = request.GET.get('paciente')
    if paciente_param is not None:
        paciente_id, error = _parse_positive_int(paciente_param, 'paciente')
        if error:
            return error
        if not Paciente.objects.filter(pk=paciente_id, doctor=doctor).exists():
            return _error('El paciente no pertenece a este médico.', 403)

    fecha_desde = None
    fecha_hasta = None
    if 'fecha_desde' in request.GET:
        fecha_desde, error = _parse_date(request.GET['fecha_desde'], 'fecha_desde')
        if error:
            return error
    if 'fecha_hasta' in request.GET:
        fecha_hasta, error = _parse_date(request.GET['fecha_hasta'], 'fecha_hasta')
        if error:
            return error
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        return _error('fecha_desde no puede ser posterior a fecha_hasta.', 400)

    page_number, error = _parse_page_number(request.GET.get('page', '1'))
    if error:
        return error
    page_size, error = _parse_positive_int(
        request.GET.get('page_size', str(PAGE_SIZE_DEFAULT)),
        'page_size',
    )
    if error:
        return error
    page_size = min(page_size, PAGE_SIZE_MAX)

    zone = ZoneInfo(doctor.zona_horaria)
    queryset = _owned_alerts(doctor).order_by('-creada_en', '-pk')
    nuevas_count = queryset.filter(estado=AlertaDolor.ESTADO_NUEVA).count()

    if estado is not None:
        queryset = queryset.filter(estado=estado)
    if paciente_id is not None:
        queryset = queryset.filter(paciente_id=paciente_id)
    if fecha_desde is not None:
        inicio_local = timezone.make_aware(datetime.combine(fecha_desde, time.min), zone)
        queryset = queryset.filter(creada_en__gte=inicio_local)
    if fecha_hasta is not None:
        fin_local = timezone.make_aware(datetime.combine(fecha_hasta, time.max), zone)
        queryset = queryset.filter(creada_en__lte=fin_local)

    paginator = Paginator(queryset, page_size)
    try:
        pagina = paginator.page(page_number)
    except EmptyPage:
        pagina = paginator.page(paginator.num_pages)

    return JsonResponse({
        'success': True,
        'alertas': [_serialize_alert(alerta, zone) for alerta in pagina.object_list],
        'nuevas_count': nuevas_count,
        'total': paginator.count,
        'page': pagina.number,
        'page_size': page_size,
        'pages': paginator.num_pages,
    })


def marcar_alerta_vista(request, alerta_id):
    doctor, error = _active_doctor(request)
    if error:
        return error
    if request.method != 'POST':
        return _error('Método no permitido.', 405)

    with transaction.atomic():
        alerta = _owned_alert(doctor, alerta_id, lock=True)
        if alerta is None:
            return _error('No se encontró la alerta.', 404)
        if alerta.estado == AlertaDolor.ESTADO_NUEVA:
            alerta.estado = AlertaDolor.ESTADO_VISTA
            alerta.vista_en = timezone.now()
            alerta.save(update_fields=['estado', 'vista_en'])

    return JsonResponse({'success': True, 'alerta': _serialize_alert(alerta, ZoneInfo(doctor.zona_horaria))})


def _request_note(request):
    if request.content_type == 'application/json':
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, _error('El cuerpo JSON no es válido.', 400)
        if not isinstance(payload, dict):
            return None, _error('El cuerpo JSON debe ser un objeto.', 400)
        nota = payload.get('nota', '')
    else:
        nota = request.POST.get('nota', '')

    if not isinstance(nota, str):
        return None, _error('La nota debe ser texto.', 400)
    nota = nota.strip()
    if len(nota) > 500:
        return None, _error('La nota no puede superar 500 caracteres.', 400)
    return nota, None


def marcar_alerta_atendida(request, alerta_id):
    doctor, error = _active_doctor(request)
    if error:
        return error
    if request.method != 'POST':
        return _error('Método no permitido.', 405)

    nota, error = _request_note(request)
    if error:
        return error

    with transaction.atomic():
        alerta = _owned_alert(doctor, alerta_id, lock=True)
        if alerta is None:
            return _error('No se encontró la alerta.', 404)
        if alerta.estado != AlertaDolor.ESTADO_ATENDIDA:
            alerta.estado = AlertaDolor.ESTADO_ATENDIDA
            alerta.atendida_por = doctor
            alerta.atendida_en = timezone.now()
            alerta.nota_atencion = nota
            alerta.save(update_fields=[
                'estado',
                'atendida_por',
                'atendida_en',
                'nota_atencion',
            ])

    return JsonResponse({'success': True, 'alerta': _serialize_alert(alerta, ZoneInfo(doctor.zona_horaria))})


def _active_patient(request):
    email = request.session.get('current_user')
    if not email:
        return None, None, _error('Tu sesión expiró. Inicia sesión nuevamente.', 401)

    if request.session.get('current_user_role') != Usuario.ROLE_PACIENTE:
        return None, None, _error('Esta acción requiere una cuenta de paciente.', 403)

    usuario = Usuario.objects.filter(
        email=email,
        role=Usuario.ROLE_PACIENTE,
        is_active=True,
    ).first()
    if usuario is None:
        return None, None, _error('No se encontró un paciente activo para esta sesión.', 403)

    paciente = Paciente.objects.filter(usuario=usuario).first()
    if paciente is None:
        return None, None, _error('La cuenta no tiene un perfil de paciente asociado.', 404)
    return usuario, paciente, None


def _reminder_json_data(request):
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, _error('El cuerpo JSON no es válido.', 400)
        if not isinstance(data, dict):
            return None, _error('El cuerpo JSON debe ser un objeto.', 400)
        return data, None

    if request.method == 'POST':
        data = request.POST.dict()
        dias = request.POST.getlist('dias_semana')
        if dias:
            data['dias_semana'] = dias
        return data, None
    return None, _error('El cuerpo de la solicitud debe ser JSON.', 400)


def _serialize_reminder(recordatorio, zone):
    return {
        'id': recordatorio.pk,
        'hora': recordatorio.hora.strftime('%H:%M'),
        'dias_semana': recordatorio.dias_semana,
        'activo': recordatorio.activo,
        'creado_en': _local_iso(recordatorio.creado_en, zone),
    }


def _reminder_form_error(form):
    return _error(f'Datos inválidos: {form.errors.as_text()}', 400)


def _save_reminder_form(form):
    try:
        with transaction.atomic():
            return form.save(), None
    except IntegrityError:
        return None, _error('Ya existe un recordatorio activo para esa hora.', 400)


def recordatorios_paciente(request):
    usuario, paciente, error = _active_patient(request)
    if error:
        return error

    if request.method == 'GET':
        zone = ZoneInfo(usuario.zona_horaria)
        recordatorios = Recordatorio.objects.filter(
            paciente=paciente,
        ).order_by('hora', 'pk')
        return JsonResponse({
            'success': True,
            'recordatorios': [
                _serialize_reminder(recordatorio, zone)
                for recordatorio in recordatorios
            ],
            'zona_horaria': usuario.zona_horaria,
            'recordatorios_activos': usuario.recordatorios_activos,
        })

    if request.method != 'POST':
        return _error('Método no permitido.', 405)

    data, error = _reminder_json_data(request)
    if error:
        return error
    if set(data) - {'hora', 'dias_semana'}:
        return _error('Solo se permiten los campos hora y dias_semana.', 400)
    form_data = {
        'paciente': str(paciente.pk),
        'hora': data.get('hora'),
        'dias_semana': data.get('dias_semana'),
        'activo': True,
    }

    with transaction.atomic():
        paciente = Paciente.objects.select_for_update().get(pk=paciente.pk)
        form = RecordatorioForm(data=form_data)
        if not form.is_valid():
            return _reminder_form_error(form)
        recordatorio, error = _save_reminder_form(form)
        if error:
            return error

    return JsonResponse({
        'success': True,
        'recordatorio': _serialize_reminder(recordatorio, ZoneInfo(usuario.zona_horaria)),
    }, status=201)


def editar_recordatorio(request, recordatorio_id):
    usuario, paciente, error = _active_patient(request)
    if error:
        return error
    if request.method != 'PATCH':
        return _error('Método no permitido.', 405)

    data, error = _reminder_json_data(request)
    if error:
        return error
    if not data or set(data) - {'hora', 'dias_semana'}:
        return _error('Indica hora o dias_semana para editar.', 400)

    with transaction.atomic():
        paciente = Paciente.objects.select_for_update().get(pk=paciente.pk)
        recordatorio = Recordatorio.objects.select_for_update().filter(
            pk=recordatorio_id,
            paciente=paciente,
        ).first()
        if recordatorio is None:
            return _error('No se encontró el recordatorio.', 404)

        form_data = {
            'paciente': str(paciente.pk),
            'hora': data.get('hora', recordatorio.hora.strftime('%H:%M')),
            'dias_semana': data.get('dias_semana', recordatorio.dias_semana),
            'activo': recordatorio.activo,
        }
        form = RecordatorioForm(data=form_data, instance=recordatorio)
        if not form.is_valid():
            return _reminder_form_error(form)
        recordatorio, error = _save_reminder_form(form)
        if error:
            return error

    return JsonResponse({
        'success': True,
        'recordatorio': _serialize_reminder(recordatorio, ZoneInfo(usuario.zona_horaria)),
    })


def cambiar_estado_recordatorio(request, recordatorio_id):
    usuario, paciente, error = _active_patient(request)
    if error:
        return error
    if request.method != 'PATCH':
        return _error('Método no permitido.', 405)

    data, error = _reminder_json_data(request)
    if error:
        return error
    if set(data) != {'activo'} or type(data['activo']) is not bool:
        return _error('El campo activo debe ser un booleano.', 400)

    with transaction.atomic():
        paciente = Paciente.objects.select_for_update().get(pk=paciente.pk)
        recordatorio = Recordatorio.objects.select_for_update().filter(
            pk=recordatorio_id,
            paciente=paciente,
        ).first()
        if recordatorio is None:
            return _error('No se encontró el recordatorio.', 404)

        form_data = {
            'paciente': str(paciente.pk),
            'hora': recordatorio.hora.strftime('%H:%M'),
            'dias_semana': recordatorio.dias_semana,
            'activo': data['activo'],
        }
        form = RecordatorioForm(data=form_data, instance=recordatorio)
        if not form.is_valid():
            return _reminder_form_error(form)
        recordatorio, error = _save_reminder_form(form)
        if error:
            return error

    return JsonResponse({
        'success': True,
        'recordatorio': _serialize_reminder(recordatorio, ZoneInfo(usuario.zona_horaria)),
    })


def eliminar_recordatorio(request, recordatorio_id):
    usuario, paciente, error = _active_patient(request)
    if error:
        return error
    if request.method != 'DELETE':
        return _error('Método no permitido.', 405)

    with transaction.atomic():
        paciente = Paciente.objects.select_for_update().get(pk=paciente.pk)
        recordatorio = Recordatorio.objects.select_for_update().filter(
            pk=recordatorio_id,
            paciente=paciente,
        ).first()
        if recordatorio is None:
            return _error('No se encontró el recordatorio.', 404)
        recordatorio_id = recordatorio.pk
        recordatorio.delete()

    return JsonResponse({'success': True, 'eliminado': recordatorio_id})


def recordatorio_detalle(request, recordatorio_id):
    if request.method == 'PATCH':
        return editar_recordatorio(request, recordatorio_id)
    if request.method == 'DELETE':
        return eliminar_recordatorio(request, recordatorio_id)

    _, _, error = _active_patient(request)
    if error:
        return error
    return _error('Método no permitido.', 405)


def reporte_semanal(request):
    doctor, error = _active_doctor(request)
    if error:
        return error
    if request.method != 'GET':
        return _error('Método no permitido.', 405)

    formato = request.GET.get('formato')
    if formato not in (None, 'pdf', 'xlsx'):
        return _error('El parámetro formato debe ser pdf o xlsx.', 400)

    zona_doctor = ZoneInfo(doctor.zona_horaria)
    if 'semana' in request.GET:
        fecha_semana, error = _parse_date(request.GET['semana'], 'semana')
        if error:
            return error
        semana_inicio = inicio_de_semana(fecha_semana, zona_doctor)
    else:
        hoy_doctor = timezone.localdate(timezone=zona_doctor)
        semana_inicio = inicio_de_semana(hoy_doctor, zona_doctor) - timedelta(days=7)

    ids_solicitados = [
        valor
        for valor in request.GET.getlist('pacientes')
        if valor != ''
    ]
    if len(ids_solicitados) > REPORTE_PACIENTES_MAX:
        return _error(
            f'No se permiten más de {REPORTE_PACIENTES_MAX} ids en pacientes.',
            400,
        )

    paciente_ids = []
    for valor in ids_solicitados:
        paciente_id, error = _parse_positive_int(valor, 'pacientes')
        if error:
            return error
        paciente_ids.append(paciente_id)
    paciente_ids = list(dict.fromkeys(paciente_ids))

    pacientes_doctor = list(
        Paciente.objects.filter(
            doctor=doctor,
        ).select_related(
            'usuario',
        ).order_by(
            'pk',
        )
    )
    pacientes_por_id = {
        paciente.pk: paciente
        for paciente in pacientes_doctor
    }
    if paciente_ids:
        if any(paciente_id not in pacientes_por_id for paciente_id in paciente_ids):
            return _error('El paciente no pertenece a este médico.', 403)
        pacientes = [pacientes_por_id[paciente_id] for paciente_id in paciente_ids]
    else:
        pacientes = pacientes_doctor

    filas = []
    for paciente in pacientes:
        filas.append({
            'paciente_id': paciente.pk,
            'paciente_nombre': paciente.nombre,
            'resumen': resumen_semanal(paciente, semana_inicio),
        })

    sesiones_por_estado = {
        estado: 0
        for estado, _ in Sesion.ESTADO_CHOICES
    }
    for fila in filas:
        for estado, cantidad in fila['resumen']['sesiones']['por_estado'].items():
            sesiones_por_estado[estado] += cantidad

    rutinas_programadas = sum(
        fila['resumen']['rutinas']['programadas']
        for fila in filas
    )
    rutinas_completadas = sum(
        fila['resumen']['rutinas']['completadas']
        for fila in filas
    )
    totales = {
        'pacientes': len(filas),
        'rutinas_programadas': rutinas_programadas,
        'rutinas_completadas': rutinas_completadas,
        'adherencia_pct': (
            round(rutinas_completadas * 100 / rutinas_programadas, 2)
            if rutinas_programadas
            else None
        ),
        'sesiones_por_estado': sesiones_por_estado,
        'dias_con_actividad': sum(
            fila['resumen']['dias_con_actividad']
            for fila in filas
        ),
        'alertas_dolor': sum(
            fila['resumen']['alertas_dolor']['total']
            for fila in filas
        ),
        'objetivos_cumplidos': sum(
            fila['resumen']['objetivos_cumplidos']
            for fila in filas
        ),
        'objetivos_total': sum(
            fila['resumen']['objetivos_total']
            for fila in filas
        ),
    }
    reporte = {
        'success': True,
        'semana': {
            'inicio': semana_inicio.isoformat(),
            'fin': (semana_inicio + timedelta(days=6)).isoformat(),
        },
        'totales': totales,
        'pacientes': filas,
    }
    if formato == 'xlsx':
        return exportar_reporte_xlsx(reporte)
    if formato == 'pdf':
        return exportar_reporte_pdf(reporte)
    return JsonResponse(reporte)