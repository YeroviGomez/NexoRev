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