import base64
from io import BytesIO
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from crear_cuenta.models import Usuario
from .models import (
	Diagnostico,
	EvaluacionClinica,
	ObjetivoTerapeutico,
	Paciente,
	RutinaAsignada,
	Sesion,
	VideoView,
)


class DiagnosticFormTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(
			email='formulario-test@example.com',
			nombre='Paciente de prueba',
		)
		self.client = Client()
		self.autenticar(self.client, self.usuario)
		self.respuestas = {
			'nivel_dolor': '4',
			'pregunta1': 'espalda',
			'pregunta2': 'La sesión fue cómoda.',
			'pregunta3': 'si',
			'comentario': 'Puedo moverme mejor.',
		}

	def autenticar(self, client, usuario):
		session = client.session
		session['current_user'] = usuario.email
		session.save()

	def test_guarda_el_formulario_en_la_cuenta_autenticada(self):
		response = self.client.post('/principal/', self.respuestas)

		self.assertEqual(response.status_code, 302)
		diagnostico = Diagnostico.objects.get(usuario=self.usuario)
		self.assertEqual(diagnostico.nivel_dolor, 4)
		self.assertEqual(diagnostico.pregunta1, 'espalda')
		self.assertEqual(diagnostico.pregunta2, 'La sesión fue cómoda.')
		self.assertEqual(diagnostico.pregunta3, 'si')
		self.assertEqual(diagnostico.comentario, 'Puedo moverme mejor.')
		self.assertEqual(
			EvaluacionClinica.objects.get(paciente__usuario=self.usuario).nivel_dolor,
			diagnostico.nivel_dolor,
		)

	def test_actualiza_el_formulario_existente_del_paciente(self):
		self.client.post('/principal/', self.respuestas)
		respuestas_actualizadas = {**self.respuestas, 'nivel_dolor': '7'}
		self.client.post('/principal/', respuestas_actualizadas)

		self.assertEqual(Diagnostico.objects.filter(usuario=self.usuario).count(), 1)
		self.assertEqual(Diagnostico.objects.get(usuario=self.usuario).nivel_dolor, 7)

	def test_cada_paciente_solo_guarda_su_propio_formulario(self):
		self.client.post('/principal/', self.respuestas)
		otro_usuario = Usuario.objects.create(
			email='otro-formulario-test@example.com',
			nombre='Otro paciente',
		)
		otro_cliente = Client()
		self.autenticar(otro_cliente, otro_usuario)
		respuestas_otro_usuario = {**self.respuestas, 'nivel_dolor': '8'}
		otro_cliente.post('/principal/', respuestas_otro_usuario)

		self.assertEqual(Diagnostico.objects.count(), 2)
		self.assertEqual(Diagnostico.objects.get(usuario=self.usuario).nivel_dolor, 4)
		self.assertEqual(Diagnostico.objects.get(usuario=otro_usuario).nivel_dolor, 8)

	def test_rechaza_dolor_fuera_del_rango_y_no_guarda(self):
		respuestas_invalidas = {**self.respuestas, 'nivel_dolor': '11'}
		response = self.client.post('/principal/', respuestas_invalidas)

		self.assertEqual(response.status_code, 200)
		self.assertIn('nivel_dolor', response.context['form'].errors)
		self.assertFalse(Diagnostico.objects.exists())

	def test_doctor_no_puede_enviar_el_formulario_de_paciente(self):
		doctor = Usuario.objects.create(
			email='doctor-formulario-test@example.com',
			nombre='Doctor de prueba',
			role=Usuario.ROLE_DOCTOR,
		)
		cliente_doctor = Client()
		self.autenticar(cliente_doctor, doctor)
		response = cliente_doctor.post('/principal/', self.respuestas)

		self.assertEqual(response.status_code, 403)
		self.assertFalse(Diagnostico.objects.exists())

	def test_calendario_muestra_sesiones_activas_en_la_fecha_local(self):
		paciente = Paciente.objects.create(
			usuario=self.usuario,
			nombre=self.usuario.nombre,
			email=self.usuario.email,
		)
		fecha = timezone.now() + timedelta(days=2)
		Sesion.objects.create(paciente=paciente, fecha=fecha, objetivo='Rutina de movilidad')
		Sesion.objects.create(paciente=paciente, fecha=fecha, objetivo='Sesión cancelada', activo=False)

		response = self.client.get('/principal/')

		self.assertEqual(response.status_code, 200)
		sesiones = response.context['calendar_sessions']
		self.assertEqual(len(sesiones), 1)
		self.assertEqual(sesiones[0]['date'], timezone.localtime(fecha).date().isoformat())
		self.assertEqual(sesiones[0]['time'], timezone.localtime(fecha).strftime('%H:%M'))
		self.assertEqual(sesiones[0]['objective'], 'Rutina de movilidad')
		self.assertContains(response, 'calendarSessionsData')


class SessionRescheduleTests(TestCase):
	def setUp(self):
		self.doctor = Usuario.objects.create(
			email='especialista-test@example.com',
			nombre='Especialista de prueba',
			role=Usuario.ROLE_DOCTOR,
		)
		self.usuario = Usuario.objects.create(
			email='paciente-cita-test@example.com',
			nombre='Paciente de cita',
		)
		self.paciente = Paciente.objects.create(
			usuario=self.usuario,
			doctor=self.doctor,
			nombre=self.usuario.nombre,
			email=self.usuario.email,
		)
		self.sesion = Sesion.objects.create(
			paciente=self.paciente,
			fecha=timezone.now() + timedelta(days=1),
			objetivo='Rutina de movilidad',
		)
		self.doctor_client = Client()
		self.autenticar(self.doctor_client, self.doctor)

	def test_expediente_entrega_el_id_y_fecha_local_de_la_sesion(self):
		response = self.doctor_client.get(f'/principal/pacientes/{self.paciente.pk}/')

		self.assertEqual(response.status_code, 200)
		sesion = response.json()['paciente']['sesiones'][0]
		self.assertEqual(sesion['id'], self.sesion.pk)
		self.assertEqual(
			sesion['fecha_local'],
			timezone.localtime(self.sesion.fecha).strftime('%Y-%m-%dT%H:%M'),
		)

	def autenticar(self, client, usuario):
		session = client.session
		session['current_user'] = usuario.email
		session.save()

	def test_especialista_asignado_reagenda_y_calendario_refleja_el_cambio(self):
		fecha_nueva = timezone.localtime(timezone.now() + timedelta(days=5)).replace(second=0, microsecond=0)
		response = self.doctor_client.post(
			reverse('reschedule_session', args=[self.paciente.pk, self.sesion.pk]),
			{'fecha': fecha_nueva.strftime('%Y-%m-%dT%H:%M')},
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['success'])
		self.sesion.refresh_from_db()
		self.assertEqual(timezone.localtime(self.sesion.fecha), fecha_nueva)

		patient_client = Client()
		self.autenticar(patient_client, self.usuario)
		calendar_response = patient_client.get('/principal/')
		scheduled = calendar_response.context['calendar_sessions']
		self.assertEqual(len(scheduled), 1)
		self.assertEqual(scheduled[0]['date'], fecha_nueva.date().isoformat())
		self.assertEqual(scheduled[0]['time'], fecha_nueva.strftime('%H:%M'))

	def test_otro_especialista_no_puede_reagendar_la_cita(self):
		especialista_ajeno = Usuario.objects.create(
			email='otro-especialista-test@example.com',
			nombre='Otro especialista',
			role=Usuario.ROLE_DOCTOR,
		)
		cliente_ajeno = Client()
		self.autenticar(cliente_ajeno, especialista_ajeno)
		fecha_original = self.sesion.fecha

		response = cliente_ajeno.post(
			reverse('reschedule_session', args=[self.paciente.pk, self.sesion.pk]),
			{'fecha': (timezone.localtime(timezone.now() + timedelta(days=4))).strftime('%Y-%m-%dT%H:%M')},
		)

		self.assertEqual(response.status_code, 404)
		self.sesion.refresh_from_db()
		self.assertEqual(self.sesion.fecha, fecha_original)

	def test_rechaza_una_fecha_pasada(self):
		fecha_original = self.sesion.fecha
		response = self.doctor_client.post(
			reverse('reschedule_session', args=[self.paciente.pk, self.sesion.pk]),
			{'fecha': (timezone.localtime(timezone.now() - timedelta(days=1))).strftime('%Y-%m-%dT%H:%M')},
		)

		self.assertEqual(response.status_code, 400)
		self.assertFalse(response.json()['success'])
		self.sesion.refresh_from_db()
		self.assertEqual(self.sesion.fecha, fecha_original)


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class ProfilePhotoTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(
			email='foto-test@example.com',
			nombre='Usuario de prueba',
			password='password',
		)
		self.client = Client()

	def autenticar_usuario(self):
		session = self.client.session
		session['current_user'] = self.usuario.email
		session.save()

	def test_usuario_sin_sesion_no_puede_subir_foto(self):
		response = self.client.post('/principal/api/upload-photo/')

		self.assertEqual(response.status_code, 401)
		self.assertFalse(response.json()['success'])

	def test_rechaza_archivo_que_no_es_imagen(self):
		self.autenticar_usuario()
		archivo = SimpleUploadedFile('avatar.txt', b'no es una imagen', content_type='text/plain')

		response = self.client.post('/principal/api/upload-photo/', {'foto': archivo})

		self.assertEqual(response.status_code, 400)
		self.assertFalse(response.json()['success'])

	def test_guarda_foto_valida_y_devuelve_su_url(self):
		self.autenticar_usuario()
		contenido_png = base64.b64decode(
			'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk'
			'YAAAAAYAAjCB0C8AAAAASUVORK5CYII='
		)
		archivo = SimpleUploadedFile('avatar.png', contenido_png, content_type='image/png')

		response = self.client.post('/principal/api/upload-photo/', {'foto': archivo})

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['success'])
		self.usuario.refresh_from_db()
		self.assertTrue(self.usuario.foto_perfil.name.startswith('perfiles/'))

	def test_carga_foto_con_token_csrf_de_la_pagina_de_perfil(self):
		client = Client(enforce_csrf_checks=True)
		session = client.session
		session['current_user'] = self.usuario.email
		session['current_user_role'] = self.usuario.role
		session.save()
		respuesta_perfil = client.get('/principal/')
		self.assertEqual(respuesta_perfil.status_code, 200)
		token_csrf = client.cookies['csrftoken'].value

		contenido_png = base64.b64decode(
			'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk'
			'YAAAAAYAAjCB0C8AAAAASUVORK5CYII='
		)
		archivo = SimpleUploadedFile('avatar.png', contenido_png, content_type='image/png')
		response = client.post(
			'/principal/api/upload-photo/',
			{'foto': archivo},
			HTTP_X_CSRFTOKEN=token_csrf,
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['success'])

	def test_reemplaza_foto_con_jpeg_recortado(self):
		self.autenticar_usuario()
		contenido_png = base64.b64decode(
			'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk'
			'YAAAAAYAAjCB0C8AAAAASUVORK5CYII='
		)
		foto_original = SimpleUploadedFile(
			'avatar.png',
			contenido_png,
			content_type='image/png',
		)
		response_original = self.client.post(
			'/principal/api/upload-photo/',
			{'foto': foto_original},
		)
		self.assertEqual(response_original.status_code, 200)
		nombre_foto_original = response_original.json()['foto_url'].split('/media/')[-1]

		contenido_jpeg = BytesIO()
		Image.new('RGB', (512, 512), color=(24, 128, 72)).save(contenido_jpeg, format='JPEG')
		archivo = SimpleUploadedFile(
			'foto-perfil.jpg',
			contenido_jpeg.getvalue(),
			content_type='image/jpeg',
		)

		response = self.client.post('/principal/api/upload-photo/', {'foto': archivo})

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['success'])
		self.usuario.refresh_from_db()
		self.assertTrue(self.usuario.foto_perfil.name.endswith('.jpg'))
		self.assertTrue(self.usuario.foto_perfil.storage.exists(self.usuario.foto_perfil.name))
		self.assertFalse(self.usuario.foto_perfil.storage.exists(nombre_foto_original))

	def test_foto_guardada_se_muestra_en_otra_sesion_y_se_puede_restablecer(self):
		self.autenticar_usuario()
		contenido_png = base64.b64decode(
			'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk'
			'YAAAAAYAAjCB0C8AAAAASUVORK5CYII='
		)
		archivo = SimpleUploadedFile('avatar.png', contenido_png, content_type='image/png')
		respuesta_carga = self.client.post('/principal/api/upload-photo/', {'foto': archivo})
		self.assertEqual(respuesta_carga.status_code, 200)
		ruta_foto = respuesta_carga.json()['foto_url']

		otro_dispositivo = Client()
		sesion = otro_dispositivo.session
		sesion['current_user'] = self.usuario.email
		sesion['current_user_role'] = self.usuario.role
		sesion.save()
		respuesta_otro_dispositivo = otro_dispositivo.get('/principal/')
		self.assertEqual(respuesta_otro_dispositivo.status_code, 200)
		self.assertContains(respuesta_otro_dispositivo, ruta_foto)

		respuesta_reset = self.client.post('/principal/api/reset-photo/')

		self.assertEqual(respuesta_reset.status_code, 200)
		self.assertTrue(respuesta_reset.json()['success'])
		self.usuario.refresh_from_db()
		self.assertFalse(self.usuario.foto_perfil)
		self.assertFalse(
			self.usuario.foto_perfil.storage.exists(
				ruta_foto.split('/media/')[-1],
			),
		)


class ProfileUpdateTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(
			email='perfil-test@example.com',
			nombre='Usuario de prueba',
		)
		self.usuario.set_password('ClaveSegura123')
		self.usuario.save(update_fields=['password'])
		self.client = Client()
		session = self.client.session
		session['current_user'] = self.usuario.email
		session.save()

	def test_actualiza_nombre_correo_y_telefono(self):
		paciente = Paciente.objects.create(
			usuario=self.usuario,
			nombre=self.usuario.nombre,
			email=self.usuario.email,
		)
		VideoView.objects.create(
			user_email=self.usuario.email,
			video_id='abc123xyz',
			category='Espalda',
		)

		response = self.client.post(
			'/principal/api/update-profile/',
			{
				'nombre': 'Nombre actualizado',
				'email': 'nuevo@example.com',
				'telefono': '2222-3333',
			},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['success'])
		self.usuario.refresh_from_db()
		paciente.refresh_from_db()
		self.assertEqual(self.usuario.nombre, 'Nombre actualizado')
		self.assertEqual(self.usuario.email, 'nuevo@example.com')
		self.assertEqual(self.usuario.telefono, '2222-3333')
		self.assertEqual(self.client.session['current_user'], 'nuevo@example.com')
		self.assertEqual(paciente.nombre, 'Nombre actualizado')
		self.assertEqual(paciente.email, 'nuevo@example.com')
		self.assertEqual(paciente.telefono, '2222-3333')
		self.assertEqual(VideoView.objects.get().user_email, 'nuevo@example.com')

	def test_rechaza_correo_que_ya_usa_otra_cuenta(self):
		Usuario.objects.create(email='ocupado@example.com', nombre='Otra persona')

		response = self.client.post(
			'/principal/api/update-profile/',
			{
				'nombre': 'Nombre actualizado',
				'email': 'ocupado@example.com',
				'telefono': '',
			},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.usuario.refresh_from_db()
		self.assertEqual(self.usuario.email, 'perfil-test@example.com')

	def test_cambia_contrasena_si_la_actual_es_correcta(self):
		response = self.client.post(
			'/principal/api/change-password/',
			{
				'currentPassword': 'ClaveSegura123',
				'newPassword': 'NuevaClave123',
				'confirmPassword': 'NuevaClave123',
			},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['success'])
		self.usuario.refresh_from_db()
		self.assertTrue(self.usuario.check_password('NuevaClave123'))

	def test_no_cambia_contrasena_si_la_actual_es_incorrecta(self):
		response = self.client.post(
			'/principal/api/change-password/',
			{
				'currentPassword': 'Incorrecta123',
				'newPassword': 'NuevaClave123',
				'confirmPassword': 'NuevaClave123',
			},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.usuario.refresh_from_db()
		self.assertTrue(self.usuario.check_password('ClaveSegura123'))


class AppearancePreferenceTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(
			email='preferencias-test@example.com',
			nombre='Usuario de preferencias',
		)
		self.client = Client()
		session = self.client.session
		session['current_user'] = self.usuario.email
		session.save()

	def test_preferencias_visuales_se_guardan_en_la_cuenta_y_se_cargan_en_otra_sesion(self):
		preferencias = [
			('modo_oscuro', True),
			('tamano_letra', 'xlarge'),
			('desactivar_animaciones', True),
		]
		for preference, value in preferencias:
			with self.subTest(preference=preference):
				response = self.client.post(
					'/principal/api/update-appearance-preference/',
					{'preference': preference, 'value': value},
					content_type='application/json',
				)
				self.assertEqual(response.status_code, 200)
				self.assertTrue(response.json()['success'])

		self.usuario.refresh_from_db()
		self.assertTrue(self.usuario.modo_oscuro)
		self.assertEqual(self.usuario.tamano_letra, 'xlarge')
		self.assertTrue(self.usuario.desactivar_animaciones)

		otro_dispositivo = Client()
		session = otro_dispositivo.session
		session['current_user'] = self.usuario.email
		session.save()
		response = otro_dispositivo.get('/principal/')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'data-user-theme="dark"')
		self.assertContains(response, 'data-user-font-size="xlarge"')
		self.assertContains(response, 'data-user-motion-disabled="true"')

	def test_rechaza_valores_de_preferencia_invalidos(self):
		response = self.client.post(
			'/principal/api/update-appearance-preference/',
			{'preference': 'tamano_letra', 'value': 'enorme'},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertFalse(response.json()['success'])
		self.usuario.refresh_from_db()
		self.assertEqual(self.usuario.tamano_letra, 'normal')


class VideoHistoryTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(
			email='historial-test@example.com',
			nombre='Usuario de historial',
		)
		self.client = Client()
		session = self.client.session
		session['current_user'] = self.usuario.email
		session.save()

	def test_api_devuelve_los_ocho_videos_unicos_vistos_mas_recientemente(self):
		videos = [
			{
				'video_id': f'video-{index}',
				'title': f'Video {index}',
				'category': 'Espalda',
				'preview_image': f'/media/miniaturas/video-{index}.jpg',
			}
			for index in range(10)
		]
		now = timezone.now()
		for index, video in enumerate(videos):
			view = VideoView.objects.create(
				user_email=self.usuario.email,
				video_id=video['video_id'],
				category=video['category'],
				completed=True,
				completed_at=now - timedelta(minutes=index),
			)
			VideoView.objects.filter(pk=view.pk).update(
				viewed_at=now - timedelta(minutes=index),
			)
		old_repeat = VideoView.objects.create(
			user_email=self.usuario.email,
			video_id='video-0',
			category='Espalda',
		)
		VideoView.objects.filter(pk=old_repeat.pk).update(
			viewed_at=now - timedelta(days=1),
		)
		VideoView.objects.create(
			user_email=self.usuario.email,
			video_id='video-0',
			category='Espalda',
			completed=True,
			completed_at=now,
		)

		with patch('princpal.views.load_videos', return_value=videos):
			response = self.client.get('/principal/api/history/')
			second_page = self.client.get(
				'/principal/api/history/?viewed_page=2&completed_page=2',
			)

		self.assertEqual(response.status_code, 200)
		recent_videos = response.json()['recent_videos']['items']
		self.assertEqual(len(recent_videos), 8)
		self.assertEqual(
			[item['video_id'] for item in recent_videos],
			[f'video-{index}' for index in range(8)],
		)
		self.assertEqual(recent_videos[0]['title'], 'Video 0')
		self.assertEqual(recent_videos[0]['replay_url'], reverse('video_detail', args=[0]))
		self.assertEqual(recent_videos[0]['preview_image'], '/media/miniaturas/video-0.jpg')
		self.assertEqual(
			recent_videos[0]['viewed_at'],
			timezone.localtime(now).strftime('%d/%m/%Y %H:%M'),
		)
		completed_routine = response.json()['completed_videos']['items'][0]
		self.assertEqual(completed_routine['preview_image'], '/media/miniaturas/video-0.jpg')
		self.assertEqual(completed_routine['replay_url'], reverse('video_detail', args=[0]))
		self.assertEqual(
			completed_routine['completed_at'],
			timezone.localtime(now).strftime('%d/%m/%Y %H:%M'),
		)
		self.assertEqual(len(response.json()['completed_videos']['items']), 8)
		self.assertTrue(response.json()['completed_videos']['has_next'])
		self.assertEqual(len(second_page.json()['recent_videos']['items']), 2)
		self.assertEqual(len(second_page.json()['completed_videos']['items']), 2)
		self.assertFalse(second_page.json()['completed_videos']['has_next'])
		self.assertEqual(
			[item['video_id'] for item in second_page.json()['recent_videos']['items']],
			['video-8', 'video-9'],
		)

	def test_biblioteca_muestra_maximo_ocho_videos_por_pagina(self):
		videos = [
			{
				'catalog_index': index,
				'title': f'Video {index}',
				'description': 'Descripción del video',
				'level': 'Principiante',
				'difficulty': 'easy',
				'category': 'Espalda',
				'url': '',
				'video_id': f'video-{index}',
				'embed_url': '',
			}
			for index in range(11)
		]

		with patch('princpal.views.load_videos', return_value=videos):
			first_page = self.client.get('/principal/api/videos/page/?page=1')
			second_page = self.client.get('/principal/api/videos/page/?page=2')

		self.assertEqual(first_page.status_code, 200)
		self.assertEqual(first_page.content.count(b'class="video-card"'), 8)
		self.assertContains(first_page, '?page=2')
		self.assertContains(first_page, 'Siguiente página')
		self.assertEqual(second_page.status_code, 200)
		self.assertEqual(second_page.content.count(b'class="video-card"'), 3)
		self.assertNotContains(second_page, 'Siguiente página')
# Create your tests here.


class MedicalDashboardTests(TestCase):
	def setUp(self):
		self.doctor = Usuario.objects.create(
			email='dashboard-doctor@example.com',
			nombre='Especialista',
			role=Usuario.ROLE_DOCTOR,
		)
		self.patient_user = Usuario.objects.create(
			email='dashboard-patient@example.com',
			nombre='Paciente Dashboard',
		)
		self.patient = Paciente.objects.create(
			usuario=self.patient_user,
			doctor=self.doctor,
			nombre=self.patient_user.nombre,
			email=self.patient_user.email,
			avance=65,
			estado=Paciente.ESTADO_EN_PROCESO,
		)
		self.client = Client()
		session = self.client.session
		session['current_user'] = self.doctor.email
		session.save()

	def test_dashboard_uses_assigned_patient_clinical_records(self):
		evaluation = EvaluacionClinica.objects.create(
			paciente=self.patient,
			nivel_dolor=5,
			metrica='Movilidad',
			valor_actual=60,
			unidad='grados',
		)
		goal = ObjetivoTerapeutico.objects.create(
			paciente=self.patient,
			nombre='Flexión de rodilla',
			metrica='Movilidad',
			valor_objetivo=90,
			unidad='grados',
		)
		session = Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() - timedelta(days=1),
			objetivo='Ejercicios de movilidad',
			realizada=True,
			realizada_en=timezone.now() - timedelta(hours=2),
		)

		page = self.client.get(reverse('principal'))
		response = self.client.get(reverse('doctor_dashboard_data'))

		self.assertEqual(page.status_code, 200)
		self.assertEqual(page.context['active_view'], 'dashboard')
		self.assertContains(page, 'Dashboard médico')
		self.assertEqual(response.status_code, 200)
		patient_data = response.json()['patients'][0]
		self.assertEqual(patient_data['name'], self.patient.nombre)
		self.assertEqual(patient_data['evaluations'][0]['pain'], evaluation.nivel_dolor)
		self.assertEqual(patient_data['goals'][0]['target'], float(goal.valor_objetivo))
		self.assertEqual(patient_data['goals'][0]['direction'], ObjetivoTerapeutico.DIRECCION_MAYOR)
		self.assertEqual(patient_data['sessions'][0]['id'], session.pk)
		self.assertTrue(patient_data['sessions'][0]['completed'])

	def test_doctor_can_register_evaluation_goal_and_planned_session(self):
		evaluation_response = self.client.post(
			reverse('register_clinical_evaluation', args=[self.patient.pk]),
			{
				'nivel_dolor': '4',
				'metrica': 'Fuerza',
				'valor_actual': '20',
				'unidad': 'kg',
			},
		)
		goal_response = self.client.post(
			reverse('add_therapeutic_goal', args=[self.patient.pk]),
			{
				'nombre': 'Fuerza de pierna',
				'metrica': 'Fuerza',
				'direccion': 'mayor',
				'valor_objetivo': '30',
				'unidad': 'kg',
			},
		)
		future_date = timezone.localtime(timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
		session_response = self.client.post(
			reverse('schedule_session', args=[self.patient.pk]),
			{'fecha': future_date, 'objetivo': 'Fortalecimiento'},
		)

		self.assertEqual(evaluation_response.status_code, 302)
		self.assertEqual(goal_response.status_code, 302)
		self.assertEqual(session_response.status_code, 302)
		self.assertEqual(EvaluacionClinica.objects.filter(paciente=self.patient).count(), 1)
		self.assertEqual(ObjetivoTerapeutico.objects.filter(paciente=self.patient).count(), 1)
		self.assertEqual(Sesion.objects.filter(paciente=self.patient, activo=True).count(), 1)

	def test_dashboard_and_clinical_write_routes_are_scoped_to_assigned_patients(self):
		other_doctor = Usuario.objects.create(
			email='otro-dashboard-doctor@example.com',
			nombre='Otro especialista',
			role=Usuario.ROLE_DOCTOR,
		)
		other_patient = Paciente.objects.create(
			doctor=other_doctor,
			nombre='Paciente ajeno',
			email='paciente-ajeno-dashboard@example.com',
		)
		EvaluacionClinica.objects.create(paciente=other_patient, nivel_dolor=8)

		data_response = self.client.get(reverse('doctor_dashboard_data'))
		write_response = self.client.post(
			reverse('register_clinical_evaluation', args=[other_patient.pk]),
			{'nivel_dolor': '2'},
		)

		self.assertEqual(data_response.status_code, 200)
		self.assertEqual([patient['id'] for patient in data_response.json()['patients']], [self.patient.pk])
		self.assertEqual(write_response.status_code, 403)
		self.assertEqual(EvaluacionClinica.objects.filter(paciente=other_patient).count(), 1)

	def test_doctor_can_complete_only_due_sessions(self):
		due_session = Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() - timedelta(minutes=5),
			objetivo='Sesión concluida',
		)
		future_session = Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() + timedelta(days=1),
			objetivo='Próxima sesión',
		)

		due_response = self.client.post(reverse('complete_session', args=[due_session.pk]))
		future_response = self.client.post(reverse('complete_session', args=[future_session.pk]))

		self.assertEqual(due_response.status_code, 302)
		self.assertEqual(future_response.status_code, 403)
		due_session.refresh_from_db()
		future_session.refresh_from_db()
		self.assertTrue(due_session.realizada)
		self.assertIsNotNone(due_session.realizada_en)
		self.assertFalse(future_session.realizada)


class PatientProgressTests(TestCase):
	def setUp(self):
		self.doctor = Usuario.objects.create(
			email='progress-doctor@example.com',
			nombre='Fisioterapeuta',
			role=Usuario.ROLE_DOCTOR,
		)
		self.user = Usuario.objects.create(
			email='progress-patient@example.com',
			nombre='Paciente',
		)
		self.patient = Paciente.objects.create(
			usuario=self.user,
			doctor=self.doctor,
			nombre=self.user.nombre,
			email=self.user.email,
			avance=0,
			estado=Paciente.ESTADO_INICIAL,
		)
		self.patient_client = Client()
		session = self.patient_client.session
		session['current_user'] = self.user.email
		session.save()
		self.doctor_client = Client()
		session = self.doctor_client.session
		session['current_user'] = self.doctor.email
		session.save()

	def test_patient_progress_uses_goals_sessions_routines_and_clinical_history(self):
		ObjetivoTerapeutico.objects.create(
			paciente=self.patient,
			nombre='Mejorar movilidad',
			metrica='Movilidad',
			direccion=ObjetivoTerapeutico.DIRECCION_MAYOR,
			valor_objetivo=80,
			unidad='grados',
		)
		ObjetivoTerapeutico.objects.create(
			paciente=self.patient,
			nombre='Recuperar fuerza',
			metrica='Fuerza',
			direccion=ObjetivoTerapeutico.DIRECCION_MAYOR,
			valor_objetivo=30,
			unidad='kg',
		)
		EvaluacionClinica.objects.create(
			paciente=self.patient,
			nivel_dolor=8,
			metrica='Movilidad',
			valor_actual=60,
			unidad='grados',
		)
		EvaluacionClinica.objects.create(
			paciente=self.patient,
			nivel_dolor=6,
			metrica='Movilidad',
			valor_actual=85,
			unidad='grados',
		)
		EvaluacionClinica.objects.create(paciente=self.patient, nivel_dolor=7)
		Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() - timedelta(days=1),
			objetivo='Sesión realizada',
			realizada=True,
			realizada_en=timezone.now() - timedelta(hours=1),
		)
		Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() + timedelta(days=1),
			objetivo='Sesión programada',
		)
		RutinaAsignada.objects.create(
			paciente=self.patient,
			video_id='routine-1',
			titulo='Ejercicios de movilidad',
			fecha_programada=timezone.localdate(),
			completada_en=timezone.now(),
		)
		RutinaAsignada.objects.create(
			paciente=self.patient,
			video_id='routine-2',
			titulo='Ejercicios de equilibrio',
			fecha_programada=timezone.localdate(),
		)

		response = self.patient_client.get(reverse('patient_progress_data'))
		progress = response.json()['progress']

		self.assertEqual(response.status_code, 200)
		self.assertEqual(progress['components'], {
			'goals': 50,
			'sessions': 50,
			'routines': 50,
			'evaluations': 50,
		})
		self.assertEqual(progress['recoveryPercent'], 50)
		self.assertEqual((progress['goalCompleted'], progress['goalTotal']), (1, 2))
		self.assertEqual((progress['sessionsCompleted'], progress['sessionsPlanned']), (1, 2))
		self.assertEqual((progress['dailyRoutinesCompleted'], progress['dailyRoutinesAssigned']), (1, 2))
		self.assertEqual(progress['dailyPercent'], 50)
		self.assertEqual(len(progress['progressHistory']), 1)

	def test_patient_progress_page_and_api_are_scoped_to_the_authenticated_patient(self):
		other_user = Usuario.objects.create(
			email='other-progress-patient@example.com',
			nombre='Otro paciente',
		)
		other_patient = Paciente.objects.create(
			usuario=other_user,
			nombre=other_user.nombre,
			email=other_user.email,
		)
		ObjetivoTerapeutico.objects.create(
			paciente=other_patient,
			nombre='Objetivo privado',
			metrica='Movilidad',
			valor_objetivo=10,
		)

		page = self.patient_client.get(reverse('principal'))
		api = self.patient_client.get(reverse('patient_progress_data'))
		doctor_api = self.doctor_client.get(reverse('patient_progress_data'))

		self.assertEqual(page.status_code, 200)
		self.assertContains(page, 'Mi progreso')
		self.assertContains(page, 'patientRecoveryChart')
		self.assertEqual(api.status_code, 200)
		self.assertEqual(api.json()['progress']['goalTotal'], 0)
		self.assertNotIn('Objetivo privado', str(api.json()))
		self.assertEqual(doctor_api.status_code, 404)

	def test_assigned_routine_updates_when_the_patient_marks_video_completed(self):
		today = timezone.localdate()
		assignment = RutinaAsignada.objects.create(
			paciente=self.patient,
			video_id='video-1',
			titulo='Rutina de equilibrio',
			fecha_programada=today,
		)
		video = {
			'video_id': 'video-1',
			'title': 'Rutina de equilibrio',
			'category': 'Equilibrio',
		}

		with patch('princpal.views.load_videos', return_value=[video]):
			response = self.patient_client.post(reverse('complete_video', args=[0]))

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['completed'])
		assignment.refresh_from_db()
		self.assertIsNotNone(assignment.completada_en)
		view = VideoView.objects.get(video_id='video-1')
		self.assertEqual(view.rutina_asignada_id, assignment.pk)

		with patch('princpal.views.load_videos', return_value=[video]):
			undo_response = self.patient_client.post(reverse('complete_video', args=[0]))

		self.assertEqual(undo_response.status_code, 200)
		self.assertFalse(undo_response.json()['completed'])
		assignment.refresh_from_db()
		view.refresh_from_db()
		self.assertIsNone(assignment.completada_en)
		self.assertIsNone(view.rutina_asignada_id)

	def test_clinical_evaluations_update_the_persisted_progress_history(self):
		evaluation_url = reverse('register_clinical_evaluation', args=[self.patient.pk])
		self.doctor_client.post(evaluation_url, {'nivel_dolor': '8'})
		self.doctor_client.post(evaluation_url, {'nivel_dolor': '5'})

		self.patient.refresh_from_db()
		progress = self.patient_client.get(reverse('patient_progress_data')).json()['progress']

		self.assertEqual(progress['components']['evaluations'], 100)
		self.assertEqual(progress['recoveryPercent'], 25)
		self.assertEqual(self.patient.historial_avance[-1]['avance'], 25)

	def test_doctor_can_assign_a_routine_only_to_an_assigned_patient(self):
		routine = {
			'video_id': 'video-2',
			'title': 'Rutina de estiramiento',
		}
		url = reverse('assign_routine', args=[self.patient.pk])
		form_data = {
			'video_id': 'video-2',
			'fecha_programada': timezone.localdate().isoformat(),
		}

		with patch('princpal.views.load_videos', return_value=[routine]):
			response = self.doctor_client.post(url, form_data)

		self.assertEqual(response.status_code, 302)
		assignment = RutinaAsignada.objects.get(paciente=self.patient)
		self.assertEqual(assignment.titulo, routine['title'])
		self.assertEqual(assignment.fecha_programada, timezone.localdate())

		other_doctor = Usuario.objects.create(
			email='different-progress-doctor@example.com',
			nombre='Otro fisioterapeuta',
			role=Usuario.ROLE_DOCTOR,
		)
		other_client = Client()
		session = other_client.session
		session['current_user'] = other_doctor.email
		session.save()
		with patch('princpal.views.load_videos', return_value=[routine]):
			unauthorized = other_client.post(url, form_data)

		self.assertEqual(unauthorized.status_code, 404)
		self.assertEqual(RutinaAsignada.objects.filter(paciente=self.patient).count(), 1)
