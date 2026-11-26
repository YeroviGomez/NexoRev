from functools import wraps

from django.db import transaction
from django.db.models import Count, DateTimeField, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from mensajeria.models import Mensaje
from mensajeria.permisos import (
    pacientes_conversables,
    tiene_acceso_a_paciente,
    usuario_de_sesion,
)
from mensajeria.servicios import (
    mensajes_no_leidos,
    publicar_a_participantes,
    publicar_contadores_a_participantes,
    resumen_no_leidos,
    texto_mensaje_para_usuario,
)
from princpal.models import Paciente


def requiere_usuario_mensajeria(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        usuario = usuario_de_sesion(request.session)
        if not usuario:
            if request.path.startswith('/mensajeria/api/'):
                return JsonResponse(
                    {'error': 'Tu sesión terminó. Inicia sesión nuevamente.'},
                    status=401,
                )
            return redirect('login')
        request.mensajeria_usuario = usuario
        return view_func(request, *args, **kwargs)

    return wrapper


def _serializar_mensaje(mensaje, usuario):
    return {
        'id': mensaje.pk,
        'paciente_id': mensaje.paciente_id,
        'autor_id': mensaje.autor_id,
        'tipo_mensaje': mensaje.tipo,
        'texto': texto_mensaje_para_usuario(mensaje.texto, mensaje.tipo, usuario),
        'creado_en': mensaje.creado_en.isoformat(),
        'leido_en': mensaje.leido_en.isoformat() if mensaje.leido_en else None,
    }


def _resumen_conversaciones(usuario):
    ultimo_mensaje = Mensaje.objects.filter(paciente_id=OuterRef('pk')).order_by(
        '-creado_en', '-pk'
    )
    if usuario.role == 'doctor':
        ultimo_mensaje = ultimo_mensaje.filter(
            Q(paciente__asignaciones__chat_visible_desde__isnull=True)
            | Q(creado_en__gte=F('paciente__asignaciones__chat_visible_desde')),
            paciente__asignaciones__doctor=usuario,
            paciente__asignaciones__fin__isnull=True,
        )
    pacientes = pacientes_conversables(usuario).select_related('usuario').annotate(
        ultimo_mensaje_id=Subquery(ultimo_mensaje.values('pk')[:1]),
        ultimo_mensaje_texto=Subquery(ultimo_mensaje.values('texto')[:1]),
        ultimo_mensaje_fecha=Subquery(
            ultimo_mensaje.values('creado_en')[:1],
            output_field=DateTimeField(),
        ),
        ultimo_mensaje_tipo=Subquery(ultimo_mensaje.values('tipo')[:1]),
        ultima_actividad=Coalesce(
            Subquery(
                ultimo_mensaje.values('creado_en')[:1],
                output_field=DateTimeField(),
            ),
            F('fecha_registro'),
        ),
    ).order_by('-ultima_actividad', '-pk')
    no_leidos_por_paciente = {
        row['paciente_id']: row['total']
        for row in mensajes_no_leidos(usuario).values('paciente_id').annotate(total=Count('pk'))
    }
    return [
        {
            'paciente_id': paciente.pk,
            'nombre': paciente.nombre,
            'usuario_nombre': paciente.usuario.nombre,
            'ultimo_mensaje_id': paciente.ultimo_mensaje_id,
            'ultimo_mensaje': texto_mensaje_para_usuario(
                paciente.ultimo_mensaje_texto or '',
                paciente.ultimo_mensaje_tipo,
                usuario,
            ),
            'ultimo_mensaje_fecha': (
                paciente.ultimo_mensaje_fecha.isoformat()
                if paciente.ultimo_mensaje_fecha else None
            ),
            'no_leidos': no_leidos_por_paciente.get(paciente.pk, 0),
        }
        for paciente in pacientes
        if tiene_acceso_a_paciente(usuario, paciente)
    ]


@never_cache
@ensure_csrf_cookie
@requiere_usuario_mensajeria
def inicio(request):
    usuario = request.mensajeria_usuario
    context = {
        'usuario': usuario,
        'ws_activo': False,
        'conversaciones': [],
        'paciente_id': None,
        'doctor_nombre': '',
        'sin_medico': False,
    }
    if usuario.role == 'doctor':
        context['conversaciones'] = _resumen_conversaciones(usuario)
        context['ws_activo'] = True
    elif usuario.role == 'paciente':
        paciente = (
            Paciente.objects.select_related('doctor')
            .filter(usuario=usuario)
            .first()
        )
        context['ws_activo'] = bool(paciente)
        if paciente and paciente.doctor_id and tiene_acceso_a_paciente(usuario, paciente):
            context.update({
                'paciente_id': paciente.pk,
                'doctor_nombre': paciente.doctor.nombre,
                'ws_activo': True,
            })
        else:
            context['sin_medico'] = True
    return render(request, 'mensajeria/inicio.html', context)


@require_GET
@requiere_usuario_mensajeria
def lista_conversaciones(request):
    if request.mensajeria_usuario.role != 'doctor':
        return JsonResponse({'error': 'Solo los médicos pueden consultar la lista.'}, status=403)
    return JsonResponse({'conversaciones': _resumen_conversaciones(request.mensajeria_usuario)})


@require_GET
@requiere_usuario_mensajeria
def historial_mensajes(request, paciente_id):
    usuario = request.mensajeria_usuario
    cursor = request.GET.get('antes')
    if cursor:
        try:
            cursor = int(cursor)
        except ValueError:
            return JsonResponse({'error': 'El cursor debe ser un identificador válido.'}, status=400)
        if cursor < 1:
            return JsonResponse({'error': 'El cursor debe ser un identificador válido.'}, status=400)

    with transaction.atomic():
        paciente = Paciente.objects.select_for_update().filter(pk=paciente_id).first()
        if not paciente or not tiene_acceso_a_paciente(usuario, paciente):
            return JsonResponse({'error': 'No tienes acceso a esta conversación.'}, status=403)

        queryset = Mensaje.objects.filter(paciente=paciente).select_related('autor')
        if usuario.role == 'doctor':
            assignment = (
                paciente.asignaciones.filter(
                    doctor_id=paciente.doctor_id,
                    fin__isnull=True,
                )
                .only('chat_visible_desde')
                .first()
            )
            if assignment and assignment.chat_visible_desde:
                queryset = queryset.filter(creado_en__gte=assignment.chat_visible_desde)
        if cursor:
            queryset = queryset.filter(pk__lt=cursor)
        pagina = list(queryset.order_by('-creado_en', '-pk')[:41])
        hay_mas = len(pagina) > 40
        pagina = pagina[:40]
        pagina.reverse()
        mensajes = [_serializar_mensaje(mensaje, usuario) for mensaje in pagina]
    return JsonResponse({
        'mensajes': mensajes,
        'hay_mas': hay_mas,
        'siguiente_cursor': pagina[0].pk if hay_mas and pagina else None,
    })


@require_POST
@requiere_usuario_mensajeria
def marcar_leidos(request, paciente_id):
    usuario = request.mensajeria_usuario
    with transaction.atomic():
        paciente = Paciente.objects.select_for_update().filter(pk=paciente_id).first()
        if not paciente or not tiene_acceso_a_paciente(usuario, paciente):
            return JsonResponse({'error': 'No tienes acceso a esta conversación.'}, status=403)

        ahora = timezone.now()
        pendientes = mensajes_no_leidos(usuario, paciente)
        mensajes_ids = list(pendientes.values_list('pk', flat=True))
        pendientes.update(leido_en=ahora)
    publicar_a_participantes(
        paciente,
        {
            'tipo': 'leido',
            'paciente_id': paciente.pk,
            'leido_por': usuario.pk,
            'leido_en': ahora.isoformat(),
            'mensajes_ids': mensajes_ids,
        },
    )
    publicar_contadores_a_participantes(paciente)
    return JsonResponse(resumen_no_leidos(usuario))


@require_GET
@requiere_usuario_mensajeria
def contador_no_leidos(request):
    return JsonResponse(resumen_no_leidos(request.mensajeria_usuario))
