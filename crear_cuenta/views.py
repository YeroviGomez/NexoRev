from django.shortcuts import redirect, render

from .models import Usuario


def crear_cuenta_view(request):
    context = {}

    if request.method == 'POST':
        nombre = request.POST.get('fullName', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirmPassword', '')

        if len(nombre) < 3:
            context['error_message'] = 'Ingresa tu nombre completo.'
        elif not email or '@' not in email:
            context['error_message'] = 'Ingrese un correo válido.'
        elif len(password) < 8:
            context['error_message'] = 'La contraseña debe tener al menos 8 caracteres.'
        elif password != confirm_password:
            context['error_message'] = 'Las contraseñas no coinciden.'
        else:
            if Usuario.objects.filter(email=email).exists():
                context['error_message'] = 'Ya existe una cuenta con ese correo.'
            else:
                allowed_domains = {
                    'gmail.com', 'hotmail.com', 'outlook.com', 'live.com', 'yahoo.com',
                    'icloud.com', 'protonmail.com', 'zoho.com', 'aol.com', 'gmx.com',
                    'yandex.com', 'mail.com', 'fastmail.com', 'tutanota.com'
                }

                if '@' not in email or not email.endswith('.com'):
                    context['error_message'] = 'Ingrese un correo válido.'
                    return render(request, 'crear_cuenta.html', context)

                domain = email.split('@')[-1]
                if domain not in allowed_domains:
                    context['error_message'] = 'Ingrese un correo válido.'
                    return render(request, 'crear_cuenta.html', context)

                usuario = Usuario(email=email, nombre=nombre)
                usuario.set_password(password)
                usuario.save()
                return redirect('login')

    return render(request, 'crear_cuenta.html', context)
