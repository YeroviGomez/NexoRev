from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class Usuario(models.Model):
    email = models.EmailField('correo electrónico', unique=True)
    nombre = models.CharField('nombre completo', max_length=150)
    password = models.CharField('contraseña', max_length=128)
    is_active = models.BooleanField('activo', default=True)
    fecha_creacion = models.DateTimeField('fecha de creación', auto_now_add=True)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.email

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
