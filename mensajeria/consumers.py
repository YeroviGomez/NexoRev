from collections import deque
import time

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.db import transaction
from django.utils import timezone

from crear_cuenta.models import Usuario
from mensajeria.models import Mensaje
from mensajeria.permisos import (
    pacientes_conversables,
    tiene_acceso_a_paciente,
    usuario_de_sesion,
)
from mensajeria.servicios import (
    mensajes_no_leidos,
    publicar_a_participantes,
    publicar_contadores_a_participantes,
    resumen_no_leidos,
)
from princpal.models import Paciente


class MensajeriaConsumer(JsonWebsocketConsumer):
    max_mensajes_por_ventana = 20
    ventana_frecuencia_segundos = 10

    def connect(self):
        self.user = usuario_de_sesion(self.scope['session'])
        primer_paciente = (
            pacientes_conversables(self.user)
            .select_related('usuario', 'doctor')
            .first()
            if self.user else None
        )
        if (
            not self.user
            or not primer_paciente
            or not tiene_acceso_a_paciente(self.user, primer_paciente)
        ):
            self.close(code=4403)
            return

        self.user_group = f'usuario_{self.user.pk}'
        self.active_patient_ids = set()
        self.message_timestamps = deque()
        async_to_sync(self.channel_layer.group_add)(self.user_group, self.channel_name)
        self.accept()
        self.send_json(resumen_no_leidos(self.user))

    def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            async_to_sync(self.channel_layer.group_discard)(
                self.user_group,
                self.channel_name,
            )

    def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            self._send_error('Solicitud inválida.')
            return
        if not self._within_rate_limit():
            self.close(code=4429)
            return

        user = usuario_de_sesion(self.scope['session'])
        if not user or user.pk != self.user.pk:
            self.close(code=4401)
            return
        self.user = user

        tipo = content.get('tipo')
        paciente_id = content.get('paciente_id')
        if tipo not in {'abrir', 'enviar', 'leer'} or type(paciente_id) is not int:
            self._send_error('Solicitud inválida.')
            return

        paciente = (
            Paciente.objects.select_related('usuario', 'doctor')
            .filter(pk=paciente_id)
            .first()
        )
        if not paciente or not tiene_acceso_a_paciente(user, paciente):
            self.close(code=4403)
            return
        self.active_patient_ids.add(paciente.pk)

        if tipo == 'abrir':
            return
        if tipo == 'leer':
            self._marcar_leidos(paciente)
            return
        self._enviar_mensaje(content.get('texto'), paciente.pk)

    def _within_rate_limit(self):
        now = time.monotonic()
        while (
            self.message_timestamps
            and now - self.message_timestamps[0] >= self.ventana_frecuencia_segundos
        ):
            self.message_timestamps.popleft()
        if len(self.message_timestamps) >= self.max_mensajes_por_ventana:
            return False
        self.message_timestamps.append(now)
        return True

    def _enviar_mensaje(self, texto, paciente_id):
        if not isinstance(texto, str):
            self._send_error('El mensaje debe ser texto.')
            return
        texto = texto.strip()
        if not texto or len(texto) > 2000:
            self._send_error('El mensaje debe tener entre 1 y 2000 caracteres.')
            return

        with transaction.atomic():
            paciente = Paciente.objects.select_for_update().filter(pk=paciente_id).first()
            if not paciente or not tiene_acceso_a_paciente(self.user, paciente):
                self.close(code=4403)
                return
            mensaje = Mensaje.objects.create(
                paciente=paciente,
                autor=self.user,
                texto=texto,
            )
        payload = {
            'tipo': 'mensaje',
            'paciente_id': paciente.pk,
            'id': mensaje.pk,
            'autor_id': self.user.pk,
            'texto': mensaje.texto,
            'creado_en': mensaje.creado_en.isoformat(),
        }
        publicar_a_participantes(paciente, payload)
        self._send_unread_counts(paciente)

    def _marcar_leidos(self, paciente):
        with transaction.atomic():
            paciente = Paciente.objects.select_for_update().filter(pk=paciente.pk).first()
            if not paciente or not tiene_acceso_a_paciente(self.user, paciente):
                self.close(code=4403)
                return
            leido_en = timezone.now()
            pendientes = mensajes_no_leidos(self.user, paciente)
            mensajes_ids = list(pendientes.values_list('pk', flat=True))
            pendientes.update(leido_en=leido_en)
        publicar_a_participantes(
            paciente,
            {
                'tipo': 'leido',
                'paciente_id': paciente.pk,
                'leido_por': self.user.pk,
                'leido_en': leido_en.isoformat(),
                'mensajes_ids': mensajes_ids,
            },
        )
        self._send_unread_counts(paciente)

    def _send_unread_counts(self, paciente):
        publicar_contadores_a_participantes(paciente)

    def mensajeria_evento(self, event):
        self.send_json(event['payload'])

    def mensajeria_revocar_acceso(self, event):
        paciente_id = event.get('paciente_id')
        if paciente_id not in self.active_patient_ids:
            return
        paciente = Paciente.objects.filter(pk=paciente_id).first()
        user = usuario_de_sesion(self.scope['session'])
        if not user or not paciente or not tiene_acceso_a_paciente(user, paciente):
            self.close(code=4403)
            return

    def _send_error(self, message):
        self.send_json({'tipo': 'error', 'mensaje': message})
