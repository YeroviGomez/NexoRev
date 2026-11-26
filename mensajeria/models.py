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


class Llamada(models.Model):
    ESTADO_SONANDO = 'sonando'
    ESTADO_EN_CURSO = 'en_curso'
    ESTADO_RECHAZADA = 'rechazada'
    ESTADO_PERDIDA = 'perdida'
    ESTADO_CANCELADA = 'cancelada'
    ESTADO_FINALIZADA = 'finalizada'
    ESTADO_CHOICES = [
        (ESTADO_SONANDO, 'Sonando'),
        (ESTADO_EN_CURSO, 'En curso'),
        (ESTADO_RECHAZADA, 'Rechazada'),
        (ESTADO_PERDIDA, 'Perdida'),
        (ESTADO_CANCELADA, 'Cancelada'),
        (ESTADO_FINALIZADA, 'Finalizada'),
    ]
    ESTADOS_ACTIVOS = (ESTADO_SONANDO, ESTADO_EN_CURSO)

    paciente = models.ForeignKey(
        'princpal.Paciente',
        on_delete=models.CASCADE,
        related_name='llamadas',
    )
    iniciador = models.ForeignKey(
        'crear_cuenta.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='llamadas_iniciadas',
    )
    estado = models.CharField(
        max_length=12,
        choices=ESTADO_CHOICES,
        default=ESTADO_SONANDO,
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    contestada_en = models.DateTimeField(null=True, blank=True)
    finalizada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creado_en', '-pk']
        indexes = [
            models.Index(fields=['paciente', 'creado_en']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['paciente'],
                condition=models.Q(estado__in=('sonando', 'en_curso')),
                name='unique_active_call_per_patient',
            ),
        ]

    def __str__(self):
        return f'Videollamada {self.pk} — paciente {self.paciente_id}'
