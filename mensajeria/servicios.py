from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Count, Q

from crear_cuenta.models import Usuario
from mensajeria.models import Mensaje
from mensajeria.permisos import pacientes_conversables


def mensajes_no_leidos(user, paciente=None):
    queryset = Mensaje.objects.filter(
        paciente__in=pacientes_conversables(user),
        leido_en__isnull=True,
    ).filter(Q(autor_id__isnull=True) | ~Q(autor_id=user.pk))
    if paciente is not None:
        queryset = queryset.filter(paciente=paciente)
    return queryset


def resumen_no_leidos(user):
    por_conversacion = {
        row['paciente_id']: row['total']
        for row in mensajes_no_leidos(user).values('paciente_id').annotate(total=Count('pk'))
    }
    return {
        'tipo': 'no_leidos',
        'total': sum(por_conversacion.values()),
        'por_conversacion': por_conversacion,
    }


def publicar_a_participantes(paciente, payload):
    channel_layer = get_channel_layer()
    for user_id in {paciente.usuario_id, paciente.doctor_id}:
        if user_id:
            async_to_sync(channel_layer.group_send)(
                f'usuario_{user_id}',
                {'type': 'mensajeria.evento', 'payload': payload},
            )


def publicar_contadores_a_participantes(paciente):
    channel_layer = get_channel_layer()
    for user_id in {paciente.usuario_id, paciente.doctor_id}:
        if user_id:
            user = Usuario.objects.filter(pk=user_id, is_active=True).first()
            if user:
                async_to_sync(channel_layer.group_send)(
                    f'usuario_{user_id}',
                    {
                        'type': 'mensajeria.evento',
                        'payload': resumen_no_leidos(user),
                    },
                )
