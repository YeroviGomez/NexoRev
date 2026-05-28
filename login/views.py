from django.shortcuts import redirect, render

from crear_cuenta.models import Usuario


def login_view(request):
    context = {}

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        if not email or not password:
            context['error_message'] = 'Ingresa correo y contraseña.'
            return render(request, 'login.html', context)

        allowed_domains = {
            'gmail.com','hotmail.com','outlook.com','live.com','yahoo.com','icloud.com',
            'protonmail.com','zoho.com','aol.com','gmx.com','yandex.com','mail.com',
            'fastmail.com','tutanota.com'
        }

        if '@' not in email or not email.endswith('.com'):
            context['error_message'] = 'Ingrese un correo válido.'
            return render(request, 'login.html', context)

        domain = email.split('@')[-1]
        if domain not in allowed_domains:
            context['error_message'] = 'Ingrese un correo válido.'
            return render(request, 'login.html', context)

        try:
            usuario = Usuario.objects.get(email=email)
        except Usuario.DoesNotExist:
            usuario = None

        if usuario is None or not usuario.check_password(password):
            context['error_message'] = 'Correo o contraseña incorrectos.'
        else:
            request.session['current_user'] = usuario.email
            request.session['show_tutorial'] = True
            return redirect('principal')

    return render(request, 'login.html', context)


def logout_view(request):
    request.session.flush()
    return redirect('login')
