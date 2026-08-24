from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_control
from functools import wraps
from .forms import DiagnosticoForm
from .models import Diagnostico

from crear_cuenta.models import Usuario


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

    videos = [
        {
            'title': 'Ejercicios para dolor de rodilla',
            'description': 'Rutina básica para fortalecer la rodilla y reducir el dolor',
            'duration': '10:45',
            'difficulty': 'easy',
            'level': 'Principiante',
            'category': 'Rodilla',
        },
        {
            'title': 'Rehabilitación de hombro',
            'description': 'Ejercicios de movilidad para recuperar el rango de movimiento del hombro',
            'duration': '15:30',
            'difficulty': 'medium',
            'level': 'Intermedio',
            'category': 'Hombro',
        },
        {
            'title': 'Fortalecimiento de espalda baja',
            'description': 'Rutina completa para fortalecer la zona lumbar y prevenir lesiones',
            'duration': '20:00',
            'difficulty': 'medium',
            'level': 'Intermedio',
            'category': 'Espalda',
        },
        {
            'title': 'Estiramiento de cuello y cervicales',
            'description': 'Ejercicios suaves para aliviar la tensión en cuello y cervicales',
            'duration': '8:15',
            'difficulty': 'easy',
            'level': 'Principiante',
            'category': 'Cuello',
        },
        {
            'title': 'Recuperación de tobillo',
            'description': 'Ejercicios progresivos para rehabilitar esguinces de tobillo',
            'duration': '12:30',
            'difficulty': 'easy',
            'level': 'Principiante',
            'category': 'Tobillo',
        },
        {
            'title': 'Movilidad de cadera',
            'description': 'Rutina avanzada para mejorar la flexibilidad y fuerza de la cadera',
            'duration': '18:45',
            'difficulty': 'hard',
            'level': 'Avanzado',
            'category': 'Cadera',
        },
    ]
    categories = ['Todas', 'Rodilla', 'Hombro', 'Espalda', 'Cuello', 'Tobillo', 'Cadera']

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
