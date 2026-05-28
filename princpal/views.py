from django.shortcuts import render

from crear_cuenta.models import Usuario


def principal_view(request):
    show_tutorial = request.session.pop('show_tutorial', False)
    current_user_email = request.session.get('current_user', '')
    usuario = None

    if current_user_email:
        try:
            usuario = Usuario.objects.get(email=current_user_email)
        except Usuario.DoesNotExist:
            usuario = None

    return render(request, 'principal.html', {
        'show_tutorial': show_tutorial,
        'usuario': usuario,
        'current_user_email': current_user_email,
    })
