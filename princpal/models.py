from django.db import models
from django.utils import timezone


class Paciente(models.Model):
    ESTADO_INICIAL = 'inicial'
    ESTADO_EN_PROCESO = 'en_proceso'
    ESTADO_AVANZADO = 'avanzado'
    ESTADO_FINALIZADO = 'finalizado'
    ESTADO_CHOICES = [
        (ESTADO_INICIAL, 'Inicial'),
        (ESTADO_EN_PROCESO, 'En proceso'),
        (ESTADO_AVANZADO, 'Avanzado'),
        (ESTADO_FINALIZADO, 'Finalizado'),
    ]

    usuario = models.OneToOneField(
        'crear_cuenta.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='perfil_paciente',
        verbose_name='usuario'
    )
    doctor = models.ForeignKey(
        'crear_cuenta.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pacientes_asignados',
        verbose_name='doctor',
        db_column='doctor_id',
        limit_choices_to={'role': 'doctor'}
    )
    nombre = models.CharField('nombre', max_length=150)
    email = models.EmailField('correo electrónico', unique=True)
    edad = models.PositiveSmallIntegerField('edad', default=0)
    telefono = models.CharField('teléfono', max_length=20, blank=True)
    direccion = models.CharField('dirección', max_length=255, blank=True)
    zona_afectada = models.CharField('zona afectada', max_length=100, blank=True)
    fecha_nacimiento = models.DateField('fecha de nacimiento', null=True, blank=True)
    avance = models.PositiveSmallIntegerField('avance (%)', default=0)
    estado = models.CharField('estado', max_length=20, choices=ESTADO_CHOICES, default=ESTADO_INICIAL)
    historial_avance = models.JSONField('historial de avance', default=list, blank=True)
    fecha_registro = models.DateTimeField('fecha de registro', auto_now_add=True)

    class Meta:
        verbose_name = 'Paciente'
        verbose_name_plural = 'Pacientes'

    def __str__(self):
        return self.nombre

    @property
    def color_estado(self):
        palette = {
            self.ESTADO_INICIAL: '#ef4444',
            self.ESTADO_EN_PROCESO: '#f97316',
            self.ESTADO_AVANZADO: '#facc15',
            self.ESTADO_FINALIZADO: '#22c55e',
        }
        return palette.get(self.estado, '#94a3b8')

    def recalcular_estado(self):
        if self.avance >= 100:
            self.estado = self.ESTADO_FINALIZADO
        elif self.avance >= 71:
            self.estado = self.ESTADO_AVANZADO
        elif self.avance >= 31:
            self.estado = self.ESTADO_EN_PROCESO
        else:
            self.estado = self.ESTADO_INICIAL
        return self.estado

    def registrar_avance(self, nuevo_avance):
        nuevo_avance = max(0, min(100, int(nuevo_avance)))
        self.avance = nuevo_avance
        self.historial_avance = list(self.historial_avance or [])
        self.historial_avance.append({
            'fecha': timezone.now().isoformat(),
            'avance': nuevo_avance,
        })
        self.recalcular_estado()
        self.save(update_fields=['avance', 'estado', 'historial_avance'])
        return self

    def get_progress_series(self):
        series = self.historial_avance or []
        if not series:
            return [{'fecha': timezone.now().strftime('%Y-%m-%d'), 'avance': self.avance}]
        return series


class Sesion(models.Model):
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='sesiones')
    fecha = models.DateTimeField('fecha de sesión')
    objetivo = models.CharField('objetivo', max_length=255)
    avance = models.TextField('avance', blank=True)
    activo = models.BooleanField('activa', default=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Sesión'
        verbose_name_plural = 'Sesiones'

    def __str__(self):
        return f"{self.paciente.nombre} — {self.fecha:%Y-%m-%d}"



class Diagnostico(models.Model):
    nivel_dolor = models.IntegerField(default=1)
    pregunta1 = models.CharField(max_length=255)
    pregunta2 = models.TextField()
    pregunta3 = models.CharField(max_length=255)
    comentario = models.TextField(blank=True, null=True)
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Diagnóstico {self.id} - Dolor: {self.nivel_dolor}"


class Video(models.Model):
    title = models.CharField('título', max_length=150)
    description = models.TextField('descripción', blank=True)
    level = models.CharField('nivel', max_length=50, default='Principiante')
    category = models.CharField('categoría', max_length=100, default='General')
    file = models.FileField('archivo de video', upload_to='videos/')
    hls_manifest = models.CharField('manifiesto HLS', max_length=255, blank=True)
    thumbnail = models.ImageField('miniatura', upload_to='miniaturas/', blank=True, null=True)
    uploaded_at = models.DateTimeField('fecha de carga', auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Video local'
        verbose_name_plural = 'Videos locales'

    def __str__(self):
        return self.title


class VideoView(models.Model):
    user_email = models.EmailField('correo del usuario')
    video_id = models.CharField('ID del video', max_length=32)
    category = models.CharField('categoría', max_length=100)
    completed = models.BooleanField('rutina completada', default=False)
    completed_at = models.DateTimeField('fecha de finalización', null=True, blank=True)
    viewed_at = models.DateTimeField('fecha de visualización', auto_now_add=True)

    class Meta:
        ordering = ['-viewed_at']
        verbose_name = 'Video visto'
        verbose_name_plural = 'Videos vistos'

    def __str__(self):
        return f'{self.user_email} - {self.video_id}'