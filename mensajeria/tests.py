import asyncio
import json
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crear_cuenta.models import Usuario
from mensajeria.models import Llamada, Mensaje
from mensajeria.permisos import tiene_acceso_a_paciente
from princpal.servicios import reasignar_medico
from princpal.models import AsignacionMedico, Paciente


def crear_paciente_asignado(usuario, doctor, nombre, email):
    paciente = Paciente.objects.create(
        usuario=usuario,
        doctor=None,
        nombre=nombre,
        email=email,
    )
    paciente.doctor = doctor
    paciente._cambio_medico_por_servicio = True
    paciente.save(update_fields=['doctor'])
    AsignacionMedico.objects.create(
        paciente=paciente,
        doctor=doctor,
        tipo=AsignacionMedico.TIPO_INICIAL,
        inicio=timezone.now(),
        motivo='Asignación inicial de prueba.',
    )
    return paciente


class PermisosMensajeriaTests(TestCase):
    def setUp(self):
        self.paciente_usuario = Usuario.objects.create(
            email='paciente-chat@example.com',
            nombre='Paciente Chat',
            role=Usuario.ROLE_PACIENTE,
        )
        self.doctor = Usuario.objects.create(
            email='doctor-chat@example.com',
            nombre='Doctor Chat',
            role=Usuario.ROLE_DOCTOR,
        )
        self.ajeno = Usuario.objects.create(
            email='ajeno-chat@example.com',
            nombre='Usuario Ajeno',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente = crear_paciente_asignado(
            self.paciente_usuario,
            self.doctor,
            self.paciente_usuario.nombre,
            self.paciente_usuario.email,
        )

    def test_solo_los_dos_participantes_activos_tienen_acceso(self):
        self.assertTrue(tiene_acceso_a_paciente(self.paciente_usuario, self.paciente))
        self.assertTrue(tiene_acceso_a_paciente(self.doctor, self.paciente))
        self.assertFalse(tiene_acceso_a_paciente(self.ajeno, self.paciente))
        self.assertFalse(tiene_acceso_a_paciente(AnonymousUser(), self.paciente))

    def test_falta_de_usuario_o_medico_impide_el_acceso(self):
        paciente_sin_usuario = crear_paciente_asignado(
            None,
            self.doctor,
            'Sin usuario',
            'sin-usuario-chat@example.com',
        )
        paciente_sin_medico_usuario = Usuario.objects.create(
            email='sin-medico-chat@example.com',
            nombre='Sin médico',
            role=Usuario.ROLE_PACIENTE,
        )
        paciente_sin_medico = Paciente.objects.create(
            usuario=paciente_sin_medico_usuario,
            nombre='Sin médico',
            email='sin-medico-chat@example.com',
        )

        self.assertFalse(tiene_acceso_a_paciente(self.doctor, paciente_sin_usuario))
        self.assertFalse(tiene_acceso_a_paciente(self.paciente_usuario, paciente_sin_medico))
        self.assertFalse(tiene_acceso_a_paciente(self.ajeno, paciente_sin_medico))

    def test_historial_y_marcado_de_lectura_exigen_permiso_y_csrf(self):
        mensaje = Mensaje.objects.create(
            paciente=self.paciente,
            autor=self.paciente_usuario,
            texto='Consulta inicial',
        )
        cliente = Client()
        self._autenticar(cliente, self.ajeno)
        historial = cliente.get(
            reverse('mensajeria:historial', args=[self.paciente.pk])
        )
        self.assertEqual(historial.status_code, 403)

        cliente = Client(enforce_csrf_checks=True)
        self._autenticar(cliente, self.doctor)
        pagina = cliente.get(reverse('mensajeria:inicio'))
        self.assertEqual(pagina.status_code, 200)
        token = cliente.cookies['csrftoken'].value
        leidos = cliente.post(
            reverse('mensajeria:marcar_leidos', args=[self.paciente.pk]),
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(leidos.status_code, 200)
        mensaje.refresh_from_db()
        self.assertIsNotNone(mensaje.leido_en)
        self.assertEqual(leidos.json()['total'], 0)

    def test_historial_usa_cursor_y_hojas_de_cuarenta(self):
        Mensaje.objects.bulk_create([
            Mensaje(
                paciente=self.paciente,
                autor=self.paciente_usuario,
                texto=f'Mensaje {number}',
            )
            for number in range(41)
        ])
        cliente = Client()
        self._autenticar(cliente, self.paciente_usuario)

        primera = cliente.get(
            reverse('mensajeria:historial', args=[self.paciente.pk])
        ).json()
        self.assertEqual(len(primera['mensajes']), 40)
        self.assertTrue(primera['hay_mas'])
        anterior = cliente.get(
            reverse('mensajeria:historial', args=[self.paciente.pk]),
            {'antes': primera['siguiente_cursor']},
        ).json()
        self.assertEqual(len(anterior['mensajes']), 1)
        self.assertFalse(anterior['hay_mas'])

    def test_contador_del_medico_incluye_conversaciones_sin_mensajes(self):
        segunda_cuenta = Usuario.objects.create(
            email='paciente-vacio-chat@example.com',
            nombre='Paciente sin mensajes',
            role=Usuario.ROLE_PACIENTE,
        )
        crear_paciente_asignado(
            segunda_cuenta,
            self.doctor,
            segunda_cuenta.nombre,
            segunda_cuenta.email,
        )
        Mensaje.objects.create(
            paciente=self.paciente,
            autor=self.paciente_usuario,
            texto='Mensaje pendiente',
        )
        cliente = Client()
        self._autenticar(cliente, self.doctor)

        lista = cliente.get(reverse('mensajeria:conversaciones')).json()['conversaciones']
        contador = cliente.get(reverse('mensajeria:no_leidos')).json()
        self.assertEqual(len(lista), 2)
        self.assertEqual(sum(not item['ultimo_mensaje_id'] for item in lista), 1)
        self.assertEqual(contador['total'], 1)
        self.assertEqual(contador['por_conversacion'][str(self.paciente.pk)], 1)

    def test_paciente_abre_su_conversacion_y_puede_recuperar_el_historial(self):
        Mensaje.objects.create(
            paciente=self.paciente,
            autor=self.doctor,
            texto='Mensaje guardado',
        )
        cliente = Client()
        self._autenticar(cliente, self.paciente_usuario)

        pagina = cliente.get(reverse('mensajeria:inicio'))
        historial = cliente.get(
            reverse('mensajeria:historial', args=[self.paciente.pk])
        )

        self.assertContains(pagina, f'data-paciente-id="{self.paciente.pk}"')
        self.assertContains(pagina, self.doctor.nombre)
        self.assertEqual(historial.status_code, 200)
        self.assertEqual(historial.json()['mensajes'][0]['texto'], 'Mensaje guardado')

    @staticmethod
    def _autenticar(cliente, usuario):
        session = cliente.session
        session['current_user'] = usuario.email
        session['current_user_role'] = usuario.role
        session.save()


@override_settings(ALLOWED_HOSTS=['testserver'])
class MensajeriaWebsocketTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.paciente_usuario = Usuario.objects.create(
            email='paciente-ws@example.com',
            nombre='Paciente WS',
            role=Usuario.ROLE_PACIENTE,
        )
        self.doctor = Usuario.objects.create(
            email='doctor-ws@example.com',
            nombre='Doctor WS',
            role=Usuario.ROLE_DOCTOR,
        )
        self.otro_doctor = Usuario.objects.create(
            email='otro-doctor-ws@example.com',
            nombre='Otro Doctor',
            role=Usuario.ROLE_DOCTOR,
        )
        self.sin_chat = Usuario.objects.create(
            email='sin-chat-ws@example.com',
            nombre='Sin conversación',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente = crear_paciente_asignado(
            self.paciente_usuario,
            self.doctor,
            self.paciente_usuario.nombre,
            self.paciente_usuario.email,
        )
        self.otro_paciente_usuario = Usuario.objects.create(
            email='paciente-ajeno-ws@example.com',
            nombre='Paciente de otro doctor',
            role=Usuario.ROLE_PACIENTE,
        )
        self.otro_paciente = crear_paciente_asignado(
            self.otro_paciente_usuario,
            self.otro_doctor,
            self.otro_paciente_usuario.nombre,
            self.otro_paciente_usuario.email,
        )

    def _communicator(self, usuario):
        from NexoRev.asgi import application

        session = SessionStore()
        session['current_user'] = usuario.email
        session['current_user_role'] = usuario.role
        session.save()
        headers = [
            (
                b'cookie',
                f'{settings.SESSION_COOKIE_NAME}={session.session_key}'.encode(),
            ),
            (b'origin', b'http://testserver'),
        ]
        return WebsocketCommunicator(application, '/ws/mensajeria/', headers=headers)

    def test_participantes_intercambian_mensajes_y_marcan_lectura(self):
        paciente_socket = self._communicator(self.paciente_usuario)
        doctor_socket = self._communicator(self.doctor)
        async_to_sync(self._intercambiar_mensajes)(paciente_socket, doctor_socket)

        mensajes = list(Mensaje.objects.order_by('pk'))
        self.assertEqual(len(mensajes), 2)
        self.assertEqual(mensajes[0].texto, 'Hola, doctor.')
        self.assertEqual(len(mensajes[1].texto), 2000)
        self.assertTrue(all(mensaje.leido_en for mensaje in mensajes))

    async def _intercambiar_mensajes(self, paciente_socket, doctor_socket):
        paciente_conectado, _ = await paciente_socket.connect()
        doctor_conectado, _ = await doctor_socket.connect()
        self.assertTrue(paciente_conectado)
        self.assertTrue(doctor_conectado)
        await paciente_socket.receive_json_from()
        await doctor_socket.receive_json_from()

        await paciente_socket.send_json_to({
            'tipo': 'sistema',
            'paciente_id': self.paciente.pk,
            'texto': 'Mensaje de sistema falso',
        })
        self.assertEqual((await paciente_socket.receive_json_from())['tipo'], 'error')

        await paciente_socket.send_json_to({
            'tipo': 'enviar',
            'paciente_id': self.paciente.pk,
            'texto': 'Hola, doctor.',
        })
        paciente_evento = await paciente_socket.receive_json_from()
        doctor_evento = await doctor_socket.receive_json_from()
        self.assertEqual(paciente_evento['tipo'], 'mensaje')
        self.assertEqual(doctor_evento['tipo'], 'mensaje')
        self.assertEqual(doctor_evento['texto'], 'Hola, doctor.')
        paciente_no_leidos = await paciente_socket.receive_json_from()
        doctor_no_leidos = await doctor_socket.receive_json_from()
        self.assertEqual(paciente_no_leidos['tipo'], 'no_leidos')
        self.assertEqual(paciente_no_leidos['total'], 0)
        self.assertEqual(doctor_no_leidos['tipo'], 'no_leidos')
        self.assertEqual(doctor_no_leidos['total'], 1)
        self.assertEqual(
            doctor_no_leidos['por_conversacion'][str(self.paciente.pk)],
            1,
        )

        await paciente_socket.send_json_to({
            'tipo': 'enviar',
            'paciente_id': self.paciente.pk,
            'texto': '   ',
        })
        self.assertEqual((await paciente_socket.receive_json_from())['tipo'], 'error')
        await paciente_socket.send_json_to({
            'tipo': 'enviar',
            'paciente_id': self.paciente.pk,
            'texto': 'x' * 2001,
        })
        self.assertEqual((await paciente_socket.receive_json_from())['tipo'], 'error')
        await paciente_socket.send_json_to({
            'tipo': 'enviar',
            'paciente_id': self.paciente.pk,
            'texto': 'x' * 2000,
        })
        self.assertEqual((await paciente_socket.receive_json_from())['tipo'], 'mensaje')
        self.assertEqual((await doctor_socket.receive_json_from())['tipo'], 'mensaje')
        self.assertEqual((await paciente_socket.receive_json_from())['tipo'], 'no_leidos')
        self.assertEqual((await doctor_socket.receive_json_from())['total'], 2)

        await doctor_socket.send_json_to({
            'tipo': 'leer',
            'paciente_id': self.paciente.pk,
        })
        leido = await paciente_socket.receive_json_from()
        self.assertEqual(leido['tipo'], 'leido')
        doctor_leido = await doctor_socket.receive_json_from()
        self.assertEqual(doctor_leido['tipo'], 'leido')
        leido_en_guardado = await database_sync_to_async(
            lambda: Mensaje.objects.filter(leido_en__isnull=False).count() == 2
        )()
        self.assertTrue(leido_en_guardado)
        paciente_total_actualizado = await paciente_socket.receive_json_from()
        doctor_total_actualizado = await doctor_socket.receive_json_from()
        self.assertEqual(paciente_total_actualizado['tipo'], 'no_leidos')
        self.assertEqual(doctor_total_actualizado['tipo'], 'no_leidos')
        self.assertEqual(doctor_total_actualizado['total'], 0)
        await paciente_socket.disconnect()
        await doctor_socket.disconnect()

    def test_usuario_ajeno_no_conecta_ni_envia_a_otra_conversacion(self):
        sin_chat_socket = self._communicator(self.sin_chat)
        ajeno_socket = self._communicator(self.otro_doctor)
        async_to_sync(self._rechazar_usuarios_ajenos)(sin_chat_socket, ajeno_socket)
        self.assertFalse(Mensaje.objects.exists())

    async def _rechazar_usuarios_ajenos(self, sin_chat_socket, ajeno_socket):
        conectado, codigo = await sin_chat_socket.connect()
        self.assertTrue(conectado)
        await sin_chat_socket.receive_json_from()
        await sin_chat_socket.send_json_to({
            'tipo': 'abrir',
            'paciente_id': self.paciente.pk,
        })
        cierre_sin_chat = await sin_chat_socket.receive_output(timeout=2)
        self.assertEqual(cierre_sin_chat['type'], 'websocket.close')
        self.assertEqual(cierre_sin_chat['code'], 4403)

        conectado, _ = await ajeno_socket.connect()
        self.assertTrue(conectado)
        await ajeno_socket.receive_json_from()
        await ajeno_socket.send_json_to({
            'tipo': 'enviar',
            'paciente_id': self.paciente.pk,
            'texto': 'No autorizado',
        })
        cierre = await ajeno_socket.receive_output(timeout=2)
        self.assertEqual(cierre['type'], 'websocket.close')
        self.assertEqual(cierre['code'], 4403)

    def test_paciente_sin_medico_conecta_para_recibir_la_asignacion_en_vivo(self):
        usuario = Usuario.objects.create(
            email='sin-medico-ws@example.com',
            nombre='Sin médico',
            role=Usuario.ROLE_PACIENTE,
        )
        Paciente.objects.create(
            usuario=usuario,
            doctor=None,
            nombre='Sin médico',
            email=usuario.email,
        )
        socket = self._communicator(usuario)
        async_to_sync(self._conectar_paciente_sin_medico)(socket)

    async def _conectar_paciente_sin_medico(self, socket):
        conectado, _ = await socket.connect()
        self.assertTrue(conectado)
        resumen = await socket.receive_json_from()
        self.assertEqual(resumen['tipo'], 'no_leidos')
        await socket.disconnect()

    def test_reasignar_medico_revoca_el_chat_y_actualiza_el_contador_anterior(self):
        admin = get_user_model().objects.create_user(
            username='admin-revoca-chat',
            password='test-password',
            is_staff=True,
        )
        socket = self._communicator(self.doctor)
        async_to_sync(self._revocar_chat_tras_reasignacion)(socket, admin)

    async def _revocar_chat_tras_reasignacion(self, socket, admin):
        conectado, _ = await socket.connect()
        self.assertTrue(conectado)
        await socket.receive_json_from()
        await socket.send_json_to({
            'tipo': 'enviar',
            'paciente_id': self.paciente.pk,
            'texto': 'Mensaje antes de la reasignación.',
        })
        self.assertEqual((await socket.receive_json_from())['tipo'], 'mensaje')
        self.assertEqual((await socket.receive_json_from())['tipo'], 'no_leidos')

        def reasignar():
            reasignar_medico(
                paciente=Paciente.objects.get(pk=self.paciente.pk),
                nuevo_doctor=self.otro_doctor,
                tipo=AsignacionMedico.TIPO_CONTINUIDAD,
                motivo='Cambio de médico de prueba.',
                compartir_historial_clinico=False,
                paciente_autorizo=False,
                admin=admin,
            )

        await database_sync_to_async(reasignar)()
        revocacion = await socket.receive_output(timeout=2)
        self.assertEqual(revocacion['type'], 'websocket.send')
        payload = json.loads(revocacion['text'])
        self.assertEqual(payload['tipo'], 'acceso_revocado')
        self.assertEqual(payload['paciente_id'], self.paciente.pk)
        contador = await socket.receive_json_from(timeout=2)
        self.assertEqual(contador['tipo'], 'no_leidos')
        self.assertEqual(contador['total'], 0)
        await socket.send_json_to({
            'tipo': 'enviar',
            'paciente_id': self.paciente.pk,
            'texto': 'Intento posterior a la reasignación.',
        })
        cierre = await socket.receive_output(timeout=2)
        self.assertEqual(cierre['type'], 'websocket.close')
        self.assertEqual(cierre['code'], 4403)
        await socket.disconnect()

    def test_reasignacion_notifica_en_vivo_a_paciente_y_medicos(self):
        admin = get_user_model().objects.create_user(
            username='admin-websocket',
            password='test-password',
            is_staff=True,
        )
        paciente_socket = self._communicator(self.paciente_usuario)
        doctor_anterior_socket = self._communicator(self.doctor)
        doctor_nuevo_socket = self._communicator(self.otro_doctor)
        async_to_sync(self._recibir_notificacion_reasignacion)(
            paciente_socket,
            doctor_anterior_socket,
            doctor_nuevo_socket,
            admin,
        )

    async def _recibir_notificacion_reasignacion(
        self,
        paciente_socket,
        doctor_anterior_socket,
        doctor_nuevo_socket,
        admin,
    ):
        for socket in (paciente_socket, doctor_anterior_socket, doctor_nuevo_socket):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            self.assertEqual((await socket.receive_json_from())['tipo'], 'no_leidos')

        def reasignar():
            reasignar_medico(
                paciente=Paciente.objects.get(pk=self.paciente.pk),
                nuevo_doctor=self.otro_doctor,
                tipo='continuidad',
                motivo='Cambio en tiempo real.',
                compartir_historial_clinico=False,
                paciente_autorizo=False,
                admin=admin,
            )

        await database_sync_to_async(reasignar)()

        revocacion = await doctor_anterior_socket.receive_json_from(timeout=2)
        self.assertEqual(revocacion['tipo'], 'acceso_revocado')
        self.assertEqual(revocacion['paciente_id'], self.paciente.pk)
        evento_paciente = await paciente_socket.receive_json_from(timeout=2)
        evento_doctor = await doctor_nuevo_socket.receive_json_from(timeout=2)
        self.assertEqual(evento_paciente['tipo'], 'cambio_medico')
        self.assertEqual(evento_doctor['tipo'], 'cambio_medico')
        self.assertEqual(evento_paciente['mensaje']['tipo_mensaje'], Mensaje.TIPO_SISTEMA)
        self.assertEqual(
            evento_paciente['mensaje']['texto'],
            'Tu médico ha cambiado. Ahora te atiende Dr. Otro Doctor.',
        )
        self.assertEqual(
            evento_doctor['mensaje_medico']['texto'],
            'Cambio de médico: el paciente ahora es atendido por Dr. Otro Doctor.',
        )

        contador_anterior = await doctor_anterior_socket.receive_json_from(timeout=2)
        contador_paciente = await paciente_socket.receive_json_from(timeout=2)
        contador_nuevo = await doctor_nuevo_socket.receive_json_from(timeout=2)
        self.assertEqual(contador_anterior['total'], 0)
        self.assertEqual(contador_paciente['total'], 1)
        mensajes_nuevos = await database_sync_to_async(
            lambda: list(Mensaje.objects.filter(
                paciente__doctor=self.otro_doctor,
                leido_en__isnull=True,
            ).values_list('texto', flat=True))
        )()
        self.assertEqual(contador_nuevo['total'], 1, mensajes_nuevos)
        for socket in (paciente_socket, doctor_anterior_socket, doctor_nuevo_socket):
            await socket.disconnect()


@override_settings(ALLOWED_HOSTS=['testserver'])
class VideollamadaTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.paciente_usuario = Usuario.objects.create(
            email='paciente-video@example.com',
            nombre='Paciente Video',
            role=Usuario.ROLE_PACIENTE,
        )
        self.doctor = Usuario.objects.create(
            email='doctor-video@example.com',
            nombre='Doctora Video',
            role=Usuario.ROLE_DOCTOR,
        )
        self.otro_doctor = Usuario.objects.create(
            email='otro-doctor-video@example.com',
            nombre='Doctor Ajeno',
            role=Usuario.ROLE_DOCTOR,
        )
        self.tercero = Usuario.objects.create(
            email='tercero-video@example.com',
            nombre='Tercero',
            role=Usuario.ROLE_PACIENTE,
        )
        self.ajeno = Usuario.objects.create(
            email='ajeno-video@example.com',
            nombre='Usuario sin pacientes',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente = crear_paciente_asignado(
            self.paciente_usuario,
            self.doctor,
            self.paciente_usuario.nombre,
            self.paciente_usuario.email,
        )
        self.paciente_sin_medico_usuario = Usuario.objects.create(
            email='sin-medico-video@example.com',
            nombre='Paciente sin médico',
            role=Usuario.ROLE_PACIENTE,
        )
        self.paciente_sin_medico = Paciente.objects.create(
            usuario=self.paciente_sin_medico_usuario,
            nombre='Paciente sin médico',
            email='sin-medico-video@example.com',
        )
        self.paciente_tercero = crear_paciente_asignado(
            self.tercero,
            self.otro_doctor,
            self.tercero.nombre,
            self.tercero.email,
        )
        self.paciente_sin_usuario = Paciente.objects.create(
            nombre='Paciente sin cuenta',
            email='sin-cuenta-video@example.com',
        )

    async def _communicator(self, usuario=None):
        return await database_sync_to_async(self._build_communicator)(usuario)

    def _build_communicator(self, usuario=None):
        from NexoRev.asgi import application

        headers = [(b'origin', b'http://testserver')]
        if usuario:
            session = SessionStore()
            session['current_user'] = usuario.email
            session['current_user_role'] = usuario.role
            session.save()
            headers.append((
                b'cookie',
                f'{settings.SESSION_COOKIE_NAME}={session.session_key}'.encode(),
            ))
        return WebsocketCommunicator(
            application,
            '/ws/videollamada/',
            headers=headers,
        )

    def _autenticar(self, cliente, usuario):
        session = cliente.session
        session['current_user'] = usuario.email
        session['current_user_role'] = usuario.role
        session.save()

    def test_senalizacion_llega_solo_entre_participantes(self):
        async_to_sync(self._flujo_senalizacion)()

    async def _flujo_senalizacion(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        tercero = await self._communicator(self.tercero)
        conexion_ids = {}
        for socket in (doctor, paciente, tercero):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            conectado_event = await socket.receive_json_from()
            self.assertEqual(conectado_event['tipo'], 'conectado')
            conexion_ids[socket] = conectado_event['conexion_id']

        await doctor.send_json_to({
            'tipo': 'invitar',
            'paciente_id': self.paciente.pk,
        })
        sonando = await doctor.receive_json_from()
        entrante = await paciente.receive_json_from()
        self.assertEqual(sonando['tipo'], 'sonando')
        self.assertEqual(entrante['tipo'], 'entrante')
        self.assertTrue(await tercero.receive_nothing(timeout=0.05))

        await paciente.send_json_to({
            'tipo': 'aceptar',
            'llamada_id': sonando['llamada_id'],
        })
        aceptada_doctor = await doctor.receive_json_from()
        aceptada_paciente = await paciente.receive_json_from()
        self.assertEqual(aceptada_doctor['tipo'], 'aceptada')
        self.assertEqual(aceptada_paciente['tipo'], 'aceptada')
        self.assertEqual(
            aceptada_paciente['aceptada_conexion'],
            conexion_ids[paciente],
        )
        self.assertNotEqual(
            aceptada_paciente['aceptada_conexion'],
            conexion_ids[doctor],
        )
        self.assertTrue(await tercero.receive_nothing(timeout=0.05))

        offer = {
            'tipo': 'offer',
            'llamada_id': sonando['llamada_id'],
            'description': {'type': 'offer', 'sdp': 'offer-sdp'},
        }
        await doctor.send_json_to(offer)
        self.assertEqual((await paciente.receive_json_from())['tipo'], 'offer')
        await paciente.send_json_to({
            'tipo': 'answer',
            'llamada_id': sonando['llamada_id'],
            'description': {'type': 'answer', 'sdp': 'answer-sdp'},
        })
        self.assertEqual((await doctor.receive_json_from())['tipo'], 'answer')
        await doctor.send_json_to({
            'tipo': 'ice',
            'llamada_id': sonando['llamada_id'],
            'candidate': {'candidate': 'candidate:1 1 UDP 1 127.0.0.1 9 typ host'},
        })
        self.assertEqual((await paciente.receive_json_from())['tipo'], 'ice')

        await doctor.send_json_to({
            'tipo': 'estado_medios',
            'llamada_id': sonando['llamada_id'],
            'camara_activa': False,
            'microfono_activo': True,
        })
        estado_medios = await paciente.receive_json_from()
        self.assertEqual(estado_medios['tipo'], 'estado_medios')
        self.assertFalse(estado_medios['camara_activa'])
        self.assertTrue(estado_medios['microfono_activo'])
        self.assertTrue(await tercero.receive_nothing(timeout=0.05))

        await paciente.send_json_to({
            'tipo': 'estado_medios',
            'llamada_id': sonando['llamada_id'],
            'camara_activa': 'false',
            'microfono_activo': True,
        })
        self.assertEqual((await paciente.receive_json_from())['tipo'], 'error')
        self.assertTrue(await doctor.receive_nothing(timeout=0.05))

        await paciente.send_json_to({
            'tipo': 'salir',
            'llamada_id': sonando['llamada_id'],
        })
        terminada_doctor = await doctor.receive_json_from()
        terminada_paciente = await paciente.receive_json_from()
        self.assertEqual(terminada_doctor['tipo'], 'terminada')
        self.assertEqual(terminada_paciente['tipo'], 'terminada')
        estado = await database_sync_to_async(
            lambda: Llamada.objects.get(pk=sonando['llamada_id']).estado
        )()
        self.assertEqual(estado, Llamada.ESTADO_FINALIZADA)
        mensajes_sistema = await database_sync_to_async(
            lambda: Mensaje.objects.filter(
                paciente=self.paciente,
                autor__isnull=True,
            ).count()
        )()
        await paciente.send_json_to({
            'tipo': 'salir',
            'llamada_id': sonando['llamada_id'],
        })
        await doctor.receive_json_from()
        await paciente.receive_json_from()
        mensajes_sistema_tras_repetir = await database_sync_to_async(
            lambda: Mensaje.objects.filter(
                paciente=self.paciente,
                autor__isnull=True,
            ).count()
        )()
        self.assertEqual(mensajes_sistema_tras_repetir, mensajes_sistema)
        for socket in (doctor, paciente, tercero):
            await socket.disconnect()

    def test_permisos_y_eventos_mal_formados_se_rechazan(self):
        async_to_sync(self._probar_permisos_y_eventos)()

    async def _probar_permisos_y_eventos(self):
        ajeno = await self._communicator(self.otro_doctor)
        conectado, _ = await ajeno.connect()
        self.assertTrue(conectado)
        await ajeno.receive_json_from()
        for paciente_id in (self.paciente.pk, self.paciente_sin_medico.pk, self.paciente_sin_usuario.pk):
            await ajeno.send_json_to({'tipo': 'invitar', 'paciente_id': paciente_id})
            self.assertEqual((await ajeno.receive_json_from())['tipo'], 'error')
        await ajeno.send_json_to({'tipo': 'invitar', 'paciente_id': 'no-numérico'})
        self.assertEqual((await ajeno.receive_json_from())['tipo'], 'error')
        await ajeno.send_to(text_data='{')
        self.assertEqual((await ajeno.receive_json_from())['tipo'], 'error')
        await ajeno.send_json_to({
            'tipo': 'offer',
            'llamada_id': 1,
            'description': {'type': 'offer', 'sdp': 'x' * 50_000},
        })
        self.assertEqual((await ajeno.receive_json_from())['tipo'], 'error')
        await ajeno.send_to(text_data=' ' * (64 * 1024 + 1))
        self.assertEqual((await ajeno.receive_json_from())['tipo'], 'error')
        await ajeno.disconnect()

        sin_pacientes = await self._communicator(self.ajeno)
        conectado, codigo = await sin_pacientes.connect()
        self.assertFalse(conectado)
        self.assertEqual(codigo, 4403)

        paciente_sin_medico = await self._communicator(self.paciente_sin_medico_usuario)
        conectado, _ = await paciente_sin_medico.connect()
        self.assertFalse(conectado)

        anonimo = await self._communicator()
        conectado, codigo = await anonimo.connect()
        self.assertFalse(conectado)
        self.assertEqual(codigo, 4403)

    def test_segunda_invitacion_activa_recibe_ocupado(self):
        async_to_sync(self._probar_llamada_ocupada)()

    async def _probar_llamada_ocupada(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        for socket in (doctor, paciente):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            await socket.receive_json_from()
        await doctor.send_json_to({
            'tipo': 'invitar',
            'paciente_id': self.paciente.pk,
        })
        await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.send_json_to({
            'tipo': 'invitar',
            'paciente_id': self.paciente.pk,
        })
        self.assertEqual((await paciente.receive_json_from())['tipo'], 'ocupado')
        await doctor.disconnect()
        await paciente.disconnect()

    def test_usuario_que_se_conecta_tarde_recibe_invitacion_activa(self):
        async_to_sync(self._probar_invitacion_al_conectar)()

    async def _probar_invitacion_al_conectar(self):
        doctor = await self._communicator(self.doctor)
        conectado, _ = await doctor.connect()
        self.assertTrue(conectado)
        await doctor.receive_json_from()
        await doctor.send_json_to({
            'tipo': 'invitar',
            'paciente_id': self.paciente.pk,
        })
        invitacion = await doctor.receive_json_from()
        self.assertEqual(invitacion['tipo'], 'sonando')

        paciente = await self._communicator(self.paciente_usuario)
        conectado, _ = await paciente.connect()
        self.assertTrue(conectado)
        await paciente.receive_json_from()
        entrante = await paciente.receive_json_from()
        self.assertEqual(entrante['tipo'], 'entrante')
        self.assertEqual(entrante['llamada_id'], invitacion['llamada_id'])
        await doctor.disconnect()
        await paciente.disconnect()

    def test_rechazar_y_cancelar_actualizan_estado(self):
        async_to_sync(self._probar_estados_terminados)()

    async def _probar_estados_terminados(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        for socket in (doctor, paciente):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            await socket.receive_json_from()

        await doctor.send_json_to({'tipo': 'invitar', 'paciente_id': self.paciente.pk})
        invitacion = await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.send_json_to({
            'tipo': 'rechazar',
            'llamada_id': invitacion['llamada_id'],
        })
        self.assertEqual((await doctor.receive_json_from())['tipo'], 'rechazada')
        self.assertEqual((await paciente.receive_json_from())['tipo'], 'rechazada')
        estado = await database_sync_to_async(
            lambda: Llamada.objects.get(pk=invitacion['llamada_id']).estado
        )()
        self.assertEqual(estado, Llamada.ESTADO_RECHAZADA)

        await doctor.send_json_to({'tipo': 'invitar', 'paciente_id': self.paciente.pk})
        invitacion = await doctor.receive_json_from()
        await paciente.receive_json_from()
        await doctor.send_json_to({
            'tipo': 'cancelar',
            'llamada_id': invitacion['llamada_id'],
        })
        self.assertEqual((await paciente.receive_json_from())['tipo'], 'cancelada')
        estado = await database_sync_to_async(
            lambda: Llamada.objects.get(pk=invitacion['llamada_id']).estado
        )()
        self.assertEqual(estado, Llamada.ESTADO_CANCELADA)
        await doctor.disconnect()
        await paciente.disconnect()

    @patch('mensajeria.videollamada.TIEMPO_SONANDO_SEGUNDOS', 0.05)
    def test_invitacion_expira_y_se_marca_perdida(self):
        async_to_sync(self._probar_expiracion)()

    async def _probar_expiracion(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        for socket in (doctor, paciente):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            await socket.receive_json_from()
        await doctor.send_json_to({'tipo': 'invitar', 'paciente_id': self.paciente.pk})
        invitacion = await doctor.receive_json_from()
        await paciente.receive_json_from()
        terminal_doctor = await doctor.receive_json_from(timeout=1)
        terminal_paciente = await paciente.receive_json_from(timeout=1)
        self.assertEqual(terminal_doctor['tipo'], 'terminada')
        self.assertEqual(terminal_paciente['tipo'], 'terminada')
        self.assertEqual(terminal_doctor['motivo'], Llamada.ESTADO_PERDIDA)
        estado = await database_sync_to_async(
            lambda: Llamada.objects.get(pk=invitacion['llamada_id']).estado
        )()
        self.assertEqual(estado, Llamada.ESTADO_PERDIDA)
        await doctor.disconnect()
        await paciente.disconnect()

    @patch('mensajeria.videollamada.TIEMPO_RECONEXION_SEGUNDOS', 0.1)
    def test_desconexion_sin_reconectar_termina_llamada(self):
        async_to_sync(self._probar_desconexion)()

    async def _probar_desconexion(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        for socket in (doctor, paciente):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            await socket.receive_json_from()
        await doctor.send_json_to({'tipo': 'invitar', 'paciente_id': self.paciente.pk})
        invitacion = await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.send_json_to({
            'tipo': 'aceptar',
            'llamada_id': invitacion['llamada_id'],
        })
        await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.disconnect()
        terminado = await doctor.receive_json_from(timeout=1)
        self.assertEqual(terminado['tipo'], 'terminada')
        self.assertEqual(terminado['motivo'], 'desconexion')
        estado = await database_sync_to_async(
            lambda: Llamada.objects.get(pk=invitacion['llamada_id']).estado
        )()
        self.assertEqual(estado, Llamada.ESTADO_FINALIZADA)
        await doctor.disconnect()

    @patch('mensajeria.videollamada.TIEMPO_RECONEXION_SEGUNDOS', 0.2)
    def test_refresco_sin_reanudar_finaliza_llamada_activa(self):
        async_to_sync(self._probar_refresco_sin_reanudar)()

    async def _probar_refresco_sin_reanudar(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        for socket in (doctor, paciente):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            await socket.receive_json_from()
        await doctor.send_json_to({'tipo': 'invitar', 'paciente_id': self.paciente.pk})
        invitacion = await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.send_json_to({
            'tipo': 'aceptar',
            'llamada_id': invitacion['llamada_id'],
        })
        await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.disconnect()

        pagina_recargada = await self._communicator(self.paciente_usuario)
        conectado, _ = await pagina_recargada.connect()
        self.assertTrue(conectado)
        await pagina_recargada.receive_json_from()
        await asyncio.sleep(0.1)
        evento_doctor = await doctor.receive_json_from(timeout=1)
        self.assertEqual(evento_doctor['tipo'], 'terminada')
        self.assertEqual(evento_doctor['motivo'], 'desconexion')
        estado = await database_sync_to_async(
            lambda: Llamada.objects.get(pk=invitacion['llamada_id']).estado
        )()
        self.assertEqual(estado, Llamada.ESTADO_FINALIZADA)
        await doctor.disconnect()
        await pagina_recargada.disconnect()

    @patch('mensajeria.videollamada.TIEMPO_RECONEXION_SEGUNDOS', 2)
    def test_reanudar_en_ventana_conserva_llamada(self):
        async_to_sync(self._probar_reanudar_en_ventana)()

    async def _probar_reanudar_en_ventana(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        for socket in (doctor, paciente):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            await socket.receive_json_from()
        await doctor.send_json_to({'tipo': 'invitar', 'paciente_id': self.paciente.pk})
        invitacion = await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.send_json_to({
            'tipo': 'aceptar',
            'llamada_id': invitacion['llamada_id'],
        })
        await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.disconnect()

        pagina_reconectada = await self._communicator(self.paciente_usuario)
        conectado, _ = await pagina_reconectada.connect()
        self.assertTrue(conectado)
        await pagina_reconectada.receive_json_from()
        await pagina_reconectada.send_json_to({
            'tipo': 'reanudar',
            'llamada_id': invitacion['llamada_id'],
        })
        reanudada = await pagina_reconectada.receive_json_from()
        self.assertEqual(reanudada['tipo'], 'reanudada')
        await asyncio.sleep(0.1)
        estado = await database_sync_to_async(
            lambda: Llamada.objects.get(pk=invitacion['llamada_id']).estado
        )()
        self.assertEqual(estado, Llamada.ESTADO_EN_CURSO)

        await doctor.send_json_to({
            'tipo': 'colgar',
            'llamada_id': invitacion['llamada_id'],
        })
        self.assertEqual((await doctor.receive_json_from())['tipo'], 'terminada')
        self.assertEqual((await pagina_reconectada.receive_json_from())['tipo'], 'terminada')
        await doctor.disconnect()
        await pagina_reconectada.disconnect()

    def test_salir_tras_recarga_notifica_a_ambos_usuarios(self):
        async_to_sync(self._probar_salir_tras_recarga)()

    async def _probar_salir_tras_recarga(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        for socket in (doctor, paciente):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            await socket.receive_json_from()
        await doctor.send_json_to({'tipo': 'invitar', 'paciente_id': self.paciente.pk})
        invitacion = await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.send_json_to({
            'tipo': 'aceptar',
            'llamada_id': invitacion['llamada_id'],
        })
        await doctor.receive_json_from()
        await paciente.receive_json_from()
        cierre = {'tipo': 'salir', 'llamada_id': invitacion['llamada_id']}
        await paciente.send_json_to(cierre)
        self.assertEqual((await doctor.receive_json_from())['tipo'], 'terminada')
        self.assertEqual((await paciente.receive_json_from())['tipo'], 'terminada')
        await paciente.disconnect()

        pagina_recargada = await self._communicator(self.paciente_usuario)
        conectado, _ = await pagina_recargada.connect()
        self.assertTrue(conectado)
        await pagina_recargada.receive_json_from()
        await pagina_recargada.send_json_to(cierre)
        evento_doctor = await doctor.receive_json_from()
        evento_paciente = await pagina_recargada.receive_json_from()
        self.assertEqual(evento_doctor['tipo'], 'terminada')
        self.assertEqual(evento_paciente['tipo'], 'terminada')
        mensajes_sistema = await database_sync_to_async(
            lambda: Mensaje.objects.filter(
                paciente=self.paciente,
                autor__isnull=True,
            ).count()
        )()
        self.assertEqual(mensajes_sistema, 1)
        await doctor.disconnect()
        await pagina_recargada.disconnect()

    def test_reasignacion_termina_llamada_en_curso(self):
        async_to_sync(self._probar_reasignacion)()

    async def _probar_reasignacion(self):
        doctor = await self._communicator(self.doctor)
        paciente = await self._communicator(self.paciente_usuario)
        for socket in (doctor, paciente):
            conectado, _ = await socket.connect()
            self.assertTrue(conectado)
            await socket.receive_json_from()
        await doctor.send_json_to({'tipo': 'invitar', 'paciente_id': self.paciente.pk})
        invitacion = await doctor.receive_json_from()
        await paciente.receive_json_from()
        await paciente.send_json_to({
            'tipo': 'aceptar',
            'llamada_id': invitacion['llamada_id'],
        })
        await doctor.receive_json_from()
        await paciente.receive_json_from()

        admin = await database_sync_to_async(get_user_model().objects.create_user)(
            username='admin-videollamada',
            password='test-password',
            is_staff=True,
        )

        def reasignar():
            reasignar_medico(
                paciente=Paciente.objects.get(pk=self.paciente.pk),
                nuevo_doctor=self.otro_doctor,
                tipo=AsignacionMedico.TIPO_CONTINUIDAD,
                motivo='Cambio de médico durante videollamada.',
                compartir_historial_clinico=False,
                paciente_autorizo=False,
                admin=admin,
            )

        await database_sync_to_async(reasignar)()
        doctor_event = await doctor.receive_json_from(timeout=2)
        patient_event = await paciente.receive_json_from(timeout=2)
        self.assertEqual(doctor_event['tipo'], 'terminada')
        self.assertEqual(patient_event['tipo'], 'terminada')
        self.assertEqual(doctor_event['motivo'], 'acceso_revocado')
        estado = await database_sync_to_async(
            lambda: Llamada.objects.get(pk=invitacion['llamada_id']).estado
        )()
        self.assertEqual(estado, Llamada.ESTADO_FINALIZADA)
        await doctor.disconnect()
        await paciente.disconnect()

    def test_endpoint_ice_exige_sesion_y_usa_credenciales_turn_efimeras(self):
        cliente = Client()
        anonima = cliente.get(reverse('mensajeria:ice_servers'))
        self.assertEqual(anonima.status_code, 401)

        self._autenticar(cliente, self.doctor)
        with patch.dict('os.environ', {
            'TURN_URLS': 'turn:turn.example.test:3478',
            'TURN_SECRET': 'secret-turn-de-prueba',
            'STUN_URLS': 'stun:stun.example.test:3478',
        }):
            response = cliente.get(reverse('mensajeria:ice_servers'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        servers = response.json()['iceServers']
        self.assertEqual(len(servers), 2)
        self.assertNotEqual(servers[1]['credential'], 'secret-turn-de-prueba')
        self.assertTrue(servers[1]['username'].endswith(f':{self.doctor.pk}'))

        with patch.dict('os.environ', {
            'TURN_URLS': 'turn:turn.example.test:3478',
            'TURN_SECRET': '',
            'STUN_URLS': 'stun:stun.example.test:3478',
        }):
            sin_secreto = cliente.get(reverse('mensajeria:ice_servers')).json()
        self.assertEqual(len(sin_secreto['iceServers']), 1)
        self.assertEqual(
            sin_secreto['iceServers'][0]['urls'],
            ['stun:stun.example.test:3478'],
        )
        self.assertEqual(
            cliente.post(reverse('mensajeria:ice_servers')).status_code,
            405,
        )
