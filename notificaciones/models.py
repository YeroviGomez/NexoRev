from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class AlertaDolor(models.Model):
    REGLA_UMBRAL = 'umbral'
    REGLA_SUBIDA = 'subida'
    REGLA_RACHA = 'racha'
    REGLA_CHOICES = [
        (REGLA_UMBRAL, 'Umbral de dolor'),
        (REGLA_SUBIDA, 'Subida del dolor'),
        (REGLA_RACHA, 'Racha de dolor elevado'),
    ]

    ESTADO_NUEVA = 'nueva'
    ESTADO_VISTA = 'vista'
    ESTADO_ATENDIDA = 'atendida'
    ESTADO_CHOICES = [
        (ESTADO_NUEVA, 'Nueva'),
        (ESTADO_VISTA, 'Vista'),
        (ESTADO_ATENDIDA, 'Atendida'),
    ]

    paciente = models.ForeignKey(
        'princpal.Paciente',
        on_delete=models.CASCADE,
        related_name='alertas_dolor',
        verbose_name='paciente',
    )
    doctor = models.ForeignKey(
        'crear_cuenta.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alertas_dolor_como_doctor',
        verbose_name='médico asignado',
    )
    ocurrencia = models.OneToOneField(
        'princpal.OcurrenciaRutina',
        on_delete=models.CASCADE,
        related_name='alerta_dolor',
        verbose_name='ocurrencia de rutina',
    )
    nivel_dolor = models.PositiveSmallIntegerField(
        'nivel de dolor EVA',
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    regla = models.CharField('regla activada', max_length=10, choices=REGLA_CHOICES)
    estado = models.CharField(
        'estado',
        max_length=10,
        choices=ESTADO_CHOICES,
        default=ESTADO_NUEVA,
    )
    creada_en = models.DateTimeField('creada el', auto_now_add=True)
    vista_en = models.DateTimeField('vista el', null=True, blank=True)
    atendida_por = models.ForeignKey(
        'crear_cuenta.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alertas_dolor_atendidas',
        verbose_name='atendida por',
    )
    atendida_en = models.DateTimeField('atendida el', null=True, blank=True)
    nota_atencion = models.TextField('nota de atención', blank=True)
    correo_enviado_en = models.DateTimeField('correo enviado el', null=True, blank=True)
    correo_error = models.TextField('error de correo', blank=True)
    correo_intentos = models.PositiveSmallIntegerField('intentos de correo', default=0)

    class Meta:
        ordering = ['-creada_en']
        verbose_name = 'Alerta de dolor'
        verbose_name_plural = 'Alertas de dolor'
        indexes = [
            models.Index(fields=['doctor', 'estado'], name='alerta_doctor_estado_idx'),
            models.Index(fields=['paciente', 'creada_en'], name='alerta_paciente_creada_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(nivel_dolor__gte=0, nivel_dolor__lte=10),
                name='alerta_dolor_eva_0_10',
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.paciente_id:
            self.doctor_id = self.paciente.doctor_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Alerta de dolor para {self.paciente} ({self.nivel_dolor}/10)'


class Recordatorio(models.Model):
    paciente = models.ForeignKey(
        'princpal.Paciente',
        on_delete=models.CASCADE,
        related_name='recordatorios',
        verbose_name='paciente',
    )
    hora = models.TimeField('hora del recordatorio')
    dias_semana = models.JSONField('días de la semana', default=list)
    activo = models.BooleanField('activo', default=True)
    creado_en = models.DateTimeField('creado el', auto_now_add=True)

    class Meta:
        ordering = ['hora', 'pk']
        verbose_name = 'Recordatorio de rutina'
        verbose_name_plural = 'Recordatorios de rutina'
        constraints = [
            models.UniqueConstraint(
                fields=['paciente', 'hora'],
                condition=Q(activo=True),
                name='uniq_active_reminder_hour',
            ),
        ]

    def __str__(self):
        return f'Recordatorio para {self.paciente} a las {self.hora:%H:%M}'


class RegistroRecordatorio(models.Model):
    recordatorio = models.ForeignKey(
        Recordatorio,
        on_delete=models.CASCADE,
        related_name='registros',
        verbose_name='recordatorio',
    )
    fecha = models.DateField('fecha local')
    enviado_en = models.DateTimeField('enviado el', null=True, blank=True)
    error = models.TextField('error', blank=True)
    procesando_en = models.DateTimeField('procesando desde', null=True, blank=True)

    class Meta:
        ordering = ['-fecha', '-pk']
        verbose_name = 'Registro de recordatorio'
        verbose_name_plural = 'Registros de recordatorios'
        constraints = [
            models.UniqueConstraint(
                fields=['recordatorio', 'fecha'],
                name='uniq_recordatorio_fecha',
            ),
        ]

    def __str__(self):
        return f'{self.recordatorio} — {self.fecha:%Y-%m-%d}'


class EnvioResumenSemanal(models.Model):
    paciente = models.ForeignKey(
        'princpal.Paciente',
        on_delete=models.CASCADE,
        related_name='envios_resumen_semanal',
        verbose_name='paciente',
    )
    semana_inicio = models.DateField('inicio de semana')
    enviado_en = models.DateTimeField('enviado el', null=True, blank=True)
    error = models.TextField('error', blank=True)

    class Meta:
        ordering = ['-semana_inicio', 'pk']
        verbose_name = 'Envío de resumen semanal'
        verbose_name_plural = 'Envíos de resúmenes semanales'
        constraints = [
            models.UniqueConstraint(
                fields=['paciente', 'semana_inicio'],
                name='uniq_resumen_paciente_semana',
            ),
        ]

    def __str__(self):
        return f'Resumen de {self.paciente} — {self.semana_inicio:%Y-%m-%d}'