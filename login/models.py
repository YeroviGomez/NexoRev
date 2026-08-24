from django.db import models
from django.utils import timezone
from datetime import timedelta
import secrets


class LoginAttempt(models.Model):
    email = models.EmailField('correo electrónico')
    success = models.BooleanField('éxito', default=False)
    timestamp = models.DateTimeField('fecha', auto_now_add=True)
    ip_address = models.GenericIPAddressField('dirección IP', null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Intento de inicio de sesión'
        verbose_name_plural = 'Intentos de inicio de sesión'

    def __str__(self):
        status = 'OK' if self.success else 'FAIL'
        return f"{self.email} - {status} - {self.timestamp:%Y-%m-%d %H:%M}"


class PasswordRecovery(models.Model):
    email = models.EmailField('correo electrónico')
    code = models.CharField('código', max_length=6, unique=True)
    created_at = models.DateTimeField('fecha de creación', auto_now_add=True)
    is_used = models.BooleanField('utilizado', default=False)

    class Meta:
        verbose_name = 'Recuperación de contraseña'
        verbose_name_plural = 'Recuperaciones de contraseña'
        ordering = ['-created_at']

    def __str__(self):
        status = 'Usado' if self.is_used else 'Activo'
        return f"{self.email} - {status}"

    def is_valid(self):
        """Verifica si el código no ha expirado (válido por 15 minutos)"""
        expiration_time = self.created_at + timedelta(minutes=15)
        return not self.is_used and timezone.now() < expiration_time

    @staticmethod
    def generate_code():
        """Genera un código único de 6 dígitos"""
        while True:
            code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            if not PasswordRecovery.objects.filter(code=code, is_used=False).exists():
                return code


class TwoFactorCode(models.Model):
    email = models.EmailField('correo electrónico')
    code = models.CharField('código', max_length=6)
    created_at = models.DateTimeField('fecha de creación', auto_now_add=True)
    attempts = models.PositiveSmallIntegerField('intentos', default=0)
    is_used = models.BooleanField('utilizado', default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Código de autenticación en dos pasos'
        verbose_name_plural = 'Códigos de autenticación en dos pasos'

    def is_valid(self):
        return (
            not self.is_used
            and self.attempts < 5
            and timezone.now() < self.created_at + timedelta(minutes=10)
        )

    @staticmethod
    def generate_code():
        return ''.join(str(secrets.randbelow(10)) for _ in range(6))
