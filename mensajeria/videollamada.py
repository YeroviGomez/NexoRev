import asyncio
import json
import uuid
import time
from collections import defaultdict, deque
from datetime import timedelta

from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db import IntegrityError, transaction
from django.utils import timezone

from crear_cuenta.models import Usuario
from mensajeria.models import Llamada
from mensajeria.permisos import tiene_acceso_a_paciente, usuario_de_sesion
from mensajeria.servicios import registrar_mensaje_sistema_llamada
from princpal.models import Paciente


TIEMPO_SONANDO_SEGUNDOS = 45
TIEMPO_RECONEXION_SEGUNDOS = 15
VENTANA_FRECUENCIA_SEGUNDOS = 10
MAX_EVENTOS_POR_VENTANA = 120
MAX_BYTES_MENSAJE = 64 * 1024
MAX_BYTES_SENALIZACION = 48 * 1024

_tareas_sonando = {}
_tareas_desconexion = {}
_conexiones_por_usuario = defaultdict(int)


def _grupo_usuario(user_id):
    return f'llamada_{user_id}'


def _foto_perfil_url(user):
    return user.foto_perfil.url if user and user.foto_perfil else ''


def _participantes(paciente):
    return tuple({
        user_id for user_id in (paciente.usuario_id, paciente.doctor_id)
        if user_id
    })


def _notificacion_terminada(call, motivo):
    tipo = {
        Llamada.ESTADO_RECHAZADA: 'rechazada',
        Llamada.ESTADO_CANCELADA: 'cancelada',
    }.get(call.estado, 'terminada')
    return {
        'tipo': tipo,
        'llamada_id': call.pk,
        'paciente_id': call.paciente_id,
        'motivo': motivo,
        'estado': call.estado,
    }


def _finalizar_llamada(call, estado, ahora, texto):
    call.estado = estado
    call.finalizada_en = ahora
    call.save(update_fields=['estado', 'finalizada_en'])
    registrar_mensaje_sistema_llamada(call.paciente, texto)
    return {
        'participantes': _participantes(call.paciente),
        'evento': _notificacion_terminada(call, estado),
    }


@database_sync_to_async
def _usuario_de_sesion(session):
    return usuario_de_sesion(session)


@database_sync_to_async
def _usuario_puede_recibir_llamadas(user):
    pacientes = Paciente.objects.filter(doctor=user, usuario__isnull=False)
    if user.role == Usuario.ROLE_PACIENTE:
        pacientes = Paciente.objects.filter(usuario=user, doctor__isnull=False)
    return pacientes.exists()


@database_sync_to_async
def _llamadas_entrantes(user):
    limite = timezone.now() - timedelta(seconds=TIEMPO_SONANDO_SEGUNDOS)
    llamadas = Llamada.objects.filter(
        estado=Llamada.ESTADO_SONANDO,
        creado_en__gte=limite,
    ).exclude(
        iniciador_id=user.pk,
    )
    if user.role == Usuario.ROLE_DOCTOR:
        llamadas = llamadas.filter(
            paciente__doctor=user,
            paciente__usuario__isnull=False,
        )
    else:
        llamadas = llamadas.filter(
            paciente__usuario=user,
            paciente__doctor__isnull=False,
        )

    eventos = []
    for llamada in llamadas.select_related('iniciador').order_by('creado_en', 'pk'):
        expira_en = llamada.creado_en + timedelta(
            seconds=TIEMPO_SONANDO_SEGUNDOS,
        )
        eventos.append({
            'llamada_id': llamada.pk,
            'paciente_id': llamada.paciente_id,
            'iniciador_nombre': (
                llamada.iniciador.nombre
                if llamada.iniciador_id
                else 'Paciente o médico'
            ),
            'iniciador_foto': _foto_perfil_url(llamada.iniciador),
            'expira_en': expira_en.isoformat(),
        })
    return eventos


@database_sync_to_async
def _crear_llamada(user, paciente_id):
    try:
        with transaction.atomic():
            paciente = Paciente.objects.select_for_update().filter(
                pk=paciente_id,
            ).first()
            if not paciente or not tiene_acceso_a_paciente(user, paciente):
                return {'error': 'No tienes permiso para llamar a este paciente.', 'status': 403}
            if not paciente.usuario_id or not paciente.doctor_id:
                return {'error': 'El paciente necesita una cuenta y un médico asignado.', 'status': 409}

            ahora = timezone.now()
            activa = Llamada.objects.select_for_update().filter(
                paciente=paciente,
                estado__in=Llamada.ESTADOS_ACTIVOS,
            ).first()
            expiracion = None
            if activa and activa.estado == Llamada.ESTADO_SONANDO and (
                ahora - activa.creado_en >= timedelta(seconds=TIEMPO_SONANDO_SEGUNDOS)
            ):
                expiracion = _finalizar_llamada(
                    activa,
                    Llamada.ESTADO_PERDIDA,
                    ahora,
                    'Llamada perdida',
                )
                activa = None
            if activa:
                return {'ocupado': True, 'expiracion': expiracion}

            llamada = Llamada.objects.create(
                paciente=paciente,
                iniciador=user,
                estado=Llamada.ESTADO_SONANDO,
            )
            destinatario_id = (
                paciente.doctor_id
                if user.role == Usuario.ROLE_PACIENTE
                else paciente.usuario_id
            )
            destinatario = Usuario.objects.get(pk=destinatario_id)
            return {
                'llamada_id': llamada.pk,
                'paciente_id': paciente.pk,
                'iniciador_id': user.pk,
                'iniciador_nombre': user.nombre,
                'iniciador_foto': _foto_perfil_url(user),
                'destinatario_id': destinatario.pk,
                'destinatario_nombre': destinatario.nombre,
                'destinatario_foto': _foto_perfil_url(destinatario),
                'creado_en': llamada.creado_en.isoformat(),
                'expiracion': expiracion,
            }
    except IntegrityError:
        return {'ocupado': True}


def _bloquear_llamada(llamada_id):
    paciente_id = Llamada.objects.filter(
        pk=llamada_id,
    ).values_list('paciente_id', flat=True).first()
    if not paciente_id:
        return None, None
    paciente = Paciente.objects.select_for_update().filter(pk=paciente_id).first()
    if not paciente:
        return None, None
    llamada = Llamada.objects.select_for_update().filter(
        pk=llamada_id,
        paciente=paciente,
    ).first()
    if llamada:
        llamada.paciente = paciente
    return paciente, llamada


@database_sync_to_async
def _aceptar_llamada(user, llamada_id):
    with transaction.atomic():
        paciente, llamada = _bloquear_llamada(llamada_id)
        if not llamada or not tiene_acceso_a_paciente(user, llamada.paciente):
            return {'error': 'No tienes permiso para aceptar esta llamada.', 'status': 403}
        if llamada.estado != Llamada.ESTADO_SONANDO:
            return {'error': 'La llamada ya no está disponible.', 'status': 409}
        ahora = timezone.now()
        if ahora - llamada.creado_en >= timedelta(seconds=TIEMPO_SONANDO_SEGUNDOS):
            expiracion = _finalizar_llamada(
                llamada,
                Llamada.ESTADO_PERDIDA,
                ahora,
                'Llamada perdida',
            )
            return {'expirada': expiracion}
        if llamada.iniciador_id == user.pk:
            return {'error': 'Solo la otra persona puede aceptar la llamada.', 'status': 403}

        llamada.estado = Llamada.ESTADO_EN_CURSO
        llamada.contestada_en = ahora
        llamada.save(update_fields=['estado', 'contestada_en'])
        return {
            'participantes': _participantes(llamada.paciente),
            'evento': {
                'tipo': 'aceptada',
                'llamada_id': llamada.pk,
                'paciente_id': llamada.paciente_id,
                'iniciador_id': llamada.iniciador_id,
                'aceptada_por': user.pk,
            },
        }


@database_sync_to_async
def _cambiar_estado(user, llamada_id, accion):
    with transaction.atomic():
        paciente, llamada = _bloquear_llamada(llamada_id)
        if not llamada or not tiene_acceso_a_paciente(user, llamada.paciente):
            return {'error': 'No tienes permiso para controlar esta llamada.', 'status': 403}

        ahora = timezone.now()
        if accion in {'rechazar', 'cancelar'}:
            if llamada.estado != Llamada.ESTADO_SONANDO:
                return {'error': 'La llamada ya no está sonando.', 'status': 409}
            if accion == 'rechazar':
                if llamada.iniciador_id == user.pk:
                    return {'error': 'El iniciador no puede rechazar su propia llamada.', 'status': 403}
                estado = Llamada.ESTADO_RECHAZADA
                texto = 'Videollamada rechazada'
            else:
                if llamada.iniciador_id != user.pk:
                    return {'error': 'Solo quien inició puede cancelar la llamada.', 'status': 403}
                estado = Llamada.ESTADO_CANCELADA
                texto = 'Videollamada cancelada'
        else:
            if llamada.estado != Llamada.ESTADO_EN_CURSO:
                return {'error': 'La llamada no está en curso.', 'status': 409}
            estado = Llamada.ESTADO_FINALIZADA
            if llamada.contestada_en:
                segundos = max(int((ahora - llamada.contestada_en).total_seconds()), 0)
                minutos, resto = divmod(segundos, 60)
                texto = f'Videollamada de {minutos}:{resto:02d}'
            else:
                texto = 'Videollamada finalizada'

        motivo = {
            Llamada.ESTADO_RECHAZADA: 'rechazada',
            Llamada.ESTADO_CANCELADA: 'cancelada',
            Llamada.ESTADO_FINALIZADA: 'finalizada',
        }[estado]
        return _finalizar_llamada(llamada, estado, ahora, texto)


@database_sync_to_async
def _reenviar_senal(user, llamada_id, tipo):
    with transaction.atomic():
        paciente, llamada = _bloquear_llamada(llamada_id)
        if (
            not llamada
            or llamada.estado != Llamada.ESTADO_EN_CURSO
            or not tiene_acceso_a_paciente(user, paciente)
        ):
            return {'error': 'No tienes permiso para enviar señalización.', 'status': 403}
        if tipo == 'offer' and llamada.iniciador_id != user.pk:
            return {'error': 'Solo quien inició puede enviar la oferta.', 'status': 403}
        if tipo == 'answer' and llamada.iniciador_id == user.pk:
            return {'error': 'Solo quien recibió puede responder la oferta.', 'status': 403}
        destinatario_id = (
            paciente.doctor_id
            if user.pk == paciente.usuario_id
            else paciente.usuario_id
        )
        if not destinatario_id or destinatario_id == user.pk:
            return {'error': 'La llamada ya no tiene dos participantes válidos.', 'status': 409}
        return {'destinatario_id': destinatario_id, 'paciente_id': paciente.pk}


@database_sync_to_async
def _llamadas_activas_de_usuario(user):
    return list(
        Llamada.objects.filter(
            estado__in=Llamada.ESTADOS_ACTIVOS,
        ).filter(
            # La comprobación de participantes se hace contra la asignación vigente.
            paciente__doctor_id=user.pk,
        ).values_list('pk', flat=True)
    ) + list(
        Llamada.objects.filter(
            estado__in=Llamada.ESTADOS_ACTIVOS,
            paciente__usuario_id=user.pk,
        ).values_list('pk', flat=True)
    )


@database_sync_to_async
def _terminar_si_activa(llamada_id, esperado, estado, texto):
    with transaction.atomic():
        paciente, llamada = _bloquear_llamada(llamada_id)
        if not llamada or llamada.estado != esperado:
            return None
        return _finalizar_llamada(llamada, estado, timezone.now(), texto)


async def _enviar_a_usuarios(channel_layer, user_ids, payload):
    for user_id in set(user_ids):
        await channel_layer.group_send(
            _grupo_usuario(user_id),
            {'type': 'videollamada.evento', 'payload': payload},
        )


def finalizar_llamadas_por_reasignacion(paciente, ahora=None):
    ahora = ahora or timezone.now()
    resultados = []
    for llamada in Llamada.objects.select_for_update().filter(
        paciente=paciente,
        estado__in=Llamada.ESTADOS_ACTIVOS,
    ):
        resultado = _finalizar_llamada(
            llamada,
            Llamada.ESTADO_FINALIZADA,
            ahora,
            'Videollamada finalizada por cambio de médico',
        )
        resultado['evento']['motivo'] = 'acceso_revocado'
        resultados.append(resultado)

    if resultados:
        def publicar():
            channel_layer = get_channel_layer()
            for resultado in resultados:
                for user_id in resultado['participantes']:
                    async_to_sync(channel_layer.group_send)(
                        _grupo_usuario(user_id),
                        {
                            'type': 'videollamada.evento',
                            'payload': resultado['evento'],
                        },
                    )

        transaction.on_commit(publicar)


async def _expirar_llamada(channel_layer, llamada_id):
    try:
        await asyncio.sleep(TIEMPO_SONANDO_SEGUNDOS)
        resultado = await _terminar_si_activa(
            llamada_id,
            Llamada.ESTADO_SONANDO,
            Llamada.ESTADO_PERDIDA,
            'Llamada perdida',
        )
        if resultado:
            await _enviar_a_usuarios(
                channel_layer,
                resultado['participantes'],
                resultado['evento'],
            )
    finally:
        _tareas_sonando.pop(llamada_id, None)


async def _expirar_desconexion(channel_layer, llamada_id, user_id):
    try:
        await asyncio.sleep(TIEMPO_RECONEXION_SEGUNDOS)
        if _conexiones_por_usuario.get(user_id, 0):
            return
        resultado = await _terminar_si_activa(
            llamada_id,
            Llamada.ESTADO_EN_CURSO,
            Llamada.ESTADO_FINALIZADA,
            'Videollamada finalizada por desconexión',
        )
        if resultado:
            evento = {**resultado['evento'], 'motivo': 'desconexion'}
            await _enviar_a_usuarios(channel_layer, resultado['participantes'], evento)
    finally:
        key = (llamada_id, user_id)
        if _tareas_desconexion.get(key) is asyncio.current_task():
            _tareas_desconexion.pop(key, None)


class VideollamadaConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = await _usuario_de_sesion(self.scope['session'])
        if not self.user or self.user.role not in {
            Usuario.ROLE_PACIENTE,
            Usuario.ROLE_DOCTOR,
        } or not await _usuario_puede_recibir_llamadas(self.user):
            await self.close(code=4403)
            return

        self.user_group = _grupo_usuario(self.user.pk)
        self.connection_id = uuid.uuid4().hex
        self.message_timestamps = deque()
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        _conexiones_por_usuario[self.user.pk] += 1
        for key, task in list(_tareas_desconexion.items()):
            if key[1] == self.user.pk:
                task.cancel()
                _tareas_desconexion.pop(key, None)
        await self.accept()
        await self.send_json({
            'tipo': 'conectado',
            'conexion_id': self.connection_id,
        })
        for llamada in await _llamadas_entrantes(self.user):
            llamada_id = llamada['llamada_id']
            if llamada_id not in _tareas_sonando:
                _tareas_sonando[llamada_id] = asyncio.create_task(
                    _expirar_llamada(self.channel_layer, llamada_id),
                )
            await self.send_json({
                'tipo': 'entrante',
                **llamada,
            })

    async def disconnect(self, close_code):
        if not hasattr(self, 'user_group'):
            return
        await self.channel_layer.group_discard(self.user_group, self.channel_name)
        _conexiones_por_usuario[self.user.pk] = max(
            _conexiones_por_usuario.get(self.user.pk, 1) - 1,
            0,
        )
        if _conexiones_por_usuario[self.user.pk] == 0:
            for llamada_id in await _llamadas_activas_de_usuario(self.user):
                key = (llamada_id, self.user.pk)
                previous = _tareas_desconexion.get(key)
                if previous:
                    previous.cancel()
                _tareas_desconexion[key] = asyncio.create_task(
                    _expirar_desconexion(
                        self.channel_layer,
                        llamada_id,
                        self.user.pk,
                    ),
                )

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None or text_data is None:
            await self._send_error('Envía un objeto JSON de texto válido.')
            return
        if len(text_data.encode('utf-8')) > MAX_BYTES_MENSAJE:
            await self._send_error('El evento supera el tamaño permitido.')
            return
        try:
            content = json.loads(text_data)
        except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
            await self._send_error('El evento no contiene JSON válido.')
            return
        await self.receive_json(content)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self._send_error('El evento debe ser un objeto JSON.')
            return
        try:
            size = len(json.dumps(content, ensure_ascii=False).encode('utf-8'))
        except (TypeError, ValueError):
            await self._send_error('El evento no tiene un formato JSON válido.')
            return
        if size > MAX_BYTES_MENSAJE:
            await self._send_error('El evento supera el tamaño permitido.')
            return
        if not self._within_rate_limit():
            await self._send_error('Enviaste demasiadas señales; espera un momento.')
            return

        user = await _usuario_de_sesion(self.scope['session'])
        if not user or user.pk != self.user.pk:
            await self.close(code=4401)
            return
        self.user = user

        tipo = content.get('tipo')
        expected = {
            'invitar': {'tipo', 'paciente_id'},
            'aceptar': {'tipo', 'llamada_id'},
            'rechazar': {'tipo', 'llamada_id'},
            'cancelar': {'tipo', 'llamada_id'},
            'offer': {'tipo', 'llamada_id', 'description'},
            'answer': {'tipo', 'llamada_id', 'description'},
            'ice': {'tipo', 'llamada_id', 'candidate'},
            'estado_medios': {
                'tipo',
                'llamada_id',
                'camara_activa',
                'microfono_activo',
            },
            'colgar': {'tipo', 'llamada_id'},
        }
        if tipo not in expected or set(content) != expected[tipo]:
            await self._send_error('El evento contiene campos inválidos.')
            return

        identifier = content.get('paciente_id') if tipo == 'invitar' else content.get('llamada_id')
        if type(identifier) is not int or identifier < 1:
            await self._send_error('El identificador no es válido.')
            return
        if tipo in {'offer', 'answer'}:
            description = content.get('description')
            if not isinstance(description, dict) or description.get('type') != tipo or not isinstance(description.get('sdp'), str):
                await self._send_error('La descripción WebRTC no es válida.')
                return
            if len(json.dumps(description).encode('utf-8')) > MAX_BYTES_SENALIZACION:
                await self._send_error('La descripción WebRTC supera el tamaño permitido.')
                return
        if tipo == 'ice':
            candidate = content.get('candidate')
            if not isinstance(candidate, dict) or len(json.dumps(candidate).encode('utf-8')) > 8192:
                await self._send_error('El candidato ICE no es válido.')
                return
        if tipo == 'estado_medios' and (
            type(content.get('camara_activa')) is not bool
            or type(content.get('microfono_activo')) is not bool
        ):
            await self._send_error('El estado de cámara y micrófono no es válido.')
            return

        if tipo == 'invitar':
            await self._invite(identifier)
        elif tipo == 'aceptar':
            await self._accept(identifier)
        elif tipo in {'rechazar', 'cancelar', 'colgar'}:
            await self._end(identifier, tipo)
        else:
            await self._relay_signal(identifier, tipo, content)

    def _within_rate_limit(self):
        now = time.monotonic()
        while (
            self.message_timestamps
            and now - self.message_timestamps[0] >= VENTANA_FRECUENCIA_SEGUNDOS
        ):
            self.message_timestamps.popleft()
        if len(self.message_timestamps) >= MAX_EVENTOS_POR_VENTANA:
            return False
        self.message_timestamps.append(now)
        return True

    async def _invite(self, paciente_id):
        resultado = await _crear_llamada(self.user, paciente_id)
        expiracion = resultado.pop('expiracion', None)
        if expiracion:
            await _enviar_a_usuarios(
                self.channel_layer,
                expiracion['participantes'],
                expiracion['evento'],
            )
        if resultado.get('error'):
            await self._send_error(resultado['error'])
            return
        if resultado.get('ocupado'):
            await self.send_json({'tipo': 'ocupado', 'paciente_id': paciente_id})
            return
        llamada_id = resultado['llamada_id']
        incoming = {
            'tipo': 'entrante',
            'llamada_id': llamada_id,
            'paciente_id': resultado['paciente_id'],
            'iniciador_id': resultado['iniciador_id'],
            'iniciador_nombre': resultado['iniciador_nombre'],
            'iniciador_foto': resultado['iniciador_foto'],
            'expira_en': (
                timezone.now() + timedelta(seconds=TIEMPO_SONANDO_SEGUNDOS)
            ).isoformat(),
        }
        await self.channel_layer.group_send(
            _grupo_usuario(resultado['destinatario_id']),
            {'type': 'videollamada.evento', 'payload': incoming},
        )
        await self.send_json({
            'tipo': 'sonando',
            'llamada_id': llamada_id,
            'paciente_id': resultado['paciente_id'],
            'destinatario_nombre': resultado['destinatario_nombre'],
            'destinatario_foto': resultado['destinatario_foto'],
            'expira_en': incoming['expira_en'],
        })
        _tareas_sonando[llamada_id] = asyncio.create_task(
            _expirar_llamada(self.channel_layer, llamada_id),
        )

    async def _accept(self, llamada_id):
        resultado = await _aceptar_llamada(self.user, llamada_id)
        if resultado.get('expirada'):
            await _enviar_a_usuarios(
                self.channel_layer,
                resultado['expirada']['participantes'],
                resultado['expirada']['evento'],
            )
            await self._send_error('La invitación expiró.')
            return
        if resultado.get('error'):
            await self._send_error(resultado['error'])
            return
        task = _tareas_sonando.pop(llamada_id, None)
        if task:
            task.cancel()
        resultado['evento']['aceptada_conexion'] = self.connection_id
        await _enviar_a_usuarios(
            self.channel_layer,
            resultado['participantes'],
            resultado['evento'],
        )

    async def _end(self, llamada_id, accion):
        estado_accion = 'finalizar' if accion == 'colgar' else accion
        resultado = await _cambiar_estado(self.user, llamada_id, estado_accion)
        if resultado.get('error'):
            await self._send_error(resultado['error'])
            return
        task = _tareas_sonando.pop(llamada_id, None)
        if task:
            task.cancel()
        await _enviar_a_usuarios(
            self.channel_layer,
            resultado['participantes'],
            resultado['evento'],
        )

    async def _relay_signal(self, llamada_id, tipo, content):
        if tipo in {'offer', 'answer'}:
            value = content['description']
        elif tipo == 'ice':
            value = content['candidate']
        else:
            value = {
                'camara_activa': content['camara_activa'],
                'microfono_activo': content['microfono_activo'],
            }
        if len(json.dumps(value).encode('utf-8')) > MAX_BYTES_SENALIZACION:
            await self._send_error('La señalización supera el tamaño permitido.')
            return
        resultado = await _reenviar_senal(self.user, llamada_id, tipo)
        if resultado.get('error'):
            await self._send_error(resultado['error'])
            return
        payload = {
            'tipo': tipo,
            'llamada_id': llamada_id,
            'paciente_id': resultado['paciente_id'],
            'from_user_id': self.user.pk,
        }
        if tipo in {'offer', 'answer'}:
            payload['description'] = value
        elif tipo == 'ice':
            payload['candidate'] = value
        else:
            payload.update(value)
        await self.channel_layer.group_send(
            _grupo_usuario(resultado['destinatario_id']),
            {'type': 'videollamada.evento', 'payload': payload},
        )

    async def videollamada_evento(self, event):
        await self.send_json(event['payload'])

    async def _send_error(self, message):
        await self.send_json({'tipo': 'error', 'mensaje': message})
