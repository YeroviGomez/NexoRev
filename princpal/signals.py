from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver

from princpal.models import Paciente


@receiver(pre_save, sender=Paciente)
def impedir_cambio_medico_fuera_del_servicio(sender, instance, **kwargs):
    update_fields = kwargs.get('update_fields')
    if update_fields is not None and not {'doctor', 'doctor_id'}.intersection(update_fields):
        return

    doctor_anterior_id = (
        sender.objects.filter(pk=instance.pk)
        .values_list('doctor_id', flat=True)
        .first()
        if instance.pk
        else None
    )
    if doctor_anterior_id == instance.doctor_id:
        return
    if getattr(instance, '_cambio_medico_por_servicio', False):
        return
    raise ValidationError(
        'No se puede cambiar el médico directamente. Usa el servicio de asignación médica.'
    )
