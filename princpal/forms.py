from django import forms
from pathlib import Path

from .models import Diagnostico, Video


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
