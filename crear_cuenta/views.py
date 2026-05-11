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
            context['error_message'] = 'Ingresa un correo electrónico válido.'
        elif len(password) < 8:
            context['error_message'] = 'La contraseña debe tener al menos 8 caracteres.'
        elif password != confirm_password:
            context['error_message'] = 'Las contraseñas no coinciden.'
        else:
            if Usuario.objects.filter(email=email).exists():
                context['error_message'] = 'Ya existe una cuenta con ese correo.'
            else:
                usuario = Usuario(email=email, nombre=nombre)
                usuario.set_password(password)
                usuario.save()
                context['success_message'] = 'Cuenta creada correctamente. Ahora inicia sesión.'
                return render(request, 'crear_cuenta.html', context)

    return render(request, 'crear_cuenta.html', context)
