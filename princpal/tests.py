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
from .models import Paciente, VideoView


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
