from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_control
from datetime import timedelta
import secrets

from crear_cuenta.models import SecurityQuestion, Usuario
from .models import LoginAttempt, RecoverySecurityAttempt, TwoFactorCode
import logging

logger = logging.getLogger('nexorev.auth')
RECOVERY_ATTEMPT_LIMIT = 5
RECOVERY_ATTEMPT_WINDOW = timedelta(minutes=15)


def recovery_ip_address(request):
    return request.META.get('REMOTE_ADDR') or None


def recovery_attempts_locked(email):
    window_start = timezone.now() - RECOVERY_ATTEMPT_WINDOW
    return RecoverySecurityAttempt.objects.filter(
        email=email,
        timestamp__gte=window_start,
    ).count() >= RECOVERY_ATTEMPT_LIMIT


def clear_recovery_session(request):
    for key in (
        'recovery_email',
        'recovery_code',
        'recovery_code_time',
        'recovery_code_verified',
        'recovery_questions_verified',
        'recovery_question_ids',
    ):
        request.session.pop(key, None)


def record_recovery_failure(request, email, stage):
    RecoverySecurityAttempt.objects.create(
        email=email,
        ip_address=recovery_ip_address(request),
    )
    locked = recovery_attempts_locked(email)
    logger.warning(
        'password_recovery_failed email=%s stage=%s ip=%s locked=%s',
        email,
        stage,
        recovery_ip_address(request),
        locked,
    )
    return locked


def log_verification_code(label, email, code):
    message = f'[Nexo ReV] {label} para {email}: {code}'
    print(message, flush=True)
    logger.warning(message)


def send_login_notification(usuario):
    send_mail(
        'Nuevo inicio de sesión - Nexo ReV',
        (
            f'Hola {usuario.nombre},\n\n'
            'Se inició sesión en tu cuenta de Nexo ReV.\n\n'
            'Si no reconoces esta actividad, te recomendamos cambiar tu '
            'contraseña y contactar al equipo de soporte.\n\n'
            'Saludos,\n'
            'El equipo de Nexo ReV'
        ),
        settings.DEFAULT_FROM_EMAIL,
        [usuario.email],
        fail_silently=False,
    )


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
        request.session['show_security_tips'] = True
        request.session['show_initial_guide'] = True
        if usuario:
            try:
                send_login_notification(usuario)
            except Exception:
                logger.exception(
                    'No se pudo enviar la notificación de inicio de sesión a %s',
                    email,
                )
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

        if recovery_attempts_locked(email):
            logger.warning(
                'password_recovery_blocked email=%s stage=request ip=%s',
                email,
                recovery_ip_address(request),
            )
            context['error_message'] = 'Se agotaron los intentos de recuperación. Espera 15 minutos antes de intentarlo de nuevo.'
            return render(request, 'login/recuperar_contraseña.html', context)

        usuario = Usuario.objects.filter(email=email, is_active=True).first()
        if not usuario:
            context['info_message'] = 'Si el correo existe en nuestro sistema, recibirás un código de recuperación.'
            return render(request, 'login/recuperar_contraseña.html', context)

        code = ''.join(str(secrets.randbelow(10)) for _ in range(6))
        request.session['recovery_email'] = email
        request.session['recovery_code'] = code
        request.session['recovery_code_time'] = timezone.now().isoformat()
        request.session['recovery_question_ids'] = list(
            SecurityQuestion.objects.filter(user=usuario).values_list('pk', flat=True)
        )
        clear_recovery_session_flags = (
            'recovery_code_verified',
            'recovery_questions_verified',
        )
        for key in clear_recovery_session_flags:
            request.session.pop(key, None)
        request.session.set_expiry(RECOVERY_ATTEMPT_WINDOW)

        try:
            send_mail(
                'Código de recuperación de contraseña - Nexo ReV',
                f"""
Hola {usuario.nombre},

Recibimos una solicitud para recuperar tu contraseña en Nexo ReV.

Tu código de recuperación es: {code}

Este código es válido por 15 minutos.

Si no solicitaste recuperar tu contraseña, ignora este correo.

Saludos,
El equipo de Nexo ReV
                """,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
        except Exception:
            clear_recovery_session(request)
            logger.exception('password_recovery_email_failed email=%s', email)
            context['error_message'] = 'Error al enviar el correo. Por favor, intenta nuevamente.'
            return render(request, 'login/recuperar_contraseña.html', context)

        logger.info(
            'password_recovery_started user_id=%s ip=%s',
            usuario.pk,
            recovery_ip_address(request),
        )
        return redirect('verify_recovery_code')

    return render(request, 'login/recuperar_contraseña.html', context)


def verify_recovery_code(request):
    """Verifica el código de correo, las preguntas y la nueva contraseña."""
    context = {}
    email = request.session.get('recovery_email')
    code_time = request.session.get('recovery_code_time')

    if not email or not code_time:
        return redirect('forgot_password')

    if recovery_attempts_locked(email):
        clear_recovery_session(request)
        context['error_message'] = 'Se agotaron los intentos de recuperación. Espera 15 minutos antes de intentarlo de nuevo.'
        return render(request, 'login/recuperar_contraseña.html', context)

    try:
        code_created = timezone.datetime.fromisoformat(code_time)
        if timezone.now() > code_created + timedelta(minutes=15):
            clear_recovery_session(request)
            logger.info('password_recovery_expired email=%s', email)
            context['error_message'] = 'El código de recuperación ha expirado. Solicita uno nuevo.'
            return render(request, 'login/recuperar_contraseña.html', context)
    except (TypeError, ValueError):
        clear_recovery_session(request)
        return redirect('forgot_password')

    usuario = Usuario.objects.filter(email=email, is_active=True).first()
    if not usuario:
        clear_recovery_session(request)
        logger.warning('password_recovery_user_missing email=%s', email)
        return redirect('forgot_password')

    questions = list(SecurityQuestion.objects.filter(user=usuario))
    question_ids = [question.pk for question in questions]
    expected_question_ids = request.session.get('recovery_question_ids')
    if expected_question_ids is None:
        request.session['recovery_question_ids'] = question_ids
    elif expected_question_ids != question_ids:
        clear_recovery_session(request)
        logger.warning(
            'password_recovery_questions_changed user_id=%s ip=%s',
            usuario.pk,
            recovery_ip_address(request),
        )
        return render(request, 'login/recuperar_contraseña.html', {
            'error_message': 'Tus preguntas de seguridad cambiaron. Solicita un nuevo código para continuar.',
        })

    code_verified = bool(request.session.get('recovery_code_verified'))
    questions_verified = bool(request.session.get('recovery_questions_verified'))
    if code_verified and questions and not questions_verified:
        stage = 'questions'
    elif code_verified:
        stage = 'password'
    else:
        stage = 'code'

    context['email'] = email
    context['stage'] = stage
    if stage == 'questions':
        context['security_questions'] = [
            {'id': question.pk, 'question': question.question}
            for question in questions
        ]

    if request.method == 'POST':
        if stage == 'code':
            code = request.POST.get('code', '').strip()
            if (
                len(code) != 6
                or not code.isascii()
                or not code.isdigit()
                or not secrets.compare_digest(code, request.session.get('recovery_code', ''))
            ):
                if record_recovery_failure(request, email, 'email_code'):
                    clear_recovery_session(request)
                    return render(request, 'login/recuperar_contraseña.html', {
                        'error_message': 'Se agotaron los intentos de recuperación. Espera 15 minutos antes de intentarlo de nuevo.',
                    })
                context['error_message'] = 'Código de recuperación inválido.'
                return render(request, 'login/verify_recovery_code.html', context)

            request.session['recovery_code_verified'] = True
            request.session['recovery_questions_verified'] = not questions
            logger.info(
                'password_recovery_email_verified user_id=%s questions_required=%s ip=%s',
                usuario.pk,
                bool(questions),
                recovery_ip_address(request),
            )
            return redirect('verify_recovery_code')

        if stage == 'questions':
            answers_valid = True
            for question in questions:
                answer = request.POST.get(f'answer_{question.pk}', '')
                answer_matches = question.check_answer(answer)
                answers_valid = answers_valid and bool(SecurityQuestion.normalize(answer)) and answer_matches

            if not answers_valid:
                if record_recovery_failure(request, email, 'security_questions'):
                    clear_recovery_session(request)
                    return render(request, 'login/recuperar_contraseña.html', {
                        'error_message': 'Se agotaron los intentos de recuperación. Espera 15 minutos antes de intentarlo de nuevo.',
                    })
                context['error_message'] = 'Una o más respuestas son incorrectas. Inténtalo nuevamente.'
                return render(request, 'login/verify_recovery_code.html', context)

            request.session['recovery_questions_verified'] = True
            logger.info(
                'password_recovery_questions_verified user_id=%s question_count=%s ip=%s',
                usuario.pk,
                len(questions),
                recovery_ip_address(request),
            )
            return redirect('verify_recovery_code')

        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        if not password or not password_confirm:
            context['error_message'] = 'Ingresa y confirma la nueva contraseña.'
        elif password != password_confirm:
            context['error_message'] = 'Las contraseñas no coinciden.'
        elif len(password) < 8:
            context['error_message'] = 'La contraseña debe tener al menos 8 caracteres.'
        elif password.isdigit() or password.isalpha():
            context['error_message'] = 'La contraseña debe contener letras y números.'
        else:
            usuario.set_password(password)
            usuario.save(update_fields=['password'])
            logger.info(
                'password_recovery_completed user_id=%s ip=%s',
                usuario.pk,
                recovery_ip_address(request),
            )
            clear_recovery_session(request)
            context['success_message'] = 'Contraseña actualizada correctamente. Inicia sesión con tus nuevas credenciales.'
            context['redirect_to_login'] = True
            return render(request, 'login/verify_recovery_code.html', context)

        return render(request, 'login/verify_recovery_code.html', context)

    return render(request, 'login/verify_recovery_code.html', context)
