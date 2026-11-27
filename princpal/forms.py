from django import forms
from django.utils import timezone
from pathlib import Path

from .models import (
    Diagnostico,
    EvaluacionClinica,
    ObjetivoTerapeutico,
    PlantillaRutina,
    Sesion,
    Video,
)

BODY_ZONE_FILTER_OPTIONS = [
    ('Cabeza', 'cabeza'),
    ('Cuello', 'cuello'),
    ('Pecho', 'pecho'),
    ('Abdomen y pelvis', 'abdomen-pelvis'),
    ('Espalda superior', 'espalda-superior'),
    ('Espalda inferior', 'espalda-inferior'),
    ('Hombro', 'hombro'),
    ('Brazo', 'brazo'),
    ('Mano', 'mano'),
    ('Muslo', 'muslo'),
    ('Rodilla', 'rodilla'),
    ('Pierna inferior', 'pierna-inferior'),
    ('Pie', 'pie'),
]
BODY_ZONE_CHOICES = [(label, label) for label, _ in BODY_ZONE_FILTER_OPTIONS] + [('General', 'General')]


class SaveRoutineTemplateForm(forms.Form):
    nombre = forms.CharField(
        max_length=150,
        label='Nombre de la plantilla',
        error_messages={'required': 'Escribe el nombre de la plantilla.'},
    )
    descripcion = forms.CharField(
        required=False,
        label='Descripción (opcional)',
        widget=forms.Textarea(attrs={'rows': 2}),
    )


class AssignRoutineForm(forms.Form):
    DIAS_SEMANA = [
        ('0', 'L'),
        ('1', 'M'),
        ('2', 'X'),
        ('3', 'J'),
        ('4', 'V'),
        ('5', 'S'),
        ('6', 'D'),
    ]

    plantilla = forms.ModelChoiceField(
        queryset=PlantillaRutina.objects.none(),
        label='Rutina',
        error_messages={'required': 'Selecciona una plantilla de rutina válida.'},
    )
    fecha_inicio = forms.DateField(
        label='Fecha de inicio',
        input_formats=['%Y-%m-%d'],
        error_messages={'required': 'Indica la fecha de inicio.', 'invalid': 'Indica una fecha de inicio válida.'},
        widget=forms.DateInput(attrs={'type': 'date', 'lang': 'es'}),
    )
    fecha_fin = forms.DateField(
        label='Fecha de fin',
        input_formats=['%Y-%m-%d'],
        error_messages={'required': 'Indica la fecha de fin.', 'invalid': 'Indica una fecha de fin válida.'},
        widget=forms.DateInput(attrs={'type': 'date', 'lang': 'es'}),
    )
    dias_semana = forms.MultipleChoiceField(
        choices=DIAS_SEMANA,
        label='Días de la semana',
        error_messages={'required': 'Selecciona al menos un día de la semana.'},
    )

    def __init__(self, *args, plantillas=None, ejercicios=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plantilla'].queryset = plantillas or PlantillaRutina.objects.none()
        self.ejercicios = list(ejercicios)
        for ejercicio in self.ejercicios:
            prefix = f'ejercicio_{ejercicio.pk}'
            self.fields[f'{prefix}_series'] = forms.IntegerField(
                label='Series',
                min_value=1,
                error_messages={
                    'required': 'Indica al menos una serie.',
                    'min_value': 'Las series deben ser al menos 1.',
                    'invalid': 'Indica un número válido de series.',
                },
            )
            self.fields[f'{prefix}_repeticiones'] = forms.CharField(
                label='Repeticiones',
                required=False,
                max_length=100,
            )
            self.fields[f'{prefix}_duracion'] = forms.IntegerField(
                label='Duración (minutos)',
                required=False,
                min_value=1,
                error_messages={
                    'min_value': 'La duración debe ser mayor que 0.',
                    'invalid': 'Indica una duración válida.',
                },
            )
            self.fields[f'{prefix}_notas'] = forms.CharField(
                label='Notas del médico',
                required=False,
                widget=forms.Textarea(attrs={'rows': 2}),
            )

    def clean_fecha_fin(self):
        fecha_fin = self.cleaned_data['fecha_fin']
        fecha_inicio = self.cleaned_data.get('fecha_inicio')
        if fecha_inicio and fecha_fin < fecha_inicio:
            raise forms.ValidationError('La fecha de fin no puede ser anterior a la fecha de inicio.')
        return fecha_fin

    def clean_dias_semana(self):
        dias = self.cleaned_data['dias_semana']
        if not dias:
            raise forms.ValidationError('Selecciona al menos un día de la semana.')
        return [int(dia) for dia in dias]

    def clean(self):
        cleaned_data = super().clean()
        for ejercicio in self.ejercicios:
            prefix = f'ejercicio_{ejercicio.pk}'
            duration = cleaned_data.get(f'{prefix}_duracion')
            repetitions = cleaned_data.get(f'{prefix}_repeticiones', '').strip()
            if duration is None and not repetitions:
                self.add_error(
                    f'{prefix}_repeticiones',
                    'Indica repeticiones o una duración mayor que 0.',
                )
        return cleaned_data


class ProfileUpdateForm(forms.Form):
    nombre = forms.CharField(max_length=150, min_length=3, label='Nombre completo')
    email = forms.EmailField(max_length=254, label='Correo electrónico')
    telefono = forms.CharField(max_length=20, required=False, label='Teléfono')

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if len(nombre) < 3:
            raise forms.ValidationError('Ingresa un nombre completo válido.')
        return nombre

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean_telefono(self):
        return self.cleaned_data['telefono'].strip()


class FotoPerfilForm(forms.Form):
    foto = forms.ImageField(label='Foto de perfil')

    def clean_foto(self):
        foto = self.cleaned_data['foto']
        if foto.size > 5 * 1024 * 1024:
            raise forms.ValidationError('La imagen no debe superar 5 MB.')
        return foto

class DiagnosticoForm(forms.Form):
    required_error = 'Este campo es obligatorio.'

    QUESTION_CHOICES = {
        'pregunta1': [
            ('cuello', 'a) Cuello o zona cervical'),
            ('espalda', 'b) Espalda (alta, media o lumbar)'),
            ('extremidades_superiores', 'c) Extremidades superiores (hombro, brazo, codo, muñeca o mano)'),
            ('extremidades_inferiores', 'd) Extremidades inferiores (cadera, pierna, rodilla, tobillo o pie)'),
        ],
        'pregunta2': [
            ('caida_golpe', 'a) Sí, caída o golpe'),
            ('esfuerzo_postura', 'b) Sí, esfuerzo o mala postura'),
            ('cirugia', 'c) Cirugía previa'),
            ('no', 'd) No'),
        ],
        'pregunta3': [
            ('menos_una_semana', 'a) Menos de 1 semana'),
            ('una_cuatro_semanas', 'b) 1 a 4 semanas'),
            ('uno_seis_meses', 'c) 1 a 6 meses'),
            ('mas_seis_meses', 'd) Más de 6 meses'),
        ],
        'pregunta4': [
            ('mejorado', 'a) Ha mejorado'),
            ('igual', 'b) Sigue igual'),
            ('empeorado', 'c) Ha empeorado'),
            ('intermitente', 'd) Va y viene'),
        ],
        'pregunta5': [
            ('2', 'a) Leve (1 a 3 en una escala del 1 al 10)'),
            ('5', 'b) Moderado (4 a 6 en una escala del 1 al 10)'),
            ('8', 'c) Fuerte (7 a 8 en una escala del 1 al 10)'),
            ('10', 'd) Insoportable (9 a 10 en una escala del 1 al 10)'),
        ],
        'pregunta6': [
            ('constante', 'a) Constante'),
            ('varias_veces_dia', 'b) Varias veces al día'),
            ('algunas_veces_semana', 'c) Algunas veces por semana'),
            ('ocasional', 'd) Ocasional'),
        ],
        'pregunta7': [
            ('punzante', 'a) Punzante (como un pinchazo agudo)'),
            ('ardor', 'b) Ardor (sensación de quemazón)'),
            ('presion', 'c) Presión u opresión (sensación de rigidez o carga)'),
            ('sordo', 'd) Dolor sordo (molestia profunda, continua y difícil de localizar)'),
        ],
        'pregunta8': [
            ('movimiento', 'a) Movimiento'),
            ('reposo', 'b) Reposo'),
            ('sentado_de_pie', 'c) Estar sentado o de pie mucho tiempo'),
            ('nada', 'd) Nada en particular'),
        ],
        'pregunta9': [
            ('descanso', 'a) Descanso'),
            ('calor_frio', 'b) Calor o frío'),
            ('medicacion', 'c) Medicación'),
            ('nada', 'd) Nada lo alivia'),
        ],
        'pregunta10': [
            ('no', 'a) No'),
            ('brazo', 'b) Hacia un brazo'),
            ('pierna', 'c) Hacia una pierna'),
            ('varias_zonas', 'd) Hacia varias zonas'),
        ],
        'pregunta11': [
            ('nunca', 'a) Nunca'),
            ('a_veces', 'b) A veces'),
            ('frecuentemente', 'c) Frecuentemente'),
            ('siempre', 'd) Siempre'),
        ],
        'pregunta12': [
            ('perdida_fuerza', 'a) Pérdida repentina de fuerza (se me caen objetos o me falla la pierna al caminar)'),
            ('inflamacion_severa', 'b) Inflamación severa, enrojecimiento o calor intenso en la zona'),
            ('sintomas_generales', 'c) Fiebre, mareos o malestar general asociado al dolor'),
            ('ninguno', 'd) Ninguno de los anteriores'),
        ],
        'pregunta13': [
            ('no', 'a) No'),
            ('algo_limitada', 'b) Algo limitada'),
            ('muy_limitada', 'c) Muy limitada'),
            ('no_puedo_normal', 'd) No puedo moverme con normalidad'),
        ],
        'pregunta14': [
            ('nada', 'a) Nada'),
            ('un_poco', 'b) Un poco'),
            ('bastante', 'c) Bastante'),
            ('no_puedo_realizar', 'd) No puedo realizarlas'),
        ],
        'pregunta15': [
            ('no_afecta', 'a) No me afecta'),
            ('cuesta_dormir', 'b) Me cuesta dormir'),
            ('despierta_noche', 'c) Me despierta de noche'),
            ('no_puedo_dormir', 'd) No puedo dormir'),
        ],
        'pregunta16': [
            ('ninguno', 'a) Ninguno'),
            ('medicacion', 'b) Medicación'),
            ('fisioterapia', 'c) Fisioterapia'),
            ('varios', 'd) Varios tratamientos'),
        ],
        'pregunta17': [
            ('sedentario', 'a) Sedentario (poco o nada de ejercicio físico)'),
            ('ligero', 'b) Ligero (caminatas o actividad suave 1 a 2 veces por semana)'),
            ('moderado', 'c) Moderado (ejercicio regular 3 a 4 veces por semana)'),
            ('activo', 'd) Activo / Deportista (entrenamiento frecuente 5 o más veces por semana)'),
        ],
        'pregunta18': [
            ('ninguno', 'a) Ninguno (solo espacio libre, una silla o una toalla)'),
            ('basico', 'b) Básico (colchoneta o tapete de ejercicio, compresas)'),
            ('intermedio', 'c) Intermedio (colchoneta y bandas elásticas de resistencia)'),
            ('completo', 'd) Completo (bandas elásticas, mancuernas o pelota terapéutica)'),
        ],
        'pregunta19': [
            ('disminuir_dolor', 'a) Disminuir el dolor en mi día a día'),
            ('movimiento_flexibilidad', 'b) Recuperar el rango de movimiento y flexibilidad'),
            ('fortalecer', 'c) Fortalecer la zona para evitar recaídas'),
            ('retomar_actividad', 'd) Retomar mi trabajo o actividad deportiva sin limitaciones'),
        ],
    }

    zona_afectada = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.HiddenInput,
    )
    comentario = forms.CharField(
        label='¿Hay algo más que quieras comentar?',
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        initial = dict(kwargs.pop('initial', {}) or {})
        if instance:
            initial.setdefault('zona_afectada', instance.zona_afectada)
            initial.setdefault('comentario', instance.comentario or '')
            initial.update(instance.respuestas or {})
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        for number, choices in self.QUESTION_CHOICES.items():
            self.fields[number] = forms.ChoiceField(
                label=self.QUESTION_LABELS[number],
                choices=choices,
                error_messages={'required': self.required_error},
                widget=forms.RadioSelect,
            )

    QUESTION_LABELS = {
        'pregunta1': '1. ¿Dónde sientes el dolor principalmente?',
        'pregunta2': '2. ¿Tuviste alguna lesión o golpe antes de que empezara?',
        'pregunta3': '3. ¿Desde cuándo tienes el dolor?',
        'pregunta4': '4. ¿Cómo ha evolucionado el dolor en las últimas semanas?',
        'pregunta5': '5. ¿Qué tan intenso es tu dolor ahora?',
        'pregunta6': '6. ¿Con qué frecuencia aparece?',
        'pregunta7': '7. ¿Cómo describirías el dolor?',
        'pregunta8': '8. ¿Qué empeora tu dolor?',
        'pregunta9': '9. ¿Qué lo alivia?',
        'pregunta10': '10. ¿El dolor se irradia a otra zona?',
        'pregunta11': '11. ¿Sientes hormigueo o adormecimiento?',
        'pregunta12': '12. ¿Presentas alguno de estos síntomas adicionales en la zona afectada?',
        'pregunta13': '13. ¿El dolor limita tu movilidad?',
        'pregunta14': '14. ¿Cómo afecta el dolor a tus actividades diarias?',
        'pregunta15': '15. ¿Cómo afecta el dolor a tu sueño?',
        'pregunta16': '16. ¿Has recibido tratamiento antes para este dolor?',
        'pregunta17': '17. ¿Cuál es tu nivel de actividad física habitual?',
        'pregunta18': '18. ¿Con qué implementos cuentas en casa para realizar tus ejercicios?',
        'pregunta19': '19. ¿Cuál es tu prioridad principal al iniciar este programa?',
    }

    @property
    def question_fields(self):
        return [self[number] for number in self.QUESTION_CHOICES]

    @property
    def question_sections(self):
        sections = [
            {
                'title': 'Conozcamos tu dolor',
                'hint': 'Empecemos por ubicarlo y entender cuándo comenzó.',
                'tone': 'ocean',
                'fields': range(1, 5),
            },
            {
                'title': 'Exploremos cómo se siente',
                'hint': 'Cuéntanos cómo aparece y qué cosas lo alivian o lo empeoran.',
                'tone': 'coral',
                'fields': range(5, 10),
            },
            {
                'title': 'Tu día a día',
                'hint': 'Queremos saber cómo influye en tu movimiento, tus actividades y tu descanso.',
                'tone': 'lilac',
                'fields': range(10, 16),
            },
            {
                'title': 'Tus hábitos y metas',
                'hint': 'Para terminar, comparte tus experiencias y lo que te gustaría lograr.',
                'tone': 'lime',
                'fields': range(16, 20),
            },
        ]
        return [
            {
                **section,
                'fields': [self[f'pregunta{number}'] for number in section['fields']],
            }
            for section in sections
        ]

    def save(self, *, usuario, commit=True):
        diagnostico = self.instance or Diagnostico()
        respuestas = {
            name: self.cleaned_data[name]
            for name in self.QUESTION_CHOICES
        }
        diagnostico.usuario = usuario
        diagnostico.zona_afectada = self.cleaned_data.get('zona_afectada', '').strip()
        diagnostico.respuestas = respuestas
        diagnostico.nivel_dolor = int(respuestas['pregunta5'])
        diagnostico.pregunta1 = respuestas['pregunta1']
        diagnostico.pregunta2 = respuestas['pregunta2']
        diagnostico.pregunta3 = respuestas['pregunta3']
        diagnostico.comentario = self.cleaned_data.get('comentario', '').strip()
        if commit:
            diagnostico.save()
        return diagnostico


class RescheduleSessionForm(forms.Form):
    fecha = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={'type': 'datetime-local'},
        ),
    )

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']
        if fecha <= timezone.now():
            raise forms.ValidationError('Selecciona una fecha y hora futuras.')
        return fecha


class EvaluacionClinicaForm(forms.ModelForm):
    class Meta:
        model = EvaluacionClinica
        fields = ['nivel_dolor', 'metrica', 'valor_actual', 'unidad']
        widgets = {
            'nivel_dolor': forms.NumberInput(attrs={'min': 0, 'max': 10, 'step': 1}),
            'valor_actual': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if bool(cleaned_data.get('metrica')) != (cleaned_data.get('valor_actual') is not None):
            raise forms.ValidationError('Indica juntos la métrica clínica y su valor actual.')
        if cleaned_data.get('valor_actual') is not None and not cleaned_data.get('unidad'):
            self.add_error('unidad', 'Indica la unidad de la métrica.')
        return cleaned_data


class ObjetivoTerapeuticoForm(forms.ModelForm):
    class Meta:
        model = ObjetivoTerapeutico
        fields = ['nombre', 'metrica', 'direccion', 'valor_objetivo', 'unidad']
        widgets = {'valor_objetivo': forms.NumberInput(attrs={'min': 0, 'step': '0.01'})}


class ScheduleSessionForm(forms.ModelForm):
    objetivo_terapeutico = forms.ModelChoiceField(
        queryset=ObjetivoTerapeutico.objects.none(),
        label='Objetivo del paciente',
        error_messages={'required': 'Selecciona uno de los objetivos del paciente.'},
    )

    class Meta:
        model = Sesion
        fields = [
            'fecha',
            'objetivo_terapeutico',
            'nota_objetivo',
            'duracion_minutos',
            'enlace_ubicacion',
        ]
        widgets = {
            'fecha': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local'},
            ),
            'duracion_minutos': forms.NumberInput(attrs={'min': 1, 'value': 45}),
            'nota_objetivo': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, paciente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['objetivo_terapeutico'].queryset = (
            ObjetivoTerapeutico.objects.filter(paciente=paciente)
            if paciente else ObjetivoTerapeutico.objects.none()
        )
        self.fields['duracion_minutos'].initial = 45
        self.fields['enlace_ubicacion'].required = False

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']
        if fecha <= timezone.now():
            raise forms.ValidationError('Selecciona una fecha y hora futuras.')
        return fecha


class VideoUploadForm(forms.ModelForm):
    category = forms.ChoiceField(
        choices=BODY_ZONE_CHOICES,
        label='Parte del cuerpo',
    )

    class Meta:
        model = Video
        fields = ['title', 'description', 'level', 'category', 'file', 'thumbnail']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def clean_file(self):
        video_file = self.cleaned_data['file']
        if Path(video_file.name).suffix.lower() not in {'.mp4', '.webm', '.ogg', '.ogv'}:
            raise forms.ValidationError('Usa un video MP4, WebM u OGG.')
        if video_file.size > 500 * 1024 * 1024:
            raise forms.ValidationError('El video no puede superar los 500 MB.')
        return video_file
