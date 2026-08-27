from django.db import models


class Paciente(models.Model):
    nombre = models.CharField('nombre', max_length=150)
    email = models.EmailField('correo electrónico', unique=True)
    telefono = models.CharField('teléfono', max_length=20, blank=True)
    direccion = models.CharField('dirección', max_length=255, blank=True)
    fecha_nacimiento = models.DateField('fecha de nacimiento', null=True, blank=True)
    fecha_registro = models.DateTimeField('fecha de registro', auto_now_add=True)

    class Meta:
        verbose_name = 'Paciente'
        verbose_name_plural = 'Pacientes'

    def __str__(self):
        return self.nombre


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