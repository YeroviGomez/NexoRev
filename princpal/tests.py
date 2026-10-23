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
	EjercicioPlantillaRutina,
	EjercicioRutinaAsignada,
	EvaluacionClinica,
	OcurrenciaRutina,
	ObjetivoTerapeutico,
	Paciente,
	PlantillaRutina,
	RutinaAsignada,
	Sesion,
	SolicitudReagendamiento,
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

	def test_acepta_cero_en_la_escala_eva(self):
		response = self.client.get(reverse('principal'))
		self.assertContains(response, 'min="0"')
		self.assertContains(response, 'Nivel 0 sin dolor')

		submission = self.client.post(
			reverse('principal'),
			{**self.respuestas, 'nivel_dolor': '0'},
		)

		self.assertEqual(submission.status_code, 302)
		self.assertEqual(Diagnostico.objects.get(usuario=self.usuario).nivel_dolor, 0)
		self.assertEqual(
			EvaluacionClinica.objects.get(paciente__usuario=self.usuario).nivel_dolor,
			0,
		)

	def test_diagnostico_muestra_eva_de_cero_a_diez(self):
		response = self.client.get(reverse('principal'))

		self.assertContains(response, 'min="0"')
		self.assertContains(response, 'max="10"')
		self.assertContains(response, 'Nivel 0 sin dolor')

	def test_rechaza_dolor_eva_negativo(self):
		response = self.client.post(
			reverse('principal'),
			{**self.respuestas, 'nivel_dolor': '-1'},
		)

		self.assertEqual(response.status_code, 200)
		self.assertIn('nivel_dolor', response.context['form'].errors)
		self.assertFalse(Diagnostico.objects.exists())

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
		self.assertEqual(len(sesiones), 2)
		programada = next(item for item in sesiones if item['objective'] == 'Rutina de movilidad')
		cancelada = next(item for item in sesiones if item['objective'] == 'Sesión cancelada')
		self.assertEqual(programada['date'], timezone.localtime(fecha).date().isoformat())
		self.assertEqual(programada['time'], timezone.localtime(fecha).strftime('%H:%M'))
		self.assertEqual(programada['status'], Sesion.ESTADO_PROGRAMADA)
		self.assertEqual(cancelada['status'], Sesion.ESTADO_CANCELADA)
		self.assertContains(response, 'calendarSessionsData')
		self.assertContains(response, 'Solicitar cambio de fecha de una sesión')
		self.assertContains(response, 'Sesiones y cambios de fecha')
		content = response.content.decode()
		self.assertLess(content.index('calendar-layout'), content.index('reschedule-history'))


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
		self.assertEqual(sesion['estado'], Sesion.ESTADO_PROGRAMADA)
		self.assertEqual(sesion['duracion_minutos'], 45)
		self.assertEqual(
			sesion['fecha_local'],
			timezone.localtime(self.sesion.fecha).strftime('%Y-%m-%dT%H:%M'),
		)

	def test_expediente_incluye_tabs_de_datos_clinicos_y_solicitudes_pendientes(self):
		evaluation = EvaluacionClinica.objects.create(
			paciente=self.paciente,
			nivel_dolor=4,
			metrica='Movilidad',
			valor_actual=75,
			unidad='grados',
		)
		goal = ObjetivoTerapeutico.objects.create(
			paciente=self.paciente,
			nombre='Recuperar movilidad',
			metrica='Movilidad',
			valor_objetivo=90,
			unidad='grados',
		)
		template = PlantillaRutina.objects.create(
			doctor=self.doctor,
			nombre='Movilidad de rodilla',
		)
		assignment = RutinaAsignada.objects.create(
			paciente=self.paciente,
			video_id='movilidad',
			titulo=template.nombre,
			fecha_programada=timezone.localdate(),
			plantilla=template,
			fecha_inicio=timezone.localdate(),
			fecha_fin=timezone.localdate() + timedelta(days=7),
			dias_semana=[0, 2, 4],
		)
		EjercicioRutinaAsignada.objects.create(
			asignacion=assignment,
			video_id='movilidad',
			titulo='Flexión de rodilla',
			orden=1,
			series=3,
			repeticiones='10',
		)
		OcurrenciaRutina.objects.create(
			asignacion=assignment,
			fecha=timezone.localdate(),
			nivel_dolor=2,
			dificultad=OcurrenciaRutina.DIFICULTAD_FACIL,
			comentario='Sin molestias.',
		)
		pending_request = SolicitudReagendamiento.objects.create(
			sesion=self.sesion,
			motivo='Necesito cambiar el horario.',
			fecha_original=self.sesion.fecha,
			fecha_propuesta=timezone.now() + timedelta(days=5),
		)

		response = self.doctor_client.get(reverse('paciente_detail_api', args=[self.paciente.pk]))

		self.assertEqual(response.status_code, 200)
		profile = response.json()['paciente']
		self.assertEqual(profile['evaluaciones'][0]['pain'], evaluation.nivel_dolor)
		self.assertEqual(
			profile['evaluaciones'][0]['date'],
			timezone.localtime(evaluation.fecha).strftime('%d/%m/%Y %H:%M'),
		)
		self.assertEqual(
			profile['evaluaciones'][0]['date_iso'],
			timezone.localtime(evaluation.fecha).isoformat(),
		)
		self.assertEqual(profile['objetivos'][0]['id'], goal.pk)
		self.assertEqual(profile['rutinas'][0]['title'], template.nombre)
		self.assertEqual(profile['rutinas'][0]['exercises'][0]['series'], 3)
		self.assertEqual(profile['rutinas'][0]['occurrences'][0]['comment'], 'Sin molestias.')
		self.assertEqual(profile['sesiones'][0]['solicitud_pendiente']['id'], pending_request.pk)

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

	def test_rechaza_reagendar_si_choca_con_otra_sesion_del_medico(self):
		fecha_objetivo = timezone.localtime(
			timezone.now() + timedelta(days=5)
		).replace(second=0, microsecond=0)
		otro_usuario = Usuario.objects.create(
			email='otro-paciente-choque@example.com',
			nombre='Otro paciente',
		)
		otro_paciente = Paciente.objects.create(
			usuario=otro_usuario,
			doctor=self.doctor,
			nombre=otro_usuario.nombre,
			email=otro_usuario.email,
		)
		Sesion.objects.create(
			paciente=otro_paciente,
			fecha=fecha_objetivo,
			objetivo='Otra sesión',
		)

		response = self.doctor_client.post(
			reverse('reschedule_session', args=[self.paciente.pk, self.sesion.pk]),
			{'fecha': fecha_objetivo.strftime('%Y-%m-%dT%H:%M')},
		)

		self.assertEqual(response.status_code, 409)
		self.assertIn('médico', response.json()['error'])
		self.sesion.refresh_from_db()
		self.assertNotEqual(timezone.localtime(self.sesion.fecha), fecha_objetivo)


class RescheduleRequestTests(TestCase):
	def setUp(self):
		self.doctor = Usuario.objects.create(
			email='medico-solicitud@example.com',
			nombre='Médico de prueba',
			role=Usuario.ROLE_DOCTOR,
		)
		self.usuario = Usuario.objects.create(
			email='paciente-solicitud@example.com',
			nombre='Paciente de prueba',
		)
		self.paciente = Paciente.objects.create(
			usuario=self.usuario,
			doctor=self.doctor,
			nombre=self.usuario.nombre,
			email=self.usuario.email,
		)
		self.sesion = Sesion.objects.create(
			paciente=self.paciente,
			fecha=timezone.now() + timedelta(days=2),
			objetivo='Terapia de movilidad',
		)
		self.patient_client = Client()
		self.doctor_client = Client()
		self.autenticar(self.patient_client, self.usuario)
		self.autenticar(self.doctor_client, self.doctor)

	def autenticar(self, client, usuario):
		session = client.session
		session['current_user'] = usuario.email
		session.save()

	def fecha_futura(self, dias):
		return timezone.localtime(
			timezone.now() + timedelta(days=dias)
		).replace(second=0, microsecond=0)

	def solicitar_cambio(self, cliente=None):
		propuesta = self.fecha_futura(6)
		response = (cliente or self.patient_client).post(
			reverse('create_reschedule_request', args=[self.sesion.pk]),
			{
				'motivo': 'Tengo una cita médica ese día.',
				'fecha_propuesta': propuesta.strftime('%Y-%m-%dT%H:%M'),
			},
		)
		return response, propuesta

	def test_paciente_solicita_cambio_sin_modificar_el_horario_original(self):
		fecha_original = self.sesion.fecha
		response, propuesta = self.solicitar_cambio()

		self.assertEqual(response.status_code, 201)
		self.assertTrue(response.json()['success'])
		solicitud = SolicitudReagendamiento.objects.get(sesion=self.sesion)
		self.assertEqual(solicitud.estado, SolicitudReagendamiento.ESTADO_PENDIENTE)
		self.assertEqual(solicitud.motivo, 'Tengo una cita médica ese día.')
		self.assertEqual(timezone.localtime(solicitud.fecha_propuesta), propuesta)
		self.sesion.refresh_from_db()
		self.assertEqual(self.sesion.fecha, fecha_original)

	def test_paciente_no_puede_cambiar_horario_por_la_ruta_directa(self):
		fecha_original = self.sesion.fecha
		propuesta = self.fecha_futura(6)
		response = self.patient_client.post(
			reverse('reschedule_session', args=[self.paciente.pk, self.sesion.pk]),
			{'fecha': propuesta.strftime('%Y-%m-%dT%H:%M')},
		)
		schedule_response = self.patient_client.post(
			reverse('schedule_session', args=[self.paciente.pk]),
			{
				'fecha': propuesta.strftime('%Y-%m-%dT%H:%M'),
				'objetivo': 'Sesión agregada por paciente',
			},
		)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(schedule_response.status_code, 403)
		self.assertFalse(SolicitudReagendamiento.objects.exists())
		self.assertEqual(Sesion.objects.filter(paciente=self.paciente).count(), 1)
		self.sesion.refresh_from_db()
		self.assertEqual(self.sesion.fecha, fecha_original)

	def test_calendario_y_dashboard_medico_muestran_fecha_y_estado_de_solicitud(self):
		response, _ = self.solicitar_cambio()
		request_id = response.json()['request']['id']
		patient_calendar = self.patient_client.get(reverse('principal'))
		request_item = SolicitudReagendamiento.objects.get(pk=request_id)
		self.assertContains(
			patient_calendar,
			timezone.localtime(request_item.fecha_propuesta).strftime('%d/%m/%Y %H:%M'),
		)

		calendar_response = self.doctor_client.get(reverse('principal'))
		calendar_session = calendar_response.context['calendar_sessions'][0]
		self.assertEqual(calendar_session['patient'], self.paciente.nombre)
		self.assertEqual(calendar_session['request']['id'], request_id)
		self.assertEqual(calendar_session['request']['status'], SolicitudReagendamiento.ESTADO_PENDIENTE)
		self.assertEqual(calendar_session['status'], 'reagendamiento_solicitado')
		self.assertEqual(self.sesion.estado, Sesion.ESTADO_PROGRAMADA)
		self.assertContains(calendar_response, 'Solicitudes de cambio de sesión')
		self.assertContains(calendar_response, 'Tengo una cita médica ese día.')
		self.assertContains(calendar_response, self.paciente.nombre)

		dashboard_response = self.doctor_client.get(reverse('doctor_dashboard_data'))
		session_data = dashboard_response.json()['patients'][0]['sessions'][0]
		self.assertEqual(
			session_data['scheduledDate'],
			timezone.localtime(self.sesion.fecha).isoformat(),
		)
		self.assertEqual(
			dashboard_response.json()['pending_reschedule_requests'][0]['id'],
			request_id,
		)

	def test_medico_aprueba_y_sesiones_del_calendario_actualizan_fecha(self):
		response, propuesta = self.solicitar_cambio()
		solicitud_id = response.json()['request']['id']

		with patch('princpal.views.send_mail') as send_mail:
			decision = self.doctor_client.post(
				reverse('review_reschedule_request', args=[solicitud_id]),
				{'accion': 'aprobar'},
			)

		self.assertEqual(decision.status_code, 200)
		self.sesion.refresh_from_db()
		self.assertEqual(timezone.localtime(self.sesion.fecha), propuesta)
		solicitud = SolicitudReagendamiento.objects.get(pk=solicitud_id)
		self.assertEqual(solicitud.estado, SolicitudReagendamiento.ESTADO_APROBADA)
		send_mail.assert_called_once()
		self.assertEqual(send_mail.call_args.args[3], [self.usuario.email])
		self.assertIn('aprobó tu solicitud', send_mail.call_args.args[1])
		updated_dashboard = self.doctor_client.get(reverse('doctor_dashboard_data')).json()
		self.assertEqual(
			updated_dashboard['patients'][0]['sessions'][0]['scheduledDate'],
			timezone.localtime(propuesta).isoformat(),
		)
		patient_response = self.patient_client.get(reverse('principal'))
		self.assertEqual(patient_response.context['calendar_sessions'][0]['date'], propuesta.date().isoformat())
		self.assertEqual(
			patient_response.context['calendar_sessions'][0]['request']['status'],
			SolicitudReagendamiento.ESTADO_APROBADA,
		)
		self.assertEqual(
			patient_response.context['calendar_sessions'][0]['status'],
			Sesion.ESTADO_PROGRAMADA,
		)
		self.assertContains(patient_response, 'Cambio aprobado')
		self.assertContains(patient_response, 'Nueva fecha confirmada')
		doctor_response = self.doctor_client.get(reverse('principal'))
		self.assertEqual(
			doctor_response.context['calendar_sessions'][0]['date'],
			propuesta.date().isoformat(),
		)

	def test_medico_puede_proponer_fecha_y_paciente_debe_aceptarla(self):
		response, _ = self.solicitar_cambio()
		solicitud_id = response.json()['request']['id']
		propuesta_alternativa = self.fecha_futura(8)
		fecha_original = self.sesion.fecha

		with patch('princpal.views.send_mail'):
			decision = self.doctor_client.post(
				reverse('review_reschedule_request', args=[solicitud_id]),
				{
					'accion': 'proponer',
					'fecha_alternativa': propuesta_alternativa.strftime('%Y-%m-%dT%H:%M'),
					'respuesta': 'Este horario está disponible.',
				},
			)

		self.assertEqual(decision.status_code, 200)
		self.assertEqual(decision.json()['status'], SolicitudReagendamiento.ESTADO_PENDIENTE)
		self.sesion.refresh_from_db()
		self.assertEqual(self.sesion.fecha, fecha_original)
		accepted = self.patient_client.post(
			reverse('respond_to_reschedule_proposal', args=[solicitud_id]),
			{'accion': 'aceptar'},
		)
		self.assertEqual(accepted.status_code, 200)
		self.sesion.refresh_from_db()
		self.assertEqual(timezone.localtime(self.sesion.fecha), propuesta_alternativa)
		self.assertEqual(
			SolicitudReagendamiento.objects.get(pk=solicitud_id).estado,
			SolicitudReagendamiento.ESTADO_APROBADA,
		)

	def test_medico_no_puede_aprobar_un_cambio_con_choque_de_horario(self):
		response, propuesta = self.solicitar_cambio()
		Sesion.objects.create(
			paciente=self.paciente,
			fecha=propuesta,
			objetivo='Otra sesión del paciente',
		)

		decision = self.doctor_client.post(
			reverse('review_reschedule_request', args=[response.json()['request']['id']]),
			{'accion': 'aprobar'},
		)

		self.assertEqual(decision.status_code, 409)
		self.assertIn('paciente', decision.json()['error'])
		self.sesion.refresh_from_db()
		self.assertNotEqual(timezone.localtime(self.sesion.fecha), propuesta)
		self.assertEqual(
			SolicitudReagendamiento.objects.get(pk=response.json()['request']['id']).estado,
			SolicitudReagendamiento.ESTADO_PENDIENTE,
		)

	def test_paciente_no_puede_aceptar_una_alternativa_con_choque_de_horario(self):
		response, _ = self.solicitar_cambio()
		request_id = response.json()['request']['id']
		alternativa = self.fecha_futura(8)
		Sesion.objects.create(
			paciente=self.paciente,
			fecha=alternativa,
			objetivo='Otra sesión del paciente',
		)
		self.doctor_client.post(
			reverse('review_reschedule_request', args=[request_id]),
			{
				'accion': 'proponer',
				'fecha_alternativa': alternativa.strftime('%Y-%m-%dT%H:%M'),
			},
		)

		accepted = self.patient_client.post(
			reverse('respond_to_reschedule_proposal', args=[request_id]),
			{'accion': 'aceptar'},
		)

		self.assertEqual(accepted.status_code, 409)
		self.assertIn('paciente', accepted.json()['error'])
		self.sesion.refresh_from_db()
		self.assertNotEqual(timezone.localtime(self.sesion.fecha), alternativa)

	def test_paciente_ve_propuesta_alternativa_y_solicitudes_rechazadas_en_su_historial(self):
		response, _ = self.solicitar_cambio()
		solicitud_id = response.json()['request']['id']
		fecha_alternativa = self.fecha_futura(8)
		with patch('princpal.views.send_mail'):
			self.doctor_client.post(
				reverse('review_reschedule_request', args=[solicitud_id]),
				{
					'accion': 'proponer',
					'fecha_alternativa': fecha_alternativa.strftime('%Y-%m-%dT%H:%M'),
				},
			)

		pending_response = self.patient_client.get(reverse('principal'))
		self.assertContains(pending_response, 'Mis solicitudes de cambio')
		self.assertContains(pending_response, 'Nueva fecha propuesta')
		self.assertContains(pending_response, fecha_alternativa.strftime('%d/%m/%Y'))
		self.assertContains(pending_response, 'Aceptar propuesta')
		self.assertContains(pending_response, 'La fecha actual sigue vigente')

		otra_sesion = Sesion.objects.create(
			paciente=self.paciente,
			fecha=self.fecha_futura(3),
			objetivo='Ejercicios de equilibrio',
		)
		otra_solicitud_response = self.patient_client.post(
			reverse('create_reschedule_request', args=[otra_sesion.pk]),
			{
				'motivo': 'No puedo asistir ese día.',
				'fecha_propuesta': self.fecha_futura(9).strftime('%Y-%m-%dT%H:%M'),
			},
		)
		with patch('princpal.views.send_mail'):
			rejected = self.doctor_client.post(
				reverse(
					'review_reschedule_request',
					args=[otra_solicitud_response.json()['request']['id']],
				),
				{'accion': 'rechazar', 'respuesta': 'No hay horario disponible.'},
			)

		self.assertEqual(rejected.status_code, 200)
		rejected_response = self.patient_client.get(reverse('principal'))
		self.assertContains(rejected_response, 'Rechazada')
		self.assertContains(rejected_response, 'La solicitud fue rechazada')
		self.assertContains(rejected_response, 'No hay horario disponible.')

	def test_medico_rechaza_sin_alterar_horario_y_notifica_al_paciente(self):
		response, _ = self.solicitar_cambio()
		solicitud_id = response.json()['request']['id']
		fecha_original = self.sesion.fecha

		with patch('princpal.views.send_mail') as send_mail:
			decision = self.doctor_client.post(
				reverse('review_reschedule_request', args=[solicitud_id]),
				{'accion': 'rechazar', 'respuesta': 'No hay disponibilidad.'},
			)

		self.assertEqual(decision.status_code, 200)
		self.sesion.refresh_from_db()
		self.assertEqual(self.sesion.fecha, fecha_original)
		send_mail.assert_called_once()
		self.assertEqual(
			SolicitudReagendamiento.objects.get(pk=solicitud_id).estado,
			SolicitudReagendamiento.ESTADO_RECHAZADA,
		)

	def test_otro_medico_no_puede_revisar_la_solicitud(self):
		response, _ = self.solicitar_cambio()
		fecha_original = self.sesion.fecha
		otro_medico = Usuario.objects.create(
			email='medico-ajeno@example.com',
			nombre='Médico ajeno',
			role=Usuario.ROLE_DOCTOR,
		)
		otro_cliente = Client()
		self.autenticar(otro_cliente, otro_medico)

		decision = otro_cliente.post(
			reverse('review_reschedule_request', args=[response.json()['request']['id']]),
			{'accion': 'aprobar'},
		)

		self.assertEqual(decision.status_code, 404)
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
			estado=Sesion.ESTADO_COMPLETADA,
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
		goal = ObjetivoTerapeutico.objects.get(paciente=self.patient)
		future_date = timezone.localtime(timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
		session_response = self.client.post(
			reverse('schedule_session', args=[self.patient.pk]),
			{
				'fecha': future_date,
				'objetivo_terapeutico': str(goal.pk),
				'nota_objetivo': 'Progresar de forma gradual.',
				'duracion_minutos': '45',
				'enlace_ubicacion': 'Consultorio 2',
			},
		)

		self.assertEqual(evaluation_response.status_code, 302)
		self.assertEqual(goal_response.status_code, 302)
		self.assertEqual(session_response.status_code, 302)
		self.assertEqual(EvaluacionClinica.objects.filter(paciente=self.patient).count(), 1)
		self.assertEqual(ObjetivoTerapeutico.objects.filter(paciente=self.patient).count(), 1)
		self.assertEqual(Sesion.objects.filter(paciente=self.patient, activo=True).count(), 1)
		session = Sesion.objects.get(paciente=self.patient)
		self.assertEqual(session.objetivo, goal.nombre)
		self.assertEqual(session.objetivo_terapeutico, goal)
		self.assertEqual(session.nota_objetivo, 'Progresar de forma gradual.')
		self.assertEqual(session.duracion_minutos, 45)
		self.assertEqual(session.enlace_ubicacion, 'Consultorio 2')
		self.assertEqual(session.estado, Sesion.ESTADO_PROGRAMADA)

	def test_no_agenda_si_el_paciente_o_el_medico_tienen_un_choque(self):
		goal = ObjetivoTerapeutico.objects.create(
			paciente=self.patient,
			nombre='Recuperar movilidad',
			metrica='Movilidad',
			valor_objetivo=90,
		)
		fecha = timezone.localtime(timezone.now() + timedelta(days=4)).replace(
			hour=10, minute=0, second=0, microsecond=0,
		)
		Sesion.objects.create(
			paciente=self.patient,
			fecha=fecha,
			objetivo='Sesión existente',
			duracion_minutos=45,
		)

		response = self.client.post(
			reverse('schedule_session', args=[self.patient.pk]),
			{
				'fecha': (fecha + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'),
				'objetivo_terapeutico': str(goal.pk),
				'duracion_minutos': '45',
			},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Sesion.objects.filter(paciente=self.patient).count(), 1)
		self.assertContains(response, 'El horario se cruza con otra sesión del paciente y del médico asignado.')

	def test_agendar_rechaza_objetivos_de_otro_paciente(self):
		otro_paciente = Paciente.objects.create(
			doctor=self.doctor,
			nombre='Paciente distinto',
			email='paciente-distinto@example.com',
		)
		otro_objetivo = ObjetivoTerapeutico.objects.create(
			paciente=otro_paciente,
			nombre='Objetivo privado',
			metrica='Movilidad',
			valor_objetivo=10,
		)

		response = self.client.post(
			reverse('schedule_session', args=[self.patient.pk]),
			{
				'fecha': timezone.localtime(timezone.now() + timedelta(days=4)).strftime('%Y-%m-%dT%H:%M'),
				'objetivo_terapeutico': str(otro_objetivo.pk),
				'duracion_minutos': '45',
			},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		self.assertFalse(Sesion.objects.filter(paciente=self.patient).exists())

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

	def test_doctor_can_cancel_a_future_session_and_mark_a_past_one_as_no_show(self):
		future_session = Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() + timedelta(days=1),
			objetivo='Sesión futura',
		)
		past_session = Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() - timedelta(minutes=5),
			objetivo='Sesión pasada',
		)

		cancelled = self.client.post(
			reverse('complete_session', args=[future_session.pk]),
			{'estado': Sesion.ESTADO_CANCELADA},
		)
		no_show = self.client.post(
			reverse('complete_session', args=[past_session.pk]),
			{'estado': Sesion.ESTADO_NO_ASISTIO},
		)

		self.assertEqual(cancelled.status_code, 302)
		self.assertEqual(no_show.status_code, 302)
		future_session.refresh_from_db()
		past_session.refresh_from_db()
		self.assertEqual(future_session.estado, Sesion.ESTADO_CANCELADA)
		self.assertFalse(future_session.activo)
		self.assertEqual(past_session.estado, Sesion.ESTADO_NO_ASISTIO)
		self.assertTrue(past_session.activo)
		self.assertFalse(past_session.realizada)
		self.assertIsNone(past_session.realizada_en)


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
			estado=Sesion.ESTADO_COMPLETADA,
			realizada=True,
			realizada_en=timezone.now() - timedelta(hours=1),
		)
		Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() + timedelta(days=1),
			objetivo='Sesión programada',
		)
		Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() - timedelta(days=2),
			objetivo='Sesión no asistida',
			estado=Sesion.ESTADO_NO_ASISTIO,
		)
		Sesion.objects.create(
			paciente=self.patient,
			fecha=timezone.now() - timedelta(days=3),
			objetivo='Sesión cancelada',
			estado=Sesion.ESTADO_CANCELADA,
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

	def test_clinical_evaluation_validates_eva_range_on_server(self):
		url = reverse('register_clinical_evaluation', args=[self.patient.pk])
		invalid_values = [
			self.doctor_client.post(url, {'nivel_dolor': pain})
			for pain in ('-1', '11')
		]
		valid = self.doctor_client.post(url, {'nivel_dolor': '0'})

		self.assertTrue(all(response.status_code == 302 for response in invalid_values))
		self.assertEqual(valid.status_code, 302)
		self.assertEqual(
			list(EvaluacionClinica.objects.filter(paciente=self.patient).values_list('nivel_dolor', flat=True)),
			[0],
		)

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
		template = PlantillaRutina.objects.create(
			doctor=self.doctor,
			nombre='Rutina de estiramiento',
		)
		exercise = EjercicioPlantillaRutina.objects.create(
			plantilla=template,
			video_id='video-2',
			titulo='Estiramiento',
			orden=1,
		)
		url = reverse('assign_routine', args=[self.patient.pk])
		today = timezone.localdate()
		form_data = {
			'plantilla': str(template.pk),
			'fecha_inicio': today.isoformat(),
			'fecha_fin': (today + timedelta(days=7)).isoformat(),
			'dias_semana': [str(today.weekday())],
			f'ejercicio_{exercise.pk}_series': '3',
			f'ejercicio_{exercise.pk}_repeticiones': '10 por lado',
			f'ejercicio_{exercise.pk}_duracion': '',
			f'ejercicio_{exercise.pk}_notas': 'Detener si duele.',
		}

		response = self.doctor_client.post(url, form_data)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()['success'])
		assignment = RutinaAsignada.objects.get(paciente=self.patient)
		self.assertEqual(assignment.titulo, template.nombre)
		self.assertEqual(assignment.fecha_inicio, today)
		self.assertEqual(assignment.fecha_fin, today + timedelta(days=7))
		self.assertEqual(assignment.dias_semana, [today.weekday()])
		self.assertEqual(assignment.ocurrencias.count(), 2)
		assigned_exercise = assignment.ejercicios.get()
		self.assertEqual(assigned_exercise.series, 3)
		self.assertEqual(assigned_exercise.repeticiones, '10 por lado')
		self.assertEqual(assigned_exercise.notas_medico, 'Detener si duele.')

		other_doctor = Usuario.objects.create(
			email='different-progress-doctor@example.com',
			nombre='Otro fisioterapeuta',
			role=Usuario.ROLE_DOCTOR,
		)
		other_client = Client()
		session = other_client.session
		session['current_user'] = other_doctor.email
		session.save()
		unauthorized = other_client.post(url, form_data)

		self.assertEqual(unauthorized.status_code, 404)
		self.assertEqual(RutinaAsignada.objects.filter(paciente=self.patient).count(), 1)

	def test_template_edits_do_not_change_assigned_exercise_copies(self):
		template = PlantillaRutina.objects.create(doctor=self.doctor, nombre='Movilidad')
		exercise = EjercicioPlantillaRutina.objects.create(
			plantilla=template,
			video_id='video-movilidad',
			titulo='Movilidad de rodilla',
			orden=1,
		)
		today = timezone.localdate()
		response = self.doctor_client.post(
			reverse('assign_routine', args=[self.patient.pk]),
			{
				'plantilla': str(template.pk),
				'fecha_inicio': today.isoformat(),
				'fecha_fin': today.isoformat(),
				'dias_semana': [str(today.weekday())],
				f'ejercicio_{exercise.pk}_series': '4',
				f'ejercicio_{exercise.pk}_repeticiones': '8',
				f'ejercicio_{exercise.pk}_duracion': '',
				f'ejercicio_{exercise.pk}_notas': 'Rango cómodo.',
			},
		)

		self.assertEqual(response.status_code, 200)
		assignment = RutinaAsignada.objects.get(paciente=self.patient)
		exercise.titulo = 'Nombre actualizado'
		exercise.save(update_fields=['titulo'])
		template.nombre = 'Plantilla actualizada'
		template.save(update_fields=['nombre'])

		assignment.refresh_from_db()
		assigned_exercise = assignment.ejercicios.get()
		self.assertEqual(assignment.titulo, 'Movilidad')
		self.assertEqual(assigned_exercise.titulo, 'Movilidad de rodilla')
		self.assertEqual(assigned_exercise.series, 4)
		self.assertEqual(assigned_exercise.notas_medico, 'Rango cómodo.')

	def test_patient_feedback_is_validated_and_attached_to_its_occurrence(self):
		today = timezone.localdate()
		assignment = RutinaAsignada.objects.create(
			paciente=self.patient,
			video_id='video-feedback',
			titulo='Rutina de prueba',
			fecha_programada=today,
		)
		occurrence = OcurrenciaRutina.objects.create(asignacion=assignment, fecha=today)
		url = reverse('complete_routine_occurrence', args=[occurrence.pk])

		invalid = self.patient_client.post(url, {
			'nivel_dolor': '11',
			'dificultad': 'adecuada',
		})
		self.assertEqual(invalid.status_code, 400)
		self.assertEqual(invalid.json()['error'], 'El dolor debe estar entre 0 y 10.')

		response = self.patient_client.post(url, {
			'nivel_dolor': '0',
			'dificultad': 'facil',
			'comentario': 'Sin molestias.',
		})

		self.assertEqual(response.status_code, 200)
		occurrence.refresh_from_db()
		self.assertEqual(occurrence.nivel_dolor, 0)
		self.assertEqual(occurrence.dificultad, OcurrenciaRutina.DIFICULTAD_FACIL)
		self.assertEqual(occurrence.comentario, 'Sin molestias.')
		self.assertIsNotNone(occurrence.completada_en)
		doctor_progress = self.doctor_client.get(reverse('doctor_dashboard_data')).json()['patients']
		self.assertEqual(doctor_progress[0]['routineFeedback'][0]['pain'], 0)
		self.assertEqual(doctor_progress[0]['routineFeedback'][0]['comment'], 'Sin molestias.')

	def test_assigned_template_cannot_be_deleted_and_foreign_doctor_cannot_manage_it(self):
		template = PlantillaRutina.objects.create(doctor=self.doctor, nombre='Equilibrio')
		assignment = RutinaAsignada.objects.create(
			paciente=self.patient,
			video_id='video-equilibrio',
			titulo=template.nombre,
			fecha_programada=timezone.localdate(),
			plantilla=template,
		)
		self.assertIsNotNone(assignment.pk)

		delete_response = self.doctor_client.post(
			reverse('manage_routine_template', args=[template.pk]),
			{'action': 'delete'},
		)
		self.assertEqual(delete_response.status_code, 302)
		self.assertTrue(PlantillaRutina.objects.filter(pk=template.pk).exists())

		other_doctor = Usuario.objects.create(
			email='foreign-template-doctor@example.com',
			nombre='Otro médico',
			role=Usuario.ROLE_DOCTOR,
		)
		other_client = Client()
		session = other_client.session
		session['current_user'] = other_doctor.email
		session.save()
		foreign_response = other_client.post(
			reverse('manage_routine_template', args=[template.pk]),
			{'action': 'deactivate'},
		)
		self.assertEqual(foreign_response.status_code, 404)

	def test_doctor_can_create_an_ordered_template_from_the_video_catalog(self):
		videos = [
			{'video_id': 'video-first', 'title': 'Primer video'},
			{'video_id': 'video-second', 'title': 'Segundo video'},
		]
		with patch('princpal.views.load_videos', return_value=videos):
			response = self.doctor_client.post(
				reverse('save_routine_template'),
				{
					'nombre': 'Rutina combinada',
					'descripcion': 'Movilidad y equilibrio.',
					'video_ids': ['video-first', 'video-second'],
					'orden_0': '2',
					'orden_1': '1',
				},
			)

		self.assertEqual(response.status_code, 302)
		template = PlantillaRutina.objects.get(doctor=self.doctor, nombre='Rutina combinada')
		self.assertEqual(
			list(template.ejercicios.values_list('titulo', 'orden')),
			[('Segundo video', 1), ('Primer video', 2)],
		)

	def test_inactive_template_and_invalid_dose_cannot_be_assigned(self):
		template = PlantillaRutina.objects.create(
			doctor=self.doctor,
			nombre='Rutina temporal',
			activa=False,
		)
		exercise = EjercicioPlantillaRutina.objects.create(
			plantilla=template,
			video_id='video-temporal',
			titulo='Ejercicio temporal',
		)
		url = reverse('assign_routine', args=[self.patient.pk])
		today = timezone.localdate()
		base_data = {
			'plantilla': str(template.pk),
			'fecha_inicio': today.isoformat(),
			'fecha_fin': today.isoformat(),
			'dias_semana': [str(today.weekday())],
			f'ejercicio_{exercise.pk}_series': '1',
			f'ejercicio_{exercise.pk}_repeticiones': '10',
			f'ejercicio_{exercise.pk}_duracion': '',
		}

		inactive_response = self.doctor_client.post(url, base_data)
		self.assertEqual(inactive_response.status_code, 400)
		self.assertEqual(
			inactive_response.json()['error'],
			'La plantilla está desactivada y no se puede asignar.',
		)

		template.activa = True
		template.save(update_fields=['activa'])
		invalid_dose = self.doctor_client.post(url, {
			**base_data,
			'ejercicio_%s_series' % exercise.pk: '0',
			f'ejercicio_{exercise.pk}_repeticiones': '',
		})
		self.assertEqual(invalid_dose.status_code, 400)
		self.assertEqual(RutinaAsignada.objects.filter(paciente=self.patient).count(), 0)

	def test_date_range_and_weekdays_are_required_and_validated(self):
		template = PlantillaRutina.objects.create(doctor=self.doctor, nombre='Rutina de fechas')
		exercise = EjercicioPlantillaRutina.objects.create(
			plantilla=template,
			video_id='video-fechas',
			titulo='Ejercicio de fechas',
		)
		today = timezone.localdate()
		data = {
			'plantilla': str(template.pk),
			'fecha_inicio': today.isoformat(),
			'fecha_fin': (today - timedelta(days=1)).isoformat(),
			f'ejercicio_{exercise.pk}_series': '1',
			f'ejercicio_{exercise.pk}_repeticiones': '10',
			f'ejercicio_{exercise.pk}_duracion': '',
		}
		url = reverse('assign_routine', args=[self.patient.pk])

		invalid_range = self.doctor_client.post(url, data)
		self.assertEqual(invalid_range.status_code, 400)
		self.assertEqual(
			invalid_range.json()['error'],
			'La fecha de fin no puede ser anterior a la fecha de inicio.',
		)

		data['fecha_fin'] = today.isoformat()
		without_weekday = self.doctor_client.post(url, data)
		self.assertEqual(without_weekday.status_code, 400)
		self.assertEqual(
			without_weekday.json()['error'],
			'Selecciona al menos un día de la semana.',
		)
		self.assertFalse(RutinaAsignada.objects.filter(paciente=self.patient).exists())
