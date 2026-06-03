from django import forms
from .models import Diagnostico

class DiagnosticoForm(forms.ModelForm):
    class Meta:
        model = Diagnostico
        fields = ['nivel_dolor', 'pregunta1', 'pregunta2', 'pregunta3', 'comentario']

    nivel_dolor = forms.IntegerField(
        label="Nivel de dolor",
        widget=forms.NumberInput(attrs={
            'type': 'range',
            'min': '1',
            'max': '10',
            'value': '1',
            'id': 'nivelDolor',
        })
    )

    pregunta1 = forms.ChoiceField(
        label="¿Qué parte del cuerpo trabajó más en fisioterapia?",
        choices=[('espalda', 'Espalda'), ('piernas', 'Piernas'), ('brazos', 'Brazos')],
        widget=forms.RadioSelect
    )

    pregunta2 = forms.CharField(
        label="Describa brevemente su experiencia",
        widget=forms.Textarea
    )

    pregunta3 = forms.ChoiceField(
        label="¿Ha sentido mejoría?",
        choices=[('si', 'Sí'), ('no', 'No')],
        widget=forms.RadioSelect
    )
