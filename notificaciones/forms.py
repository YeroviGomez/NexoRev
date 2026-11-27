from django import forms

from princpal.models import Paciente
from .models import Recordatorio


DIAS_SEMANA_CHOICES = [
    ('0', 'Lunes'),
    ('1', 'Martes'),
    ('2', 'Miércoles'),
    ('3', 'Jueves'),
    ('4', 'Viernes'),
    ('5', 'Sábado'),
    ('6', 'Domingo'),
]


class RecordatorioForm(forms.ModelForm):
    paciente = forms.ModelChoiceField(
        queryset=Paciente.objects.all(),
        label='Paciente',
    )
    hora = forms.TimeField(
        label='Hora',
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )
    dias_semana = forms.MultipleChoiceField(
        choices=DIAS_SEMANA_CHOICES,
        label='Días de la semana',
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Recordatorio
        fields = ['paciente', 'hora', 'dias_semana', 'activo']

    def clean_dias_semana(self):
        dias = self.cleaned_data['dias_semana']
        if not dias:
            raise forms.ValidationError('Selecciona al menos un día.')
        if len(dias) != len(set(dias)):
            raise forms.ValidationError('No repitas días de la semana.')
        return [int(dia) for dia in dias]

    def clean(self):
        cleaned_data = super().clean()
        paciente = cleaned_data.get('paciente')
        hora = cleaned_data.get('hora')
        activo = cleaned_data.get('activo', True)
        if not paciente or not hora or not activo:
            return cleaned_data

        recordatorios = Recordatorio.objects.filter(paciente=paciente, activo=True)
        if self.instance.pk:
            recordatorios = recordatorios.exclude(pk=self.instance.pk)

        if recordatorios.filter(hora=hora).exists():
            self.add_error('hora', 'Ya existe un recordatorio activo para esa hora.')
        if recordatorios.count() >= 3:
            self.add_error('paciente', 'El paciente ya tiene tres recordatorios activos.')
        return cleaned_data
