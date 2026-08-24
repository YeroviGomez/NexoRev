from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from crear_cuenta.models import Usuario


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TwoFactorLoginTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(email='prueba@gmail.com', nombre='Prueba')
		self.usuario.set_password('ClaveSegura123')
		self.usuario.save()

	def test_login_requires_email_code_before_creating_session(self):
		response = self.client.post(reverse('login'), {
			'email': self.usuario.email,
			'password': 'ClaveSegura123',
		})

		self.assertRedirects(response, reverse('verify_2fa'))
		self.assertNotIn('current_user', self.client.session)
		self.assertEqual(len(mail.outbox), 1)

		verification_code = self.client.session.get('pending_2fa_id')
		self.assertIsNotNone(verification_code)

	def test_valid_email_code_opens_principal(self):
		self.client.post(reverse('login'), {
			'email': self.usuario.email,
			'password': 'ClaveSegura123',
		})
		from .models import TwoFactorCode
		code = TwoFactorCode.objects.get(email=self.usuario.email).code

		response = self.client.post(reverse('verify_2fa'), {'code': code})

		self.assertRedirects(response, reverse('principal'))
		self.assertEqual(self.client.session.get('current_user'), self.usuario.email)
