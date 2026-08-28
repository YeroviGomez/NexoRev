from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class Usuario(models.Model):
    ROLE_PACIENTE = 'paciente'
    ROLE_DOCTOR = 'doctor'
    ROLE_CHOICES = [
        (ROLE_PACIENTE, 'Paciente'),
        (ROLE_DOCTOR, 'Doctor'),
    ]

    email = models.EmailField('correo electrónico', unique=True)
    nombre = models.CharField('nombre completo', max_length=150)
    foto_perfil = models.ImageField('foto de perfil', upload_to='perfiles/', null=True, blank=True)
    password = models.CharField('contraseña', max_length=128)
    is_active = models.BooleanField('activo', default=True)
    role = models.CharField('rol', max_length=20, choices=ROLE_CHOICES, default=ROLE_PACIENTE)
    especialidad = models.CharField('especialidad', max_length=150, blank=True)
    colegiado = models.CharField('número de colegiado', max_length=80, blank=True)
    modo_oscuro = models.BooleanField('modo oscuro', default=False)
    fecha_creacion = models.DateTimeField('fecha de creación', auto_now_add=True)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.email

    @property
    def is_paciente(self):
        return self.role == self.ROLE_PACIENTE

    @property
    def is_doctor(self):
        return self.role == self.ROLE_DOCTOR

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)
