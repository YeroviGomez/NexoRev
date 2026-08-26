import base64
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from crear_cuenta.models import Usuario


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

		self.assertEqual(response.status_code, 302)

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

# Create your tests here.
