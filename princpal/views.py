from django.contrib import messages
from django.http import Http404, HttpResponseForbidden, JsonResponse, StreamingHttpResponse
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from django.urls import reverse
from functools import wraps
from pathlib import Path
import random
import re
import mimetypes
import logging
import os
import json
import shutil
import subprocess
from urllib.parse import parse_qs, urlparse
from .forms import DiagnosticoForm, FotoPerfilForm, ProfileUpdateForm, RescheduleSessionForm, VideoUploadForm
from .models import Diagnostico, Paciente, Sesion, Video, VideoView

from crear_cuenta.models import Usuario

VIDEO_PAGE_SIZE = 8

logger = logging.getLogger(__name__)


def get_page_number(value):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return 1


def build_video_history_page(queryset, videos_by_id, date_field, page_number):
    page_number = get_page_number(page_number)
    total = queryset.count()
    page_count = max((total + VIDEO_PAGE_SIZE - 1) // VIDEO_PAGE_SIZE, 1)
    page_number = min(page_number, page_count)
    start = (page_number - 1) * VIDEO_PAGE_SIZE
    items = []

    for item in queryset[start:start + VIDEO_PAGE_SIZE]:
        video_index, video = videos_by_id[item['video_id']]
        items.append({
            'title': video['title'],
            'video_id': item['video_id'],
            'preview_image': video.get('preview_image', ''),
            date_field: item['last_activity'],
            'catalog_index': video_index,
        })

    return {
        'items': items,
        'count': total,
        'page': page_number,
        'has_previous': page_number > 1,
        'has_next': start + VIDEO_PAGE_SIZE < total,
    }


def load_external_videos():
    catalog_path = Path(__file__).resolve().parent / 'data' / 'videos.txt'
    videos = []
    if not catalog_path.exists():
        return videos

    lines = [line.strip() for line in catalog_path.read_text(encoding='utf-8').splitlines()]
    blocks = []
    current_block = []
    for line in lines:
        if line.startswith('##') and current_block:
            blocks.append(current_block)
            current_block = []
        if line and (line.startswith('##') or not line.startswith('#')):
            current_block.append(line)
    if current_block:
        blocks.append(current_block)

    for block in blocks:
        if block[0].startswith('##'):
            if len(block) < 5:
                continue
            title = re.sub(r'^##\s*', '', block[0]).strip()
            description, level, category, video_url = [value.strip() for value in block[1:5]]
        else:
            video_url = block[0]
            title = 'Video de rehabilitación'
            description = 'Video agregado desde el catálogo de enlaces.'
            level = 'Recomendado'
            category = 'General'

        video_id = get_youtube_video_id(video_url)
        if not video_id:
            continue

        difficulty = {
            'principiante': 'easy',
            'bajo': 'easy',
            'intermedio': 'medium',
            'medio': 'medium',
            'avanzado': 'hard',
            'alto': 'hard',
        }.get(level.lower(), 'easy')
        videos.append({
            'catalog_index': len(videos),
            'title': title,
            'description': description,
            'duration': '',
            'difficulty': difficulty,
            'level': level,
            'category': category,
            'url': normalize_youtube_url(video_url),
            'embed_url': f'https://www.youtube.com/embed/{video_id}?rel=0',
            'video_id': video_id,
            'preview_image': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg' if video_id else '',
        })
    return videos


def load_videos():
    videos = load_external_videos()
    videos.extend({
        'title': video.title,
        'description': video.description or 'Video local de rehabilitación.',
        'duration': '',
        'difficulty': {'principiante': 'easy', 'intermedio': 'medium', 'avanzado': 'hard'}.get(video.level.lower(), 'easy'),
        'level': video.level,
        'category': video.category,
        'url': video.file.url,
        'video_url': video.file.url,
        'hls_url': f'{settings.MEDIA_URL}{video.hls_manifest}' if video.hls_manifest else '',
        'quality_sources': json.dumps({
            0: video.file.url,
            360: f'{settings.MEDIA_URL}hls/{video.pk}/quality_360.mp4',
            480: f'{settings.MEDIA_URL}hls/{video.pk}/quality_480.mp4',
            720: f'{settings.MEDIA_URL}hls/{video.pk}/quality_720.mp4',
        }),
        'embed_url': '',
        'video_id': f'local-{video.pk}',
        'preview_image': video.thumbnail.url if video.thumbnail else '',
        'is_local': True,
    } for video in Video.objects.all())
    for index, video in enumerate(videos):
        video['catalog_index'] = index
    return videos


def recent_video_history(videos, email, page_number=1):
    videos_by_id = {
        video['video_id']: (index, video)
        for index, video in enumerate(videos)
    }
    recent_views = VideoView.objects.filter(
        user_email=email,
        video_id__in=videos_by_id,
    ).values('video_id').annotate(
        last_activity=Max('viewed_at'),
    ).order_by('-last_activity', 'video_id')

    return build_video_history_page(
        recent_views,
        videos_by_id,
        'viewed_at',
        page_number,
    )


def completed_video_history(videos_by_id, email, page_number=1):
    completed_views = VideoView.objects.filter(
        user_email=email,
        completed=True,
        completed_at__isnull=False,
        video_id__in=videos_by_id,
    ).values('video_id').annotate(
        last_activity=Max('completed_at'),
    ).order_by('-last_activity', 'video_id')

    return build_video_history_page(
        completed_views,
        videos_by_id,
        'completed_at',
        page_number,
    )


def normalize_youtube_url(url):
    """Devuelve una URL HTTPS de YouTube a partir de sus formatos habituales."""
    video_id = get_youtube_video_id(url)
    return f'https://www.youtube.com/watch?v={video_id}' if video_id else ''


def get_youtube_video_id(url):
    """Extrae y valida el ID desde youtube.com, youtu.be, shorts o embed."""
    value = (url or '').strip()
    if value.startswith('://'):
        value = f'https{value}'
    elif not value.startswith(('http://', 'https://')):
        value = f'https://{value}'

    parsed_url = urlparse(value)
    hostname = parsed_url.netloc.lower().split(':', 1)[0]
    if hostname not in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be'}:
        return ''

    if hostname.endswith('youtu.be'):
        candidate = parsed_url.path.strip('/').split('/', 1)[0]
    elif parsed_url.path.startswith('/watch'):
        candidate = parse_qs(parsed_url.query).get('v', [''])[0]
    elif parsed_url.path.startswith(('/shorts/', '/embed/', '/live/')):
        candidate = parsed_url.path.split('/')[2]
    else:
        candidate = ''

    return candidate if re.fullmatch(r'[A-Za-z0-9_-]{6,}', candidate) else ''


def require_login(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get('current_user'):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@require_login
def media_file_view(request, path):
    media_root = Path(settings.MEDIA_ROOT).resolve()
    file_path = (media_root / path).resolve()
    if media_root not in file_path.parents or not file_path.is_file():
        raise Http404

    file_size = file_path.stat().st_size
    content_type = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
    range_header = request.headers.get('Range', '')
    if not range_header.startswith('bytes='):
        response = StreamingHttpResponse(_stream_file(file_path, 0, file_size), content_type=content_type)
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
        return response

    try:
        start_text, end_text = range_header[6:].split('-', 1)
        start = int(start_text) if start_text else max(file_size - int(end_text), 0)
        end = int(end_text) if end_text else file_size - 1
        if start < 0 or start > end or end >= file_size:
            raise ValueError
    except (TypeError, ValueError):
        response = StreamingHttpResponse(status=416)
        response['Content-Range'] = f'bytes */{file_size}'
        return response

    content_length = end - start + 1
    response = StreamingHttpResponse(_stream_file(file_path, start, content_length), status=206, content_type=content_type)
    response['Content-Length'] = str(content_length)
    response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    response['Accept-Ranges'] = 'bytes'
    return response


def _stream_file(file_path, start, length):
    with file_path.open('rb') as video_file:
        video_file.seek(start)
        remaining = length
        while remaining:
            chunk = video_file.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def generate_hls(video):
    """Genera tres calidades HLS; devuelve la ruta relativa del manifiesto."""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg and os.name == 'nt':
        winget_root = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet' / 'Packages'
        matches = list(winget_root.glob('Gyan.FFmpeg.Shared_*/*/bin/ffmpeg.exe'))
        ffmpeg = str(matches[0]) if matches else ''
    if not ffmpeg or not video.file:
        return ''

    output_dir = Path(settings.MEDIA_ROOT) / 'hls' / str(video.pk)
    output_dir.mkdir(parents=True, exist_ok=True)
    for quality in ('360p', '480p', '720p'):
        (output_dir / quality).mkdir(exist_ok=True)

    source_path = str(Path(video.file.path))
    has_audio = subprocess.run(
        [ffmpeg, '-i', source_path],
        capture_output=True, text=True,
    ).stderr.find('Audio:') >= 0
    for height in (360, 480, 720):
        quality_command = [
            ffmpeg, '-y', '-i', source_path,
            '-vf', f'scale=-2:{height}', '-c:v', 'libx264', '-preset', 'veryfast',
            '-profile:v', 'main', '-pix_fmt', 'yuv420p', '-b:v',
            {360: '800k', 480: '1500k', 720: '3000k'}[height],
        ]
        if has_audio:
            quality_command += ['-c:a', 'aac', '-profile:a', 'aac_low', '-ar', '44100', '-ac', '2', '-b:a', '128k']
        else:
            quality_command += ['-an']
        quality_command += ['-movflags', '+faststart', str(output_dir / f'quality_{height}.mp4')]
        try:
            subprocess.run(quality_command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError):
            for generated_height in (360, 480, 720):
                (output_dir / f'quality_{generated_height}.mp4').unlink(missing_ok=True)
            break

    output_pattern = str(output_dir / '%v' / 'segment_%03d.ts').replace('\\', '/')
    playlist_pattern = str(output_dir / '%v' / 'playlist.m3u8').replace('\\', '/')
    command = [
        ffmpeg, '-y', '-i', str(Path(video.file.path)),
        '-filter_complex',
        '[0:v]split=3[v360][v480][v720];'
        '[v360]scale=-2:360[v360out];'
        '[v480]scale=-2:480[v480out];'
        '[v720]scale=-2:720[v720out]',
        '-c:v', 'libx264', '-preset', 'veryfast', '-profile:v', 'main',
        '-b:v:0', '800k', '-maxrate:v:0', '856k', '-bufsize:v:0', '1200k',
        '-b:v:1', '1500k', '-maxrate:v:1', '1605k', '-bufsize:v:1', '2250k',
        '-b:v:2', '3000k', '-maxrate:v:2', '3210k', '-bufsize:v:2', '4500k',
        '-f', 'hls', '-hls_time', '6', '-hls_playlist_type', 'vod',
        '-hls_segment_filename', output_pattern,
        '-master_pl_name', 'master.m3u8',
        playlist_pattern,
    ]
    video_maps = [
        '-map', '[v360out]', '-map', '[v480out]', '-map', '[v720out]',
    ]
    if has_audio:
        video_maps = [
            '-map', '[v360out]', '-map', '0:a:0',
            '-map', '[v480out]', '-map', '0:a:0',
            '-map', '[v720out]', '-map', '0:a:0',
        ]
        audio_options = ['-c:a', 'aac', '-profile:a', 'aac_low', '-b:a', '128k', '-ar', '44100', '-ac', '2', '-var_stream_map', 'v:0,a:0 v:1,a:1 v:2,a:2']
    else:
        audio_options = ['-var_stream_map', 'v:0 v:1 v:2']
    command[command.index('-c:v'):command.index('-f')] = video_maps + [
        '-c:v', 'libx264', '-preset', 'veryfast', '-profile:v', 'main',
        '-b:v:0', '800k', '-maxrate:v:0', '856k', '-bufsize:v:0', '1200k',
        '-b:v:1', '1500k', '-maxrate:v:1', '1605k', '-bufsize:v:1', '2250k',
        '-b:v:2', '3000k', '-maxrate:v:2', '3210k', '-bufsize:v:2', '4500k',
    ] + audio_options
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        for playlist in (output_dir / 'master.m3u8',):
            playlist.unlink(missing_ok=True)
        for quality_dir in ('0', '1', '2', '360p', '480p', '720p'):
            shutil.rmtree(output_dir / quality_dir, ignore_errors=True)
        return ''
    return f'hls/{video.pk}/master.m3u8'


@require_login
@cache_control(no_cache=True, no_store=True, must_revalidate=True, max_age=0)
@ensure_csrf_cookie
def principal_view(request):
    show_security_tips = request.session.pop('show_security_tips', False)
    show_initial_guide = request.session.pop('show_initial_guide', False)
    current_user_email = request.session.get('current_user', '')
    usuario = Usuario.objects.filter(email=current_user_email, is_active=True).first()
    if not usuario:
        return redirect('login')

    paciente = None
    doctor_patients = []
    available_patients = []
    patient_progress_series = []
    calendar_sessions = []
    request.session.pop('diagnostico_id', None)
    diagnostico = Diagnostico.objects.filter(usuario=usuario).first() if usuario.is_paciente else None
    active_view = 'inicio'

    form = DiagnosticoForm(request.POST or None, instance=diagnostico)

    if request.method == "POST":
        if not usuario.is_paciente:
            return HttpResponseForbidden('Solo los pacientes pueden enviar este formulario.')

        if form.is_valid():
            diagnostico_guardado = form.save(commit=False)
            diagnostico_guardado.usuario = usuario
            diagnostico_guardado.save()
            if diagnostico:
                messages.success(request, "Formulario actualizado correctamente.")
            else:
                messages.success(request, "Formulario enviado correctamente.")
            return redirect("/principal/#diagnostico")
        messages.error(request, "Por favor, complete todos los campos obligatorios.")
        active_view = 'diagnostico'

    request.session['current_user_role'] = usuario.role
    paciente = Paciente.objects.filter(usuario=usuario).select_related('doctor').first()
    if usuario.is_doctor:
        doctor_patients = list(Paciente.objects.filter(doctor=usuario).select_related('usuario').order_by('-avance'))
        available_patients = Paciente.objects.filter(
            doctor__isnull=True,
        ).select_related('usuario').order_by('nombre')
    if usuario.is_paciente and paciente is None:
        paciente = Paciente.objects.filter(email=current_user_email, usuario__isnull=True).first()
        if paciente:
            paciente.usuario = usuario
            paciente.save(update_fields=['usuario'])
        else:
            paciente = Paciente.objects.create(
                email=current_user_email,
                nombre=usuario.nombre,
                usuario=usuario,
                doctor=None,
                avance=0,
                estado=Paciente.ESTADO_INICIAL,
            )
    if paciente:
        patient_progress_series = paciente.get_progress_series()
        if usuario.is_paciente:
            for sesion in Sesion.objects.filter(paciente=paciente, activo=True).order_by('fecha'):
                fecha_local = timezone.localtime(sesion.fecha)
                calendar_sessions.append({
                    'date': fecha_local.date().isoformat(),
                    'time': fecha_local.strftime('%H:%M'),
                    'objective': sesion.objetivo,
                })

    videos = []
    categories = ['Todas', 'Rodilla', 'Hombro', 'Espalda', 'Cuello', 'Tobillo', 'Cadera']
    videos.extend(load_videos())
    categories = ['Todas'] + list(dict.fromkeys(video['category'] for video in videos))
    page_size = VIDEO_PAGE_SIZE
    videos_page = videos[:page_size]
    videos_by_id = {video['video_id']: (index, video) for index, video in enumerate(videos)}
    recent_history = recent_video_history(
        videos,
        current_user_email,
        request.GET.get('viewed_page', 1),
    )
    completed_history = completed_video_history(
        videos_by_id,
        current_user_email,
        request.GET.get('completed_page', 1),
    )
    completed_event_count = VideoView.objects.filter(
        user_email=current_user_email,
        completed=True,
        completed_at__isnull=False,
    ).count()

    return render(request, 'principal.html', {
        'show_security_tips': show_security_tips,
        'show_initial_guide': show_initial_guide,
        'usuario': usuario,
        'paciente': paciente,
        'doctor_patients': doctor_patients,
        'available_patients': available_patients,
        'patient_progress_series': patient_progress_series,
        'calendar_sessions': calendar_sessions,
        'current_user_email': current_user_email,
        'videos': videos_page,
        'videos_total': len(videos),
        'videos_has_next': len(videos) > page_size,
        'videos_next_page': 2,
        'categories': categories,
        'form': form,
        'is_diagnostic_update': diagnostico is not None,
        'active_view': active_view,
        'completed_history': completed_history['items'],
        'completed_history_pagination': completed_history,
        'completed_event_count': completed_event_count,
        'recent_videos': recent_history['items'],
        'recent_history_pagination': recent_history,
    })


@require_login
@require_POST
def update_appearance_preference(request):
    usuario = Usuario.objects.filter(email=request.session.get('current_user')).first()
    if not usuario:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado.'}, status=404)

    try:
        data = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'La solicitud no contiene datos válidos.'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'success': False, 'error': 'La solicitud no contiene datos válidos.'}, status=400)

    preference = data.get('preference')
    value = data.get('value')
    if preference == 'modo_oscuro' and isinstance(value, bool):
        field_name = 'modo_oscuro'
    elif preference == 'tamano_letra' and isinstance(value, str) and value in {'normal', 'large', 'xlarge'}:
        field_name = 'tamano_letra'
    elif preference == 'desactivar_animaciones' and isinstance(value, bool):
        field_name = 'desactivar_animaciones'
    else:
        return JsonResponse({'success': False, 'error': 'La preferencia no es válida.'}, status=400)

    setattr(usuario, field_name, value)
    usuario.save(update_fields=[field_name])
    return JsonResponse({'success': True, 'preference': field_name, 'value': value})


@require_login
@require_POST
def add_paciente_view(request):
    current_user_email = request.session.get('current_user', '')
    usuario = get_object_or_404(Usuario, email=current_user_email)
    if not usuario.is_doctor:
        messages.error(request, 'Solo un especialista puede añadir pacientes.')
        return redirect('principal')

    existing_patient_id = (request.POST.get('existing_patient_id') or '').strip()
    if existing_patient_id:
        try:
            paciente = Paciente.objects.select_related('usuario').get(
                pk=int(existing_patient_id),
                doctor__isnull=True,
            )
        except (Paciente.DoesNotExist, ValueError):
            messages.error(request, 'El paciente seleccionado no está disponible para asignación.')
            return redirect('principal')

        paciente.doctor = usuario
        paciente.save(update_fields=['doctor'])
        messages.success(request, f'Paciente {paciente.nombre} asignado correctamente.')
        return redirect('principal')

    nombre = (request.POST.get('nombre') or '').strip()
    email = (request.POST.get('email') or '').strip()
    edad = (request.POST.get('edad') or '').strip()
    zona_afectada = (request.POST.get('zona_afectada') or '').strip()
    avance = (request.POST.get('avance') or '0').strip()

    if not nombre or not email:
        messages.error(request, 'Completa al menos el nombre y el correo del paciente.')
        return redirect('principal')

    try:
        paciente, created = Paciente.objects.get_or_create(
            email=email,
            defaults={
                'nombre': nombre,
                'doctor': usuario,
                'usuario': None,
                'edad': int(edad) if edad else 0,
                'zona_afectada': zona_afectada,
                'avance': int(avance) if avance else 0,
                'estado': Paciente.ESTADO_INICIAL,
            },
        )
    except ValueError:
        messages.error(request, 'La edad y el avance deben ser valores numéricos válidos.')
        return redirect('principal')

    paciente.nombre = nombre
    paciente.doctor = usuario
    paciente.email = email
    if edad:
        paciente.edad = int(edad)
    if zona_afectada:
        paciente.zona_afectada = zona_afectada
    if avance:
        paciente.avance = min(100, max(0, int(avance)))
    paciente.recalcular_estado()
    paciente.save(update_fields=['nombre', 'doctor', 'email', 'edad', 'zona_afectada', 'avance', 'estado'])

    if created:
        messages.success(request, f'Paciente {nombre} añadido correctamente.')
    else:
        messages.success(request, f'Paciente {nombre} actualizado correctamente.')
    return redirect('principal')


@require_login
def doctor_patients_api(request, doctor_id):
    doctor = get_object_or_404(Usuario, pk=doctor_id, role='doctor')
    current_doctor = get_object_or_404(
        Usuario,
        email=request.session.get('current_user', ''),
        role='doctor',
    )
    if current_doctor.pk != doctor.pk:
        return JsonResponse({'error': 'No tienes permiso para consultar estos pacientes.'}, status=403)
    if request.method == 'POST':
        nombre = (request.POST.get('nombre') or '').strip()
        email = (request.POST.get('email') or '').strip()
        if not nombre or not email:
            return JsonResponse({'ok': False, 'error': 'Faltan nombre o correo.'}, status=400)
        edad = request.POST.get('edad') or 0
        zona_afectada = request.POST.get('zona_afectada') or ''
        avance = request.POST.get('avance') or 0
        try:
            paciente, created = Paciente.objects.get_or_create(
                email=email,
                defaults={
                    'nombre': nombre,
                    'doctor': doctor,
                    'edad': int(edad),
                    'zona_afectada': zona_afectada,
                    'avance': min(100, max(0, int(avance))),
                },
            )
        except ValueError:
            return JsonResponse({'ok': False, 'error': 'Edad o avance inválidos.'}, status=400)
        paciente.nombre = nombre
        paciente.doctor = doctor
        paciente.edad = int(edad)
        paciente.zona_afectada = zona_afectada
        paciente.avance = min(100, max(0, int(avance)))
        paciente.recalcular_estado()
        paciente.save()
        return JsonResponse({'ok': True, 'created': created, 'paciente': paciente_detail_payload(paciente)})

    pacientes = Paciente.objects.filter(doctor=doctor).select_related('usuario').order_by('-avance', 'nombre')
    return JsonResponse({
        'doctor_id': doctor.pk,
        'items': [paciente_detail_payload(paciente) for paciente in pacientes],
    })


@require_login
def paciente_detail_api(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    current_doctor = get_object_or_404(
        Usuario,
        email=request.session.get('current_user', ''),
        role='doctor',
    )
    if paciente.doctor_id != current_doctor.pk:
        return JsonResponse({'error': 'No tienes permiso para consultar este expediente.'}, status=403)
    return JsonResponse({'paciente': paciente_detail_payload(paciente)})


@require_login
@require_POST
def reschedule_session_view(request, paciente_id, sesion_id):
    doctor = Usuario.objects.filter(
        email=request.session.get('current_user', ''),
        role=Usuario.ROLE_DOCTOR,
        is_active=True,
    ).first()
    if not doctor:
        return JsonResponse({'success': False, 'error': 'Solo el especialista asignado puede reagendar esta cita.'}, status=403)

    sesion = get_object_or_404(
        Sesion,
        pk=sesion_id,
        paciente_id=paciente_id,
        paciente__doctor=doctor,
    )
    if not sesion.activo:
        return JsonResponse({'success': False, 'error': 'Esta cita ya no está activa.'}, status=409)

    form = RescheduleSessionForm(request.POST)
    if not form.is_valid():
        return JsonResponse({
            'success': False,
            'error': form.errors.get('fecha', ['Ingresa una fecha válida.'])[0],
        }, status=400)

    sesion.fecha = form.cleaned_data['fecha']
    sesion.save(update_fields=['fecha'])
    fecha_local = timezone.localtime(sesion.fecha)
    return JsonResponse({
        'success': True,
        'fecha': fecha_local.isoformat(),
        'fecha_local': fecha_local.strftime('%Y-%m-%dT%H:%M'),
        'fecha_display': fecha_local.strftime('%d/%m/%Y %H:%M'),
    })


def paciente_detail_payload(paciente):
    sesiones = []
    for sesion in paciente.sesiones.all():
        fecha_local = timezone.localtime(sesion.fecha)
        sesiones.append({
            'id': sesion.pk,
            'fecha': sesion.fecha.isoformat(),
            'fecha_local': fecha_local.strftime('%Y-%m-%dT%H:%M'),
            'fecha_display': fecha_local.strftime('%d/%m/%Y %H:%M'),
            'objetivo': sesion.objetivo,
            'avance': sesion.avance,
            'activo': sesion.activo,
        })

    return {
        'id': paciente.pk,
        'nombre': paciente.nombre,
        'email': paciente.email,
        'edad': paciente.edad,
        'zona_afectada': paciente.zona_afectada,
        'avance': paciente.avance,
        'estado': paciente.estado,
        'estado_display': paciente.get_estado_display(),
        'color_estado': paciente.color_estado,
        'doctor_id': paciente.doctor_id,
        'historial_avance': paciente.get_progress_series(),
        'sesiones': sesiones,
    }


@require_login
@cache_control(no_cache=True, no_store=True, must_revalidate=True, max_age=0)
def diagnostico_view(request, pk=None):
    usuario = Usuario.objects.filter(
        email=request.session.get('current_user'),
        is_active=True,
    ).first()
    if not usuario or not usuario.is_paciente:
        return HttpResponseForbidden('Solo los pacientes pueden enviar este formulario.')

    if pk:
        diagnostico = get_object_or_404(Diagnostico, pk=pk, usuario=usuario)
    else:
        diagnostico = Diagnostico.objects.filter(usuario=usuario).first()

    form = DiagnosticoForm(request.POST or None, instance=diagnostico)
    if request.method == "POST":
        if form.is_valid():
            diagnostico_guardado = form.save(commit=False)
            diagnostico_guardado.usuario = usuario
            diagnostico_guardado.save()
            messages.success(request, "Formulario enviado correctamente.")
            return redirect("/principal/#diagnostico")
        messages.error(request, "Por favor, complete todos los campos obligatorios.")

    return render(request, "principal/diagnostico.html", {"form": form})


@require_login
def videos_page_view(request):
    videos = load_videos()
    page_number = max(int(request.GET.get('page', 1)), 1)
    start = (page_number - 1) * VIDEO_PAGE_SIZE
    end = start + VIDEO_PAGE_SIZE
    return render(request, 'principal/partials/video_results.html', {
        'videos': videos[start:end],
        'videos_has_next': end < len(videos),
        'videos_next_page': page_number + 1,
    })


@require_login
def history_view(request):
    videos = load_videos()
    videos_by_id = {video['video_id']: (index, video) for index, video in enumerate(videos)}
    email = request.session.get('current_user', '')
    completed_events = VideoView.objects.filter(
        user_email=email,
        completed=True,
        completed_at__isnull=False,
    )
    completed_history = completed_video_history(
        videos_by_id,
        email,
        request.GET.get('completed_page', 1),
    )
    recent_history = recent_video_history(
        videos,
        email,
        request.GET.get('viewed_page', 1),
    )
    completed_video_ids = list(completed_events.values_list('video_id', flat=True).distinct())

    def serialize_history_page(history_page, date_field):
        serialized_items = [
            {
                **item,
                date_field: timezone.localtime(item[date_field]).strftime('%d/%m/%Y %H:%M'),
                'replay_url': reverse('video_detail', args=[item['catalog_index']]),
            }
            for item in history_page['items']
        ]
        return {
            'items': serialized_items,
            'count': history_page['count'],
            'page': history_page['page'],
            'has_previous': history_page['has_previous'],
            'has_next': history_page['has_next'],
        }

    serialized_completed = serialize_history_page(completed_history, 'completed_at')
    serialized_recent = serialize_history_page(recent_history, 'viewed_at')

    return JsonResponse({
        'count': completed_events.count(),
        'completed_count': completed_history['count'],
        'completed_video_ids': completed_video_ids,
        'items': serialized_completed['items'],
        'completed_videos': serialized_completed,
        'recent_videos': serialized_recent,
    })


@require_login
def surprise_video_view(request):
    videos = load_videos()
    if not videos:
        return render(request, 'principal/partials/featured_video.html', {'video': None})

    email = request.session.get('current_user', '')
    category_counts = VideoView.objects.filter(user_email=email).values('category').annotate(
        total=Count('id')
    ).order_by('-total')
    preferred_category = category_counts.first()['category'] if category_counts else None
    candidates = [video for video in videos if video['category'].casefold() == preferred_category.casefold()] if preferred_category else videos
    shown_ids = request.session.get('surprise_video_ids', [])
    unseen_candidates = [video for video in candidates if video['video_id'] not in shown_ids]
    if not unseen_candidates:
        shown_ids = []
        unseen_candidates = candidates
    video = random.choice(unseen_candidates or videos)
    request.session['surprise_video_ids'] = [*shown_ids, video['video_id']]
    return render(request, 'principal/partials/featured_video.html', {'video': video})


@require_login
@cache_control(no_cache=True, no_store=True, must_revalidate=True, max_age=0)
def video_detail_view(request, video_index):
    videos = load_videos()
    if video_index < 0 or video_index >= len(videos):
        return redirect('principal')

    video = videos[video_index]
    usuario = Usuario.objects.filter(email=request.session.get('current_user', '')).first()
    completed_today = VideoView.objects.filter(
        user_email=request.session.get('current_user', ''), video_id=video['video_id'],
        completed=True, completed_at__date=timezone.localdate(),
    ).exists()
    VideoView.objects.create(
        user_email=request.session.get('current_user', ''),
        video_id=video['video_id'],
        category=video['category'],
    )
    recommendations = []
    recommendation_ids = set()
    for index, item in enumerate(videos):
        if index == video_index or item['category'].casefold() != video['category'].casefold():
            continue
        if item['video_id'] in recommendation_ids:
            continue
        recommendation_ids.add(item['video_id'])
        recommendations.append({**item, 'catalog_index': index})
    return render(request, 'principal/video_detail.html', {
        'video': video,
        'recommendations': recommendations,
        'current_user_email': request.session.get('current_user', ''),
        'usuario': usuario,
        'completed_today': completed_today,
    })


@require_login
@require_POST
def complete_video_view(request, video_index):
    videos = load_videos()
    if video_index < 0 or video_index >= len(videos):
        return JsonResponse({'success': False, 'error': 'Video no encontrado.'}, status=404)

    video = videos[video_index]
    email = request.session.get('current_user', '')
    completed_today = VideoView.objects.filter(
        user_email=email, video_id=video['video_id'], completed=True,
        completed_at__date=timezone.localdate(),
    ).order_by('-completed_at').first()
    if completed_today:
        completed_today.completed = False
        completed_today.completed_at = None
        completed_today.save(update_fields=['completed', 'completed_at'])
        return JsonResponse({'success': True, 'completed': False, 'title': video['title']})

    viewed_video = VideoView.objects.filter(
        user_email=email, video_id=video['video_id']
    ).order_by('-viewed_at').first()
    if viewed_video:
        viewed_video.completed = True
        viewed_video.completed_at = timezone.now()
        viewed_video.save(update_fields=['completed', 'completed_at'])
        completed_at = viewed_video.completed_at
    else:
        completed_at = timezone.now()
        VideoView.objects.create(
            user_email=email, video_id=video['video_id'],
            category=video['category'], completed=True, completed_at=completed_at,
        )

    usuario = Usuario.objects.filter(email=email).first()
    paciente = Paciente.objects.filter(usuario=usuario).first() if usuario else None
    if paciente:
        paciente.registrar_avance(min(100, paciente.avance + 10))

    return JsonResponse({'success': True, 'completed': True, 'title': video['title'], 'completed_at': completed_at.isoformat(), 'message': random.choice([
        '¡Gran trabajo hoy!',
        '¡Estás más cerca de tu recuperación!',
        '¡Cada rutina cuenta, sigue así!',
        '¡Tu constancia está dando frutos!',
    ]), 'progress': getattr(paciente, 'avance', 0)})


@require_login
@require_POST
def update_profile_view(request):
    usuario = Usuario.objects.filter(email=request.session.get('current_user')).first()
    if not usuario:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado.'}, status=404)

    try:
        data = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'La solicitud no contiene datos válidos.'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'success': False, 'error': 'La solicitud no contiene datos válidos.'}, status=400)

    form = ProfileUpdateForm(data)
    if not form.is_valid():
        error = next(iter(form.errors.values()))[0]
        return JsonResponse({'success': False, 'error': error}, status=400)

    nombre = form.cleaned_data['nombre']
    email = form.cleaned_data['email']
    telefono = form.cleaned_data['telefono']
    if Usuario.objects.exclude(pk=usuario.pk).filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Ya existe una cuenta con ese correo.'}, status=400)

    correo_anterior = usuario.email
    paciente = Paciente.objects.filter(usuario=usuario).first()
    if paciente is None:
        paciente = Paciente.objects.filter(email=correo_anterior).first()
    if paciente and email != correo_anterior and Paciente.objects.exclude(pk=paciente.pk).filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Ese correo ya está asociado a otro paciente.'}, status=400)

    with transaction.atomic():
        usuario.nombre = nombre
        usuario.email = email
        usuario.telefono = telefono
        usuario.save(update_fields=['nombre', 'email', 'telefono'])

        if paciente:
            paciente.nombre = nombre
            paciente.email = email
            paciente.telefono = telefono
            paciente.save(update_fields=['nombre', 'email', 'telefono'])

        if email != correo_anterior:
            VideoView.objects.filter(user_email=correo_anterior).update(user_email=email)
            request.session['current_user'] = email

    return JsonResponse({'success': True, 'email': email})


@require_login
@require_POST
def change_password_view(request):
    usuario = Usuario.objects.filter(email=request.session.get('current_user')).first()
    if not usuario:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado.'}, status=404)

    try:
        data = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'La solicitud no contiene datos válidos.'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'success': False, 'error': 'La solicitud no contiene datos válidos.'}, status=400)

    current_password = data.get('currentPassword')
    new_password = data.get('newPassword')
    confirm_password = data.get('confirmPassword')
    if not all(isinstance(value, str) and value for value in (current_password, new_password, confirm_password)):
        return JsonResponse({'success': False, 'error': 'Completa todos los campos de contraseña.'}, status=400)
    if not usuario.check_password(current_password):
        return JsonResponse({'success': False, 'error': 'La contraseña actual es incorrecta.'}, status=400)
    if new_password != confirm_password:
        return JsonResponse({'success': False, 'error': 'Las nuevas contraseñas no coinciden.'}, status=400)
    if len(new_password) < 8:
        return JsonResponse({'success': False, 'error': 'La nueva contraseña debe tener al menos 8 caracteres.'}, status=400)
    if new_password == current_password:
        return JsonResponse({'success': False, 'error': 'La nueva contraseña debe ser distinta de la actual.'}, status=400)

    usuario.set_password(new_password)
    usuario.save(update_fields=['password'])
    return JsonResponse({'success': True})


@require_login
@require_POST
def upload_profile_photo(request):
    usuario = Usuario.objects.filter(email=request.session.get('current_user')).first()
    if not usuario:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado.'}, status=404)

    form = FotoPerfilForm(request.POST, request.FILES)
    if not form.is_valid():
        error = form.errors.get('foto', ['Selecciona una imagen válida.'])[0]
        return JsonResponse({'success': False, 'error': error}, status=400)

    foto_anterior = usuario.foto_perfil
    try:
        usuario.foto_perfil = form.cleaned_data['foto']
        usuario.save(update_fields=['foto_perfil'])
        foto_url = usuario.foto_perfil.url
        if foto_anterior and foto_anterior.name != usuario.foto_perfil.name:
            foto_anterior.delete(save=False)
    except Exception:
        logger.exception('No se pudo guardar la foto de perfil del usuario %s', usuario.pk)
        return JsonResponse(
            {'success': False, 'error': 'No se pudo guardar la foto. Inténtalo nuevamente.'},
            status=500,
        )

    return JsonResponse({'success': True, 'foto_url': foto_url})


@require_login
@require_POST
def reset_profile_photo(request):
    usuario = Usuario.objects.filter(email=request.session.get('current_user')).first()
    if not usuario:
        return JsonResponse({'success': False, 'error': 'Usuario no encontrado.'}, status=404)

    foto_anterior = usuario.foto_perfil
    try:
        usuario.foto_perfil = None
        usuario.save(update_fields=['foto_perfil'])
        if foto_anterior:
            foto_anterior.delete(save=False)
    except Exception:
        logger.exception('No se pudo restablecer la foto de perfil del usuario %s', usuario.pk)
        return JsonResponse(
            {'success': False, 'error': 'No se pudo restablecer la foto. Inténtalo nuevamente.'},
            status=500,
        )

    return JsonResponse({'success': True})


@require_login
@require_POST
def upload_video_view(request):
    form = VideoUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        error = form.errors.get('file', ['Revisa los datos del video.'])[0]
        return JsonResponse({'success': False, 'error': error}, status=400)
    video = form.save()
    hls_manifest = generate_hls(video)
    if hls_manifest:
        video.hls_manifest = hls_manifest
        video.save(update_fields=['hls_manifest'])
    return JsonResponse({
        'success': True,
        'video_id': video.pk,
        'adaptive_streaming': bool(hls_manifest),
    })
