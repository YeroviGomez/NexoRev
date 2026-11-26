import json

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
from mensajeria.models import Mensaje
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
