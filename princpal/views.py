from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.utils import timezone
from functools import wraps
from pathlib import Path
import random
import re
from urllib.parse import parse_qs, urlparse
from .forms import DiagnosticoForm, FotoPerfilForm
from .models import Diagnostico, VideoView

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
    videos.extend(load_external_videos())
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
    videos = load_external_videos()
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
    videos = load_external_videos()
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
    videos = load_external_videos()
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
    videos = load_external_videos()
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
    videos = load_external_videos()
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
