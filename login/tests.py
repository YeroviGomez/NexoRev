from contextlib import redirect_stdout
from io import StringIO
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from crear_cuenta.models import SecurityQuestion, Usuario
from .models import RecoverySecurityAttempt, TwoFactorCode


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


class SessionTerminationTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(
			email='sesion-activa@gmail.com',
			nombre='Usuario activo',
		)
		session = self.client.session
		session['current_user'] = self.usuario.email
		session['current_user_role'] = Usuario.ROLE_PACIENTE
		session.save()
		self.session_key = session.session_key

	def test_cerrar_sesion_elimina_la_sesion_del_servidor_y_registra_quien_y_cuando(self):
		self.assertTrue(Session.objects.filter(session_key=self.session_key).exists())

		with self.assertLogs('nexorev.auth', level='INFO') as captured:
			response = self.client.post(reverse('logout'))

		self.assertRedirects(response, reverse('login'))
		self.assertFalse(Session.objects.filter(session_key=self.session_key).exists())
		self.assertNotIn('current_user', self.client.session)
		self.assertIn(self.usuario.email, captured.output[0])
		self.assertIn('session_terminated', captured.output[0])

	def test_logout_no_permite_get_para_cortar_la_sesion(self):
		response = self.client.get(reverse('logout'))

		self.assertEqual(response.status_code, 405)
		self.assertEqual(self.client.session.get('current_user'), self.usuario.email)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class UnrecognizedLoginSessionTests(TestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(
			email='inicio-notificado@gmail.com',
			nombre='Usuario notificado',
		)
		self.usuario.set_password('ClaveSegura123')
		self.usuario.save(update_fields=['password'])

	def test_terminal_link_confirma_y_revoca_solo_la_sesion_notificada(self):
		self.client.post(reverse('login'), {
			'email': self.usuario.email,
			'password': 'ClaveSegura123',
		})
		code = TwoFactorCode.objects.get(email=self.usuario.email).code
		terminal = StringIO()

		with redirect_stdout(terminal):
			response = self.client.post(
				reverse('verify_2fa'),
				{'code': code},
			)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], reverse('principal'))
		log_line = terminal.getvalue()
		self.assertIn('[Nuevo inicio de sesión]', log_line)
		self.assertIn(self.usuario.email, log_line)
		self.assertIn('terminar esa sesión', log_line)
		match = re.search(r'https?://\S+', log_line)
		self.assertIsNotNone(match)

		target_session_key = self.client.session.session_key
		notified_device = Client()
		notified_device.cookies[settings.SESSION_COOKIE_NAME] = target_session_key
		self.assertTrue(Session.objects.filter(session_key=target_session_key).exists())
		self.assertEqual(notified_device.get(reverse('principal')).status_code, 200)
		self.assertEqual(
			notified_device.get(reverse('session_status_api')).status_code,
			200,
		)
		confirmation_path = urlsplit(match.group(0)).path
		confirmation = self.client.get(confirmation_path)
		self.assertEqual(confirmation.status_code, 200)
		self.assertContains(confirmation, self.usuario.email)
		self.assertContains(confirmation, 'Sí, terminar esta sesión')
		self.assertNotContains(confirmation, 'target="_blank"')
		self.assertTrue(Session.objects.filter(session_key=target_session_key).exists())

		with redirect_stdout(terminal):
			revoked = self.client.post(confirmation_path)

		self.assertEqual(revoked.status_code, 302)
		self.assertEqual(revoked['Location'], reverse('login'))
		self.assertFalse(Session.objects.filter(session_key=target_session_key).exists())
		self.assertIn('[Sesión no reconocida terminada]', terminal.getvalue())
		self.assertIn(f'a quién: {self.usuario.email}', terminal.getvalue())
		self.assertEqual(notified_device.get(reverse('principal')).status_code, 302)
		self.assertEqual(
			notified_device.get(reverse('session_status_api')).status_code,
			401,
		)
		self.assertEqual(self.client.cookies[settings.SESSION_COOKIE_NAME].value, '')

	def test_enlace_alterado_no_invalida_ninguna_sesion(self):
		session = self.client.session
		session['current_user'] = self.usuario.email
		session.save()
		session_key = session.session_key

		response = self.client.get(reverse('revoke_login_session', args=['token-invalido']))

		self.assertEqual(response.status_code, 400)
		self.assertTrue(Session.objects.filter(session_key=session_key).exists())

	def test_origen_null_solo_permite_revocar_con_token_csrf_valido(self):
		self.client.post(reverse('login'), {
			'email': self.usuario.email,
			'password': 'ClaveSegura123',
		})
		code = TwoFactorCode.objects.get(email=self.usuario.email).code
		terminal = StringIO()
		with redirect_stdout(terminal):
			self.client.post(reverse('verify_2fa'), {'code': code})

		match = re.search(r'https?://\S+', terminal.getvalue())
		self.assertIsNotNone(match)
		confirmation_path = urlsplit(match.group(0)).path
		target_session_key = self.client.session.session_key
		csrf_client = Client(enforce_csrf_checks=True)
		confirmation = csrf_client.get(confirmation_path)
		csrf_match = re.search(
			r'name="csrfmiddlewaretoken" value="([^"]+)"',
			confirmation.content.decode(),
		)
		self.assertIsNotNone(csrf_match)
		csrf_token = csrf_match.group(1)

		rejected = csrf_client.post(
			confirmation_path,
			{'csrfmiddlewaretoken': 'invalid'},
			HTTP_ORIGIN='null',
		)
		self.assertEqual(rejected.status_code, 403)
		self.assertTrue(Session.objects.filter(session_key=target_session_key).exists())

		with redirect_stdout(terminal):
			revoked = csrf_client.post(
				confirmation_path,
				{'csrfmiddlewaretoken': csrf_token},
				HTTP_ORIGIN='null',
			)
		self.assertEqual(revoked.status_code, 302)
		self.assertFalse(Session.objects.filter(session_key=target_session_key).exists())


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordRecoverySecurityTests(TestCase):
	def setUp(self):
		self.user = Usuario.objects.create(
			email='recovery-security@gmail.com',
			nombre='Usuario Recuperación',
		)
		self.user.set_password('ClaveAnterior123')
		self.user.save(update_fields=['password'])

	def configure_questions(self):
		for prompt, answer in (
			('¿Cuál es el nombre de tu primera mascota?', 'Luna'),
			('¿Cuál es la ciudad donde naciste?', 'San Salvador'),
		):
			question = SecurityQuestion(
				user=self.user,
				question=prompt,
				is_custom=False,
			)
			question.set_answer(answer)
			question.save()

	def start_recovery(self):
		response = self.client.post(reverse('forgot_password'), {'email': self.user.email})
		self.assertRedirects(response, reverse('verify_recovery_code'))
		return self.client.session['recovery_code']

	def verify_email_code(self, code):
		return self.client.post(reverse('verify_recovery_code'), {'code': code})

	def test_recovery_requires_email_code_then_all_security_answers(self):
		self.configure_questions()
		code = self.start_recovery()

		unverified_page = self.client.get(reverse('verify_recovery_code'))
		self.assertNotContains(unverified_page, '¿Cuál es el nombre de tu primera mascota?')
		self.assertRedirects(self.verify_email_code(code), reverse('verify_recovery_code'))
		questions_page = self.client.get(reverse('verify_recovery_code'))
		self.assertContains(questions_page, '¿Cuál es el nombre de tu primera mascota?')
		self.assertContains(questions_page, 'name="answer_')
		self.assertNotContains(questions_page, 'Luna')

		questions = list(SecurityQuestion.objects.filter(user=self.user))
		answers_response = self.client.post(reverse('verify_recovery_code'), {
			f'answer_{questions[0].pk}': 'luna',
			f'answer_{questions[1].pk}': 'SAN SALVADOR',
		})
		self.assertRedirects(answers_response, reverse('verify_recovery_code'))
		password_response = self.client.post(reverse('verify_recovery_code'), {
			'password': 'ClaveNueva456',
			'password_confirm': 'ClaveNueva456',
		})

		self.assertContains(password_response, 'Contraseña actualizada correctamente')
		self.user.refresh_from_db()
		self.assertTrue(self.user.check_password('ClaveNueva456'))
		self.assertFalse(self.client.session.get('recovery_email'))

	def test_incorrect_security_answers_deny_recovery_and_lock_after_five_attempts(self):
		self.configure_questions()
		code = self.start_recovery()
		self.verify_email_code(code)
		questions = list(SecurityQuestion.objects.filter(user=self.user))

		for attempt in range(5):
			response = self.client.post(reverse('verify_recovery_code'), {
				f'answer_{questions[0].pk}': 'respuesta incorrecta',
				f'answer_{questions[1].pk}': 'respuesta incorrecta',
			})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Se agotaron los intentos de recuperación')
		self.assertEqual(RecoverySecurityAttempt.objects.filter(email=self.user.email).count(), 5)
		self.user.refresh_from_db()
		self.assertTrue(self.user.check_password('ClaveAnterior123'))

		blocked = self.client.post(reverse('forgot_password'), {'email': self.user.email})
		self.assertEqual(blocked.status_code, 200)
		self.assertContains(blocked, 'Espera 15 minutos')
		self.assertEqual(len(mail.outbox), 1)

	def test_users_without_configured_questions_can_recover_with_email_code(self):
		code = self.start_recovery()
		self.verify_email_code(code)
		page = self.client.get(reverse('verify_recovery_code'))
		self.assertContains(page, 'Nueva Contraseña')
		response = self.client.post(reverse('verify_recovery_code'), {
			'password': 'ClaveNueva456',
			'password_confirm': 'ClaveNueva456',
		})

		self.assertContains(response, 'Contraseña actualizada correctamente')
		self.user.refresh_from_db()
		self.assertTrue(self.user.check_password('ClaveNueva456'))

	def test_recovery_restarts_if_security_questions_change_after_code_request(self):
		self.configure_questions()
		code = self.start_recovery()
		self.verify_email_code(code)
		SecurityQuestion.objects.filter(user=self.user).delete()

		response = self.client.get(reverse('verify_recovery_code'))

		self.assertContains(response, 'Tus preguntas de seguridad cambiaron')
		self.assertNotIn('recovery_email', self.client.session)
		self.user.refresh_from_db()
		self.assertTrue(self.user.check_password('ClaveAnterior123'))
