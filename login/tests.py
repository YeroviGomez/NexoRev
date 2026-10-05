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
		self.assertTrue(self.client.session.get('show_initial_guide'))
		self.assertEqual(len(mail.outbox), 2)
		self.assertEqual(
			mail.outbox[1].subject,
			'Nuevo inicio de sesión - Nexo ReV',
		)
		self.assertEqual(mail.outbox[1].to, [self.usuario.email])
		self.assertIn('Se inició sesión en tu cuenta de Nexo ReV', mail.outbox[1].body)

		principal_response = self.client.get(reverse('principal'))
		self.assertEqual(principal_response.status_code, 200)
		self.assertContains(principal_response, 'data-show-initial-guide="true"')
		self.assertNotIn('show_initial_guide', self.client.session)

		refreshed_response = self.client.get(reverse('principal'))
		self.assertContains(refreshed_response, 'data-show-initial-guide="false"')

	def test_invalid_email_code_does_not_send_login_notification(self):
		self.client.post(reverse('login'), {
			'email': self.usuario.email,
			'password': 'ClaveSegura123',
		})

		response = self.client.post(reverse('verify_2fa'), {'code': '000000'})

		self.assertEqual(response.status_code, 200)
		self.assertNotIn('current_user', self.client.session)
		self.assertEqual(len(mail.outbox), 1)
