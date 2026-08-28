from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_control
from datetime import timedelta
from crear_cuenta.models import Usuario
from .models import LoginAttempt, TwoFactorCode
import logging
import random
import string

logger = logging.getLogger('nexorev.auth')


def log_verification_code(label, email, code):
    message = f'[Nexo ReV] {label} para {email}: {code}'
    print(message, flush=True)
    logger.warning(message)


@cache_control(no_cache=True, no_store=True, must_revalidate=True, max_age=0)
def login_view(request):
    if request.session.get('current_user'):
        return redirect('principal')

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
            TwoFactorCode.objects.filter(email=usuario.email, is_used=False).update(is_used=True)
            verification = TwoFactorCode.objects.create(
                email=usuario.email,
                code=TwoFactorCode.generate_code(),
            )
            log_verification_code('Código 2FA', usuario.email, verification.code)
            request.session['pending_2fa_email'] = usuario.email
            request.session['pending_2fa_id'] = verification.pk
            request.session.set_expiry(600)
            try:
                send_mail(
                    'Código de acceso - Nexo ReV',
                    f'Hola {usuario.nombre}, tu código de acceso es {verification.code}. Es válido por 10 minutos.',
                    settings.DEFAULT_FROM_EMAIL,
                    [usuario.email],
                    fail_silently=False,
                )
            except Exception:
                request.session.flush()
                context['error_message'] = 'No se pudo enviar el código de acceso. Intenta nuevamente.'
            else:
                return redirect('verify_2fa')

    return render(request, 'login.html', context)


def verify_2fa_view(request):
    verification_id = request.session.get('pending_2fa_id')
    email = request.session.get('pending_2fa_email')
    if not verification_id or not email:
        return redirect('login')

    verification = TwoFactorCode.objects.filter(
        pk=verification_id, email=email, is_used=False
    ).first()
    context = {'email': email}
    if not verification or not verification.is_valid():
        request.session.flush()
        context['error_message'] = 'El código expiró. Inicia sesión nuevamente.'
        return render(request, 'login/verify_2fa.html', context)

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        if code != verification.code:
            verification.attempts += 1
            verification.save(update_fields=['attempts'])
            context['error_message'] = 'Código inválido. Verifica el correo e inténtalo nuevamente.'
            if not verification.is_valid():
                request.session.flush()
                context['error_message'] = 'Se agotaron los intentos. Inicia sesión nuevamente.'
            return render(request, 'login/verify_2fa.html', context)

        verification.is_used = True
        verification.save(update_fields=['is_used'])
        request.session.flush()
        usuario = Usuario.objects.filter(email=email).first()
        request.session['current_user'] = email
        request.session['current_user_role'] = usuario.role if usuario else 'paciente'
        request.session['show_tutorial'] = True
        request.session['show_security_tips'] = True
        return redirect('principal')

    return render(request, 'login/verify_2fa.html', context)


def logout_view(request):
    request.session.flush()
    return redirect('login')


def forgot_password_view(request):
    """Solicita el correo para recuperar contraseña"""
    context = {}
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        
        if not email:
            context['error_message'] = 'Ingresa tu correo electrónico.'
            return render(request, 'login/recuperar_contraseña.html', context)
        
        allowed_domains = {
            'gmail.com','hotmail.com','outlook.com','live.com','yahoo.com','icloud.com',
            'protonmail.com','zoho.com','aol.com','gmx.com','yandex.com','mail.com',
            'fastmail.com','tutanota.com'
        }
        
        if '@' not in email or not email.endswith('.com'):
            context['error_message'] = 'Ingrese un correo válido.'
            return render(request, 'login/recuperar_contraseña.html', context)
        
        domain = email.split('@')[-1]
        if domain not in allowed_domains:
            context['error_message'] = 'Ingrese un correo válido.'
            return render(request, 'login/recuperar_contraseña.html', context)
        
        # Verificar si el email existe en la BD
        try:
            usuario = Usuario.objects.get(email=email)
        except Usuario.DoesNotExist:
            # Por seguridad, no revelamos si el email existe o no
            context['info_message'] = 'Si el correo existe en nuestro sistema, recibirás un código de recuperación.'
            return render(request, 'login/recuperar_contraseña.html', context)
        
        # Generar código de 6 dígitos
        code = ''.join(random.choices(string.digits, k=6))
        log_verification_code('Código de recuperación', email, code)

        # Guardar en sesión con timestamp
        request.session['recovery_email'] = email
        request.session['recovery_code'] = code
        request.session['recovery_code_time'] = timezone.now().isoformat()
        request.session.set_expiry(timedelta(minutes=15))  # La sesión expira en 15 minutos
        
        # Enviar email
        try:
            subject = 'Código de recuperación de contraseña - Nexo ReV'
            message = f"""
Hola {usuario.nombre},

Recibimos una solicitud para recuperar tu contraseña en Nexo ReV.

Tu código de recuperación es: {code}

Este código es válido por 15 minutos.

Si no solicitaste recuperar tu contraseña, ignora este correo.

Saludos,
El equipo de Nexo ReV
            """
            
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                [email],
                fail_silently=False,
            )
            
            context['success_message'] = 'Se ha enviado un código de recuperación a tu correo.'
            return redirect('verify_recovery_code')
        except Exception as e:
            # Limpiar sesión si hay error al enviar
            if 'recovery_email' in request.session:
                del request.session['recovery_email']
                del request.session['recovery_code']
                if 'recovery_code_time' in request.session:
                    del request.session['recovery_code_time']
            
            context['error_message'] = 'Error al enviar el correo. Por favor, intenta nuevamente.'
            return render(request, 'login/recuperar_contraseña.html', context)
    
    return render(request, 'login/recuperar_contraseña.html', context)


def verify_recovery_code(request):
    """Verifica el código y permite cambiar la contraseña"""
    context = {}
    email = request.session.get('recovery_email')
    code_time = request.session.get('recovery_code_time')
    
    if not email or not code_time:
        return redirect('forgot_password')
    
    # Verificar si el código ha expirado (15 minutos)
    try:
        code_created = timezone.datetime.fromisoformat(code_time)
        if timezone.now() > code_created + timedelta(minutes=15):
            # Código expirado, limpiar sesión
            del request.session['recovery_email']
            del request.session['recovery_code']
            del request.session['recovery_code_time']
            
            context['error_message'] = 'El código de recuperación ha expirado. Solicita uno nuevo.'
            return render(request, 'login/recuperar_contraseña.html', context)
    except Exception:
        return redirect('forgot_password')
    
    context['email'] = email
    
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        
        if not code:
            context['error_message'] = 'Ingresa el código que recibiste por correo.'
            return render(request, 'login/verify_recovery_code.html', context)
        
        if not password or not password_confirm:
            context['error_message'] = 'Ingresa la nueva contraseña.'
            return render(request, 'login/verify_recovery_code.html', context)
        
        if password != password_confirm:
            context['error_message'] = 'Las contraseñas no coinciden.'
            return render(request, 'login/verify_recovery_code.html', context)
        
        if len(password) < 8:
            context['error_message'] = 'La contraseña debe tener al menos 8 caracteres.'
            return render(request, 'login/verify_recovery_code.html', context)
        
        # Verificar que no sea solo números o solo letras
        if password.isdigit() or password.isalpha():
            context['error_message'] = 'La contraseña debe contener letras y números.'
            return render(request, 'login/verify_recovery_code.html', context)
        
        # Verificar el código
        if code != request.session.get('recovery_code'):
            context['error_message'] = 'Código de recuperación inválido.'
            return render(request, 'login/verify_recovery_code.html', context)
        
        # Actualizar la contraseña del usuario
        try:
            usuario = Usuario.objects.get(email=email)
            usuario.set_password(password)
            usuario.save()
            
            # Limpiar la sesión
            del request.session['recovery_email']
            del request.session['recovery_code']
            del request.session['recovery_code_time']
            
            context['success_message'] = 'Contraseña actualizada correctamente. Inicia sesión con tus nuevas credenciales.'
            context['redirect_to_login'] = True
            
            return render(request, 'login/verify_recovery_code.html', context)
        except Exception as e:
            context['error_message'] = 'Error al actualizar la contraseña. Intenta nuevamente.'
            return render(request, 'login/verify_recovery_code.html', context)
    
    return render(request, 'login/verify_recovery_code.html', context)

