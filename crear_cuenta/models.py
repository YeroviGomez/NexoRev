from django.contrib.auth.hashers import check_password, make_password
from django.db import models


SECURITY_QUESTION_CHOICES = (
    ('first_pet', '¿Cuál es el nombre de tu primera mascota?'),
    ('primary_school', '¿Cuál era el nombre de tu escuela primaria?'),
    ('favorite_food', '¿Cuál es tu comida favorita?'),
    ('birth_city', '¿Cuál es la ciudad donde naciste?'),
    ('first_job', '¿Cuál fue tu primer empleo?'),
    ('childhood_friend', '¿Cuál es el nombre de tu mejor amigo de la infancia?'),
    ('mother_surname', '¿Cuál es el segundo apellido de tu madre?'),
)


class SecurityQuestion(models.Model):
    user = models.ForeignKey(
        'crear_cuenta.Usuario',
        on_delete=models.CASCADE,
        related_name='security_questions',
    )
    question = models.CharField('pregunta de seguridad', max_length=255)
    question_key = models.CharField('pregunta normalizada', max_length=255)
    answer_hash = models.CharField('hash de respuesta', max_length=128)
    is_custom = models.BooleanField('pregunta personalizada', default=False)
    created_at = models.DateTimeField('fecha de creación', auto_now_add=True)

    class Meta:
        ordering = ['pk']
        verbose_name = 'Pregunta de seguridad'
        verbose_name_plural = 'Preguntas de seguridad'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'question_key'],
                name='unique_security_question_per_user',
            ),
        ]

    @staticmethod
    def normalize(value):
        return ' '.join(value.split()).casefold()

    def set_answer(self, answer):
        self.answer_hash = make_password(self.normalize(answer))

    def check_answer(self, answer):
        return check_password(self.normalize(answer), self.answer_hash)

    def save(self, *args, **kwargs):
        self.question = ' '.join(self.question.split())
        self.question_key = self.normalize(self.question)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.question


class Usuario(models.Model):
    ROLE_PACIENTE = 'paciente'
    ROLE_DOCTOR = 'doctor'
    ROLE_CHOICES = [
        (ROLE_PACIENTE, 'Paciente'),
        (ROLE_DOCTOR, 'Doctor'),
    ]

    email = models.EmailField('correo electrónico', unique=True)
    nombre = models.CharField('nombre completo', max_length=150)
    telefono = models.CharField('teléfono', max_length=20, blank=True)
    foto_perfil = models.ImageField('foto de perfil', upload_to='perfiles/', null=True, blank=True)
    password = models.CharField('contraseña', max_length=128)
    is_active = models.BooleanField('activo', default=True)
    role = models.CharField('rol', max_length=20, choices=ROLE_CHOICES, default=ROLE_PACIENTE)
    especialidad = models.CharField('especialidad', max_length=150, blank=True)
    colegiado = models.CharField('número de colegiado', max_length=80, blank=True)
    modo_oscuro = models.BooleanField('modo oscuro', default=False)
    tamano_letra = models.CharField(
        'tamaño de letra',
        max_length=10,
        choices=[
            ('normal', 'Normal'),
            ('large', 'Grande'),
            ('xlarge', 'Muy grande'),
        ],
        default='normal',
    )
    desactivar_animaciones = models.BooleanField('animaciones desactivadas', default=False)
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
