from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from princpal.models import Paciente


@receiver(pre_save, sender=Paciente)
def guardar_medico_anterior(sender, instance, **kwargs):
    if instance.pk:
        instance._medico_anterior_id = (
            sender.objects.filter(pk=instance.pk)
            .values_list('doctor_id', flat=True)
            .first()
        )
    else:
        instance._medico_anterior_id = None


@receiver(post_save, sender=Paciente)
def notificar_reasignacion_medico(sender, instance, **kwargs):
    medico_anterior_id = getattr(instance, '_medico_anterior_id', None)
    if not medico_anterior_id or medico_anterior_id == instance.doctor_id:
        return

    def notificar():
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'usuario_{medico_anterior_id}',
            {
                'type': 'mensajeria.revocar_acceso',
                'paciente_id': instance.pk,
            },
        )

    transaction.on_commit(notificar)
