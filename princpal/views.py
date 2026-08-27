from django.contrib import messages
from django.http import JsonResponse
from django.http import Http404, StreamingHttpResponse
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.utils import timezone
from functools import wraps
from pathlib import Path
import random
import re
import mimetypes
import os
import json
import shutil
import subprocess
from urllib.parse import parse_qs, urlparse
from .forms import DiagnosticoForm, FotoPerfilForm, VideoUploadForm
from .models import Diagnostico, Video, VideoView

from crear_cuenta.models import Usuario


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
def principal_view(request):
    show_tutorial = request.session.pop('show_tutorial', False)
    show_security_tips = request.session.pop('show_security_tips', False)
    current_user_email = request.session.get('current_user', '')
    usuario = None
    diagnostico_id = request.session.get('diagnostico_id')
    diagnostico = None
    active_view = 'inicio'

    if diagnostico_id:
        diagnostico = Diagnostico.objects.filter(pk=diagnostico_id).first()

    form = DiagnosticoForm(request.POST or None, instance=diagnostico)

    if request.method == "POST":
        if form.is_valid():
            diagnostico_guardado = form.save()
            request.session['diagnostico_id'] = diagnostico_guardado.pk
            if diagnostico:
                messages.success(request, "Diagnostico actualizado correctamente.")
            else:
                messages.success(request, "Diagnostico guardado exitosamente.")
            return redirect("/principal/#diagnostico")
        messages.error(request, "Por favor, complete todos los campos obligatorios.")
        active_view = 'diagnostico'

    if current_user_email:
        try:
            usuario = Usuario.objects.get(email=current_user_email)
        except Usuario.DoesNotExist:
            usuario = None

    videos = []
    categories = ['Todas', 'Rodilla', 'Hombro', 'Espalda', 'Cuello', 'Tobillo', 'Cadera']
    videos.extend(load_videos())
    categories = ['Todas'] + list(dict.fromkeys(video['category'] for video in videos))
    page_size = 6
    videos_page = videos[:page_size]
    completed_videos = VideoView.objects.filter(user_email=current_user_email, completed=True, completed_at__isnull=False).order_by('-completed_at')[:20]
    video_titles = {video['video_id']: video['title'] for video in videos}
    completed_history = [
        {'title': video_titles.get(item.video_id, 'Video de rehabilitación'), 'completed_at': item.completed_at}
        for item in completed_videos
    ]

    return render(request, 'principal.html', {
        'show_tutorial': show_tutorial,
        'show_security_tips': show_security_tips,
        'usuario': usuario,
        'current_user_email': current_user_email,
        'videos': videos_page,
        'videos_total': len(videos),
        'videos_has_next': len(videos) > page_size,
        'videos_next_page': 2,
        'categories': categories,
        'form': form,
        'is_diagnostic_update': diagnostico is not None,
        'active_view': active_view,
        'completed_history': completed_history,
    })

@require_login
@cache_control(no_cache=True, no_store=True, must_revalidate=True, max_age=0)
def diagnostico_view(request, pk=None):
    if pk:
        diagnostico = get_object_or_404(Diagnostico, pk=pk)
        form = DiagnosticoForm(request.POST or None, instance=diagnostico)
        if request.method == "POST":
            if form.is_valid():
                form.save()
                messages.success(request, "Diagnóstico actualizado correctamente.")
                return redirect("diagnostico")
    else:
        form = DiagnosticoForm(request.POST or None)
        if request.method == "POST":
            if form.is_valid():
                form.save()
                messages.success(request, "Diagnóstico guardado exitosamente.")
                return redirect("diagnostico")
            else:
                messages.error(request, "Por favor, complete todos los campos obligatorios.")

    return render(request, "principal/diagnostico.html", {"form": form})


@require_login
def videos_page_view(request):
    videos = load_videos()
    page_number = max(int(request.GET.get('page', 1)), 1)
    start = (page_number - 1) * 6
    end = start + 6
    return render(request, 'principal/partials/video_results.html', {
        'videos': videos[start:end],
        'videos_has_next': end < len(videos),
        'videos_next_page': page_number + 1,
    })


@require_login
def history_view(request):
    videos = load_videos()
    video_titles = {video['video_id']: video['title'] for video in videos}
    completed_videos = VideoView.objects.filter(
        user_email=request.session.get('current_user', ''),
        completed=True,
        completed_at__isnull=False,
    ).order_by('-completed_at')[:20]
    return JsonResponse({
        'count': completed_videos.count(),
        'items': [
            {
                'title': video_titles.get(item.video_id, 'Video de rehabilitación'),
                'video_id': item.video_id,
                'completed_at': item.completed_at.strftime('%d/%m/%Y %H:%M'),
            }
            for item in completed_videos
        ],
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

    return JsonResponse({'success': True, 'completed': True, 'title': video['title'], 'completed_at': completed_at.isoformat(), 'message': random.choice([
        '¡Gran trabajo hoy!',
        '¡Estás más cerca de tu recuperación!',
        '¡Cada rutina cuenta, sigue así!',
        '¡Tu constancia está dando frutos!',
    ])})


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
    usuario.foto_perfil = form.cleaned_data['foto']
    usuario.save(update_fields=['foto_perfil'])
    if foto_anterior and foto_anterior.name != usuario.foto_perfil.name:
        foto_anterior.delete(save=False)

    return JsonResponse({'success': True, 'foto_url': usuario.foto_perfil.url})


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
