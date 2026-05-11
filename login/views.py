from django.shortcuts import redirect, render

from crear_cuenta.models import Usuario


def login_view(request):
    context = {}

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        if not email or not password:
            context['error_message'] = 'Ingresa correo y contraseña.'
        else:
            try:
                usuario = Usuario.objects.get(email=email)
            except Usuario.DoesNotExist:
                usuario = None

            if usuario is None or not usuario.check_password(password):
                context['error_message'] = 'Correo o contraseña incorrectos.'
            else:
                request.session['current_user'] = usuario.email
                return redirect('principal')

    return render(request, 'login.html', context)


def logout_view(request):
    request.session.flush()
    return redirect('login')
