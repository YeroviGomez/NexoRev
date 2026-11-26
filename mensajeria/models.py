from django.core.validators import MaxLengthValidator, MinLengthValidator
from django.db import models


class Mensaje(models.Model):
    TIPO_USUARIO = 'usuario'
    TIPO_SISTEMA = 'sistema'
    TIPO_CHOICES = [
        (TIPO_USUARIO, 'Usuario'),
        (TIPO_SISTEMA, 'Sistema'),
    ]

    paciente = models.ForeignKey(
        'princpal.Paciente',
        on_delete=models.CASCADE,
        related_name='mensajes',
    )
    autor = models.ForeignKey(
        'crear_cuenta.Usuario',
        on_delete=models.SET_NULL,
        null=True,
    )
    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES,
        default=TIPO_USUARIO,
    )
    texto = models.CharField(
        max_length=2000,
        validators=[MinLengthValidator(1), MaxLengthValidator(2000)],
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    leido_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['creado_en', 'pk']
        indexes = [
            models.Index(fields=['paciente', 'creado_en']),
        ]

    def __str__(self):
        return f'Mensaje {self.pk} — paciente {self.paciente_id}'
