from django.shortcuts import redirect, render

from princpal.models import Paciente
from .models import Usuario


def _valid_email_domain(email):
    if not email or '@' not in email or not email.endswith('.com'):
        return False
    allowed_domains = {
        'gmail.com', 'hotmail.com', 'outlook.com', 'live.com', 'yahoo.com',
        'icloud.com', 'protonmail.com', 'zoho.com', 'aol.com', 'gmx.com',
        'yandex.com', 'mail.com', 'fastmail.com', 'tutanota.com'
    }
    domain = email.split('@')[-1].lower()
    return domain in allowed_domains


def _register_user(request, role):
    context = {'role': role}

    if request.method == 'POST':
        nombre = request.POST.get('fullName', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirmPassword', '')
        especialidad = request.POST.get('specialty', '').strip()
        colegiado = request.POST.get('licenseNumber', '').strip()

        if len(nombre) < 3:
            context['error_message'] = 'Ingresa tu nombre completo.'
        elif not _valid_email_domain(email):
            context['error_message'] = 'Ingrese un correo válido.'
        elif len(password) < 8:
            context['error_message'] = 'La contraseña debe tener al menos 8 caracteres.'
        elif password != confirm_password:
            context['error_message'] = 'Las contraseñas no coinciden.'
        elif role == 'doctor' and (not especialidad or not colegiado):
            context['error_message'] = 'Completa la especialidad y el número de colegiado.'
        else:
            if Usuario.objects.filter(email=email).exists():
                context['error_message'] = 'Ya existe una cuenta con ese correo.'
            else:
                usuario = Usuario(
                    email=email,
                    nombre=nombre,
                    role=role,
                    especialidad=especialidad,
                    colegiado=colegiado,
                    modo_oscuro=False,
                )
                usuario.set_password(password)
                usuario.save()

                if role == Usuario.ROLE_PACIENTE:
                    Paciente.objects.get_or_create(
                        email=email,
                        defaults={
                            'nombre': nombre,
                            'usuario': usuario,
                            'doctor': None,
                            'avance': 0,
                            'estado': Paciente.ESTADO_INICIAL,
                        },
                    )
                return redirect('login')

    return render(request, 'crear_cuenta.html', context)


def crear_cuenta_view(request):
    return _register_user(request, Usuario.ROLE_PACIENTE)


def crear_cuenta_paciente_view(request):
    return _register_user(request, Usuario.ROLE_PACIENTE)


def crear_cuenta_doctor_view(request):
    return _register_user(request, Usuario.ROLE_DOCTOR)
