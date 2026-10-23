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

class DiagnosticoForm(forms.ModelForm):
    required_error = 'Este campo es obligatorio.'

    class Meta:
        model = Diagnostico
        fields = ['nivel_dolor', 'pregunta1', 'pregunta2', 'pregunta3', 'comentario']

    nivel_dolor = forms.IntegerField(
        label='Nivel de dolor',
        min_value=0,
        max_value=10,
        error_messages={'required': required_error},
        widget=forms.NumberInput(attrs={
            'type': 'range',
            'min': '0',
            'max': '10',
            'value': '0',
            'id': 'nivelDolor',
        }),
    )

    pregunta1 = forms.ChoiceField(
        label='\u00bfQu\u00e9 parte del cuerpo trabaj\u00f3 m\u00e1s en fisioterapia?',
        choices=[('espalda', 'Espalda'), ('piernas', 'Piernas'), ('brazos', 'Brazos')],
        error_messages={'required': required_error},
        widget=forms.RadioSelect,
    )

    pregunta2 = forms.CharField(
        label='Describa brevemente su experiencia',
        error_messages={'required': required_error},
        widget=forms.Textarea,
    )

    pregunta3 = forms.ChoiceField(
        label='\u00bfHa sentido mejor\u00eda?',
        choices=[('si', 'S\u00ed'), ('no', 'No')],
        error_messages={'required': required_error},
        widget=forms.RadioSelect,
    )


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
