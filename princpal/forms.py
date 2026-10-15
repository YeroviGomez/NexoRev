from django import forms
from django.utils import timezone
from pathlib import Path

from .models import Diagnostico, EvaluacionClinica, ObjetivoTerapeutico, Sesion, Video


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
        min_value=1,
        max_value=10,
        error_messages={'required': required_error},
        widget=forms.NumberInput(attrs={
            'type': 'range',
            'min': '1',
            'max': '10',
            'value': '1',
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
            'nivel_dolor': forms.NumberInput(attrs={'min': 0, 'max': 10}),
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
    class Meta:
        model = Sesion
        fields = ['fecha', 'objetivo']
        widgets = {
            'fecha': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={'type': 'datetime-local'},
            ),
        }

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
