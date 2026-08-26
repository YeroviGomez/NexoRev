from django import forms


class FotoPerfilForm(forms.Form):
    foto = forms.ImageField(label='Foto de perfil')

    def clean_foto(self):
        foto = self.cleaned_data['foto']
        if foto.size > 5 * 1024 * 1024:
            raise forms.ValidationError('La imagen no debe superar 5 MB.')
        return foto

from .models import Diagnostico


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
