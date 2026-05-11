from django.db import models


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
