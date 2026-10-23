from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
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
    ESTADO_PROGRAMADA = 'programada'
    ESTADO_COMPLETADA = 'completada'
    ESTADO_CANCELADA = 'cancelada'
    ESTADO_NO_ASISTIO = 'no_asistio'
    ESTADO_CHOICES = [
        (ESTADO_PROGRAMADA, 'Programada'),
        (ESTADO_COMPLETADA, 'Completada'),
        (ESTADO_CANCELADA, 'Cancelada'),
        (ESTADO_NO_ASISTIO, 'No asistió'),
    ]

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='sesiones')
    fecha = models.DateTimeField('fecha de sesión')
    objetivo = models.CharField('objetivo', max_length=255)
    objetivo_terapeutico = models.ForeignKey(
        'ObjetivoTerapeutico',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sesiones',
        verbose_name='objetivo terapéutico',
    )
    nota_objetivo = models.TextField('nota del objetivo', blank=True)
    duracion_minutos = models.PositiveSmallIntegerField(
        'duración en minutos',
        default=45,
        validators=[MinValueValidator(1)],
    )
    enlace_ubicacion = models.CharField('enlace o ubicación', max_length=500, blank=True)
    estado = models.CharField(
        'estado',
        max_length=15,
        choices=ESTADO_CHOICES,
        default=ESTADO_PROGRAMADA,
    )
    avance = models.TextField('avance', blank=True)
    activo = models.BooleanField('activa', default=True)
    realizada = models.BooleanField('realizada', default=False)
    realizada_en = models.DateTimeField('realizada el', null=True, blank=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Sesión'
        verbose_name_plural = 'Sesiones'

    def __str__(self):
        return f"{self.paciente.nombre} — {self.fecha:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        if self.estado == self.ESTADO_PROGRAMADA:
            if not self.activo:
                self.estado = self.ESTADO_CANCELADA
            elif self.realizada:
                self.estado = self.ESTADO_COMPLETADA
        self.activo = self.estado != self.ESTADO_CANCELADA
        self.realizada = self.estado == self.ESTADO_COMPLETADA
        super().save(*args, **kwargs)


class SolicitudReagendamiento(models.Model):
    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_APROBADA = 'aprobada'
    ESTADO_RECHAZADA = 'rechazada'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_APROBADA, 'Aprobada'),
        (ESTADO_RECHAZADA, 'Rechazada'),
    ]

    sesion = models.ForeignKey(
        Sesion,
        on_delete=models.CASCADE,
        related_name='solicitudes_reagendamiento',
    )
    motivo = models.TextField('motivo')
    fecha_original = models.DateTimeField('fecha original')
    fecha_propuesta = models.DateTimeField('fecha propuesta')
    fecha_alternativa = models.DateTimeField('fecha alternativa', null=True, blank=True)
    estado = models.CharField(
        'estado',
        max_length=12,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
    )
    respuesta_medico = models.TextField('respuesta del médico', blank=True)
    creada_en = models.DateTimeField('creada el', auto_now_add=True)
    actualizada_en = models.DateTimeField('actualizada el', auto_now=True)
    revisada_por = models.ForeignKey(
        'crear_cuenta.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitudes_reagendamiento_revisadas',
    )

    class Meta:
        ordering = ['-creada_en', '-pk']
        verbose_name = 'Solicitud de reagendamiento'
        verbose_name_plural = 'Solicitudes de reagendamiento'
        constraints = [
            models.UniqueConstraint(
                fields=['sesion'],
                condition=Q(estado='pendiente'),
                name='unique_pending_reschedule_per_session',
            ),
        ]

    def __str__(self):
        return f'{self.sesion.paciente.nombre} — {self.get_estado_display()}'


class EvaluacionClinica(models.Model):
    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='evaluaciones')
    fecha = models.DateTimeField('fecha de evaluación', auto_now_add=True)
    nivel_dolor = models.PositiveSmallIntegerField(
        'dolor (EVA)',
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    metrica = models.CharField('métrica clínica', max_length=100, blank=True)
    valor_actual = models.DecimalField(
        'valor actual',
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    unidad = models.CharField('unidad', max_length=30, blank=True)

    class Meta:
        ordering = ['fecha', 'pk']
        verbose_name = 'Evaluación clínica'
        verbose_name_plural = 'Evaluaciones clínicas'

    def __str__(self):
        return f'{self.paciente.nombre} — EVA {self.nivel_dolor} ({self.fecha:%Y-%m-%d})'


class ObjetivoTerapeutico(models.Model):
    DIRECCION_MAYOR = 'mayor'
    DIRECCION_MENOR = 'menor'
    DIRECCION_CHOICES = [
        (DIRECCION_MAYOR, 'Alcanzar o superar'),
        (DIRECCION_MENOR, 'Reducir hasta'),
    ]

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='objetivos')
    nombre = models.CharField('objetivo', max_length=150)
    metrica = models.CharField('métrica clínica', max_length=100)
    direccion = models.CharField(
        'criterio de cumplimiento',
        max_length=10,
        choices=DIRECCION_CHOICES,
        default=DIRECCION_MAYOR,
    )
    valor_objetivo = models.DecimalField(
        'valor objetivo',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    unidad = models.CharField('unidad', max_length=30, blank=True)
    creado_en = models.DateTimeField('creado el', auto_now_add=True)

    class Meta:
        ordering = ['nombre', 'pk']
        verbose_name = 'Objetivo terapéutico'
        verbose_name_plural = 'Objetivos terapéuticos'

    def __str__(self):
        return f'{self.paciente.nombre} — {self.nombre}'


class PlantillaRutina(models.Model):
    doctor = models.ForeignKey(
        'crear_cuenta.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='plantillas_rutina',
        limit_choices_to={'role': 'doctor'},
        verbose_name='médico',
    )
    nombre = models.CharField('nombre', max_length=150)
    descripcion = models.TextField('descripción', blank=True)
    activa = models.BooleanField('activa', default=True)
    creada_en = models.DateTimeField('creada el', auto_now_add=True)
    actualizada_en = models.DateTimeField('actualizada el', auto_now=True)

    class Meta:
        ordering = ['nombre', 'pk']
        verbose_name = 'Plantilla de rutina'
        verbose_name_plural = 'Plantillas de rutina'

    def __str__(self):
        return self.nombre


class EjercicioPlantillaRutina(models.Model):
    plantilla = models.ForeignKey(
        PlantillaRutina,
        on_delete=models.CASCADE,
        related_name='ejercicios',
    )
    video_id = models.CharField('ID del video', max_length=128)
    titulo = models.CharField('ejercicio', max_length=150)
    orden = models.PositiveSmallIntegerField('orden', default=1)

    class Meta:
        ordering = ['orden', 'pk']
        verbose_name = 'Ejercicio de plantilla'
        verbose_name_plural = 'Ejercicios de plantilla'
        constraints = [
            models.UniqueConstraint(fields=['plantilla', 'video_id'], name='unique_video_per_routine_template'),
        ]

    def __str__(self):
        return f'{self.plantilla.nombre} — {self.titulo}'


class RutinaAsignada(models.Model):
    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.CASCADE,
        related_name='rutinas_asignadas',
    )
    video_id = models.CharField('ID de rutina', max_length=128)
    titulo = models.CharField('rutina', max_length=150)
    fecha_programada = models.DateField('fecha programada')
    plantilla = models.ForeignKey(
        PlantillaRutina,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asignaciones',
        verbose_name='plantilla',
    )
    fecha_inicio = models.DateField('fecha de inicio')
    fecha_fin = models.DateField('fecha de fin')
    dias_semana = models.JSONField('días de la semana', default=list, blank=True)
    asignada_en = models.DateTimeField('asignada el', auto_now_add=True)
    completada_en = models.DateTimeField('completada el', null=True, blank=True)

    class Meta:
        ordering = ['fecha_programada', 'pk']
        verbose_name = 'Rutina asignada'
        verbose_name_plural = 'Rutinas asignadas'
        indexes = [
            models.Index(fields=['paciente', 'fecha_programada']),
            models.Index(fields=['paciente', 'fecha_inicio', 'fecha_fin']),
        ]

    def __str__(self):
        return f'{self.paciente.nombre} — {self.titulo} ({self.fecha_programada:%Y-%m-%d})'

    def save(self, *args, **kwargs):
        if self.fecha_inicio is None:
            self.fecha_inicio = self.fecha_programada
        if self.fecha_fin is None:
            self.fecha_fin = self.fecha_programada
        if not self.dias_semana:
            self.dias_semana = [self.fecha_programada.weekday()]
        super().save(*args, **kwargs)


class EjercicioRutinaAsignada(models.Model):
    asignacion = models.ForeignKey(
        RutinaAsignada,
        on_delete=models.CASCADE,
        related_name='ejercicios',
    )
    video_id = models.CharField('ID del video', max_length=128)
    titulo = models.CharField('ejercicio', max_length=150)
    orden = models.PositiveSmallIntegerField('orden', default=1)
    series = models.PositiveSmallIntegerField(
        'series',
        validators=[MinValueValidator(1)],
    )
    repeticiones = models.CharField('repeticiones', max_length=100, blank=True)
    duracion_minutos = models.PositiveSmallIntegerField(
        'duración en minutos',
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    notas_medico = models.TextField('notas del médico', blank=True)

    class Meta:
        ordering = ['orden', 'pk']
        verbose_name = 'Ejercicio de rutina asignada'
        verbose_name_plural = 'Ejercicios de rutina asignada'

    def __str__(self):
        return f'{self.asignacion.titulo} — {self.titulo}'


class OcurrenciaRutina(models.Model):
    DIFICULTAD_FACIL = 'facil'
    DIFICULTAD_ADECUADA = 'adecuada'
    DIFICULTAD_DIFICIL = 'dificil'
    DIFICULTAD_CHOICES = [
        (DIFICULTAD_FACIL, 'Fácil'),
        (DIFICULTAD_ADECUADA, 'Adecuada'),
        (DIFICULTAD_DIFICIL, 'Difícil'),
    ]

    asignacion = models.ForeignKey(
        RutinaAsignada,
        on_delete=models.CASCADE,
        related_name='ocurrencias',
    )
    fecha = models.DateField('fecha')
    completada_en = models.DateTimeField('completada el', null=True, blank=True)
    nivel_dolor = models.PositiveSmallIntegerField(
        'dolor (EVA)',
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    dificultad = models.CharField(
        'dificultad',
        max_length=10,
        choices=DIFICULTAD_CHOICES,
        blank=True,
    )
    comentario = models.TextField('comentario', blank=True)

    class Meta:
        ordering = ['fecha', 'pk']
        verbose_name = 'Ocurrencia de rutina'
        verbose_name_plural = 'Ocurrencias de rutina'
        constraints = [
            models.UniqueConstraint(fields=['asignacion', 'fecha'], name='unique_routine_occurrence_per_day'),
        ]
        indexes = [
            models.Index(fields=['fecha', 'completada_en']),
        ]

    def __str__(self):
        return f'{self.asignacion.titulo} — {self.fecha:%Y-%m-%d}'


class Diagnostico(models.Model):
    usuario = models.OneToOneField(
        'crear_cuenta.Usuario',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='diagnostico',
        verbose_name='usuario',
    )
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
    rutina_asignada = models.ForeignKey(
        RutinaAsignada,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vistas',
    )

    class Meta:
        ordering = ['-viewed_at']
        verbose_name = 'Video visto'
        verbose_name_plural = 'Videos vistos'

    def __str__(self):
        return f'{self.user_email} - {self.video_id}'