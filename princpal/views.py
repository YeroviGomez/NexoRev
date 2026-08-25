from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_control
from functools import wraps
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .forms import DiagnosticoForm
from .models import Diagnostico

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
        if line.startswith('## ') and current_block:
            blocks.append(current_block)
            current_block = []
        if line and (line.startswith('## ') or not line.startswith('#')):
            current_block.append(line)
    if current_block:
        blocks.append(current_block)

    for block in blocks:
        if block[0].startswith('## '):
            if len(block) < 5:
                continue
            title = block[0][3:].strip()
            description, level, category, video_url = block[1:5]
        else:
            video_url = block[0]
            title = 'Video de rehabilitación'
            description = 'Video agregado desde el catálogo de enlaces.'
            level = 'Recomendado'
            category = 'General'

        parsed_url = urlparse(video_url)
        if parsed_url.scheme not in {'http', 'https'} or not parsed_url.netloc:
            continue

        video_id = ''
        if parsed_url.netloc.lower() in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
            video_id = parse_qs(parsed_url.query).get('v', [''])[0]
            if parsed_url.path.startswith('/shorts/'):
                video_id = parsed_url.path.split('/shorts/', 1)[1].split('/', 1)[0]
        elif parsed_url.netloc.lower() == 'youtu.be':
            video_id = parsed_url.path.strip('/').split('/', 1)[0]

        difficulty = {
            'principiante': 'easy',
            'intermedio': 'medium',
            'medio': 'medium',
            'avanzado': 'hard',
        }.get(level.lower(), 'easy')
        videos.append({
            'title': title,
            'description': description,
            'duration': '',
            'difficulty': difficulty,
            'level': level,
            'category': category,
            'url': video_url,
            'preview_image': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg' if video_id else '',
        })
    return videos


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

    return render(request, 'principal.html', {
        'show_tutorial': show_tutorial,
        'show_security_tips': show_security_tips,
        'usuario': usuario,
        'current_user_email': current_user_email,
        'videos': videos,
        'categories': categories,
        'form': form,
        'is_diagnostic_update': diagnostico is not None,
        'active_view': active_view,
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
