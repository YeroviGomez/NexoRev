import builtins
import base64
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode
import zlib
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from crear_cuenta.models import Usuario
from princpal.models import (
    EjercicioRutinaAsignada,
    EvaluacionClinica,
    ObjetivoTerapeutico,
    OcurrenciaRutina,
    Paciente,
    RutinaAsignada,
    Sesion,
)
from .forms import RecordatorioForm
from .exports import exportar_reporte_pdf, exportar_reporte_xlsx
from .models import (
    AlertaDolor,
    EnvioResumenSemanal,
    Recordatorio,
    RegistroRecordatorio,
)
from .services import (
    crear_alerta_dolor,
    enviar_correo,
    enviar_correo_alerta,
    enviar_resumen_semanal,
    evaluar_alerta_dolor,
    inicio_de_semana,
    resumen_semanal,
)


@override_settings(
    DEFAULT_FROM_EMAIL='pruebas@nexorev.local',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class EnviarCorreoTests(TestCase):
    def test_sends_plain_text_and_html_email(self):
        ok, error = enviar_correo(
            'paciente@example.com',
            'Asunto de prueba',
            'prueba',
            {'nombre': 'Ana'},
        )

        self.assertTrue(ok)
        self.assertEqual(error, '')
        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.subject, 'Asunto de prueba')
        self.assertEqual(mensaje.to, ['paciente@example.com'])
        self.assertEqual(mensaje.from_email, 'pruebas@nexorev.local')
        self.assertIn('Hola Ana', mensaje.body)
        self.assertEqual(len(mensaje.alternatives), 1)
        contenido_html, tipo_html = mensaje.alternatives[0]
        self.assertEqual(tipo_html, 'text/html')
        self.assertIn('Hola Ana', contenido_html)

    def test_returns_error_instead_of_raising_when_send_fails(self):
        with patch(
            'notificaciones.services.EmailMultiAlternatives.send',
            side_effect=OSError('SMTP no disponible'),
        ):
            ok, error = enviar_correo(
                'paciente@example.com',
                'Asunto de prueba',
                'prueba',
                {'nombre': 'Ana'},
            )

        self.assertFalse(ok)
        self.assertEqual(error, 'SMTP no disponible')


@override_settings(
    ALERTA_DOLOR_UMBRAL=7,
    ALERTA_DOLOR_SUBIDA=3,
    ALERTA_DOLOR_RACHA_UMBRAL=6,
    ALERTA_DOLOR_RACHA_CANTIDAD=3,
)
class EvaluarAlertaDolorTests(TestCase):
    def setUp(self):
        self.doctor = Usuario.objects.create(
            email='doctor-evaluacion-alerta@example.com',
            nombre='Doctor de prueba',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente = Paciente.objects.create(
            nombre='Paciente de prueba',
            email='paciente-evaluacion-alerta@example.com',
            doctor=self.doctor,
        )
        self.numero_ocurrencia = 0

    def crear_ocurrencia(self, nivel_dolor, completada_en=None, paciente=None, completada=True):
        self.numero_ocurrencia += 1
        hoy = timezone.localdate()
        if not completada:
            completada_en = None
        elif completada_en is None:
            completada_en = timezone.now()
        asignacion = RutinaAsignada.objects.create(
            paciente=paciente or self.paciente,
            video_id=f'video-alerta-{self.numero_ocurrencia}',
            titulo=f'Rutina de prueba {self.numero_ocurrencia}',
            fecha_programada=hoy,
            fecha_inicio=hoy,
            fecha_fin=hoy,
        )
        return OcurrenciaRutina.objects.create(
            asignacion=asignacion,
            fecha=hoy,
            nivel_dolor=nivel_dolor,
            completada_en=completada_en,
        )

    def test_umbral_se_aplica_sin_antecedentes(self):
        actual = self.crear_ocurrencia(7)

        self.assertEqual(evaluar_alerta_dolor(actual), AlertaDolor.REGLA_UMBRAL)
        self.assertFalse(AlertaDolor.objects.exists())

    def test_subida_compara_con_la_ocurrencia_anterior_con_dolor(self):
        ahora = timezone.now()
        self.crear_ocurrencia(3, completada_en=ahora - timedelta(minutes=1))
        actual = self.crear_ocurrencia(6, completada_en=ahora)

        self.assertEqual(evaluar_alerta_dolor(actual), AlertaDolor.REGLA_SUBIDA)

    def test_racha_se_activa_con_tres_ocurrencias_elevadas(self):
        ahora = timezone.now()
        self.crear_ocurrencia(6, completada_en=ahora - timedelta(minutes=2))
        self.crear_ocurrencia(7, completada_en=ahora - timedelta(minutes=1))
        actual = self.crear_ocurrencia(6, completada_en=ahora)

        self.assertEqual(evaluar_alerta_dolor(actual), AlertaDolor.REGLA_RACHA)

    def test_prioriza_umbral_sobre_subida_y_racha(self):
        ahora = timezone.now()
        self.crear_ocurrencia(7, completada_en=ahora - timedelta(minutes=2))
        self.crear_ocurrencia(6, completada_en=ahora - timedelta(minutes=1))
        actual = self.crear_ocurrencia(9, completada_en=ahora)

        self.assertEqual(evaluar_alerta_dolor(actual), AlertaDolor.REGLA_UMBRAL)

    def test_prioriza_subida_sobre_racha_si_no_aplica_el_umbral(self):
        ahora = timezone.now()
        self.crear_ocurrencia(6, completada_en=ahora - timedelta(minutes=2))
        self.crear_ocurrencia(6, completada_en=ahora - timedelta(minutes=1))
        actual = self.crear_ocurrencia(9, completada_en=ahora)

        with self.settings(ALERTA_DOLOR_UMBRAL=10):
            self.assertEqual(evaluar_alerta_dolor(actual), AlertaDolor.REGLA_SUBIDA)

    def test_devuelve_none_si_falta_dolor_actual_o_no_hay_antecedente(self):
        sin_dolor = self.crear_ocurrencia(None)
        sin_antecedente = self.crear_ocurrencia(5)
        sin_completar = self.crear_ocurrencia(8, completada=False)

        self.assertIsNone(evaluar_alerta_dolor(sin_dolor))
        self.assertIsNone(evaluar_alerta_dolor(sin_antecedente))
        self.assertIsNone(evaluar_alerta_dolor(sin_completar))

    def test_un_dolor_anterior_sin_registro_no_cuenta_en_la_racha(self):
        ahora = timezone.now()
        self.crear_ocurrencia(7, completada_en=ahora - timedelta(minutes=2))
        self.crear_ocurrencia(None, completada_en=ahora - timedelta(minutes=1))
        actual = self.crear_ocurrencia(6, completada_en=ahora)

        self.assertIsNone(evaluar_alerta_dolor(actual))

    def test_crea_alerta_sin_medico_y_no_duplica_si_se_repite(self):
        paciente_sin_medico = Paciente.objects.create(
            nombre='Paciente sin médico',
            email='paciente-sin-medico-alerta@example.com',
        )
        actual = self.crear_ocurrencia(8, paciente=paciente_sin_medico)

        primera_alerta = crear_alerta_dolor(actual)
        segunda_alerta = crear_alerta_dolor(actual)

        self.assertIsNotNone(primera_alerta)
        self.assertEqual(primera_alerta, segunda_alerta)
        self.assertIsNone(primera_alerta.doctor)
        self.assertEqual(AlertaDolor.objects.filter(ocurrencia=actual).count(), 1)


class AlertaDolorTests(TestCase):
    def setUp(self):
        self.doctor = Usuario.objects.create(
            email='doctor-alerta@example.com',
            nombre='Doctora de prueba',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente = Paciente.objects.create(
            nombre='Paciente de prueba',
            email='paciente-alerta@example.com',
            doctor=self.doctor,
        )
        hoy = timezone.localdate()
        rutina = RutinaAsignada.objects.create(
            paciente=self.paciente,
            video_id='video-alerta',
            titulo='Rutina de prueba',
            fecha_programada=hoy,
            fecha_inicio=hoy,
            fecha_fin=hoy,
        )
        self.ocurrencia = OcurrenciaRutina.objects.create(
            asignacion=rutina,
            fecha=hoy,
        )

    def crear_alerta(self):
        return AlertaDolor.objects.create(
            paciente=self.paciente,
            ocurrencia=self.ocurrencia,
            nivel_dolor=8,
            regla=AlertaDolor.REGLA_UMBRAL,
        )

    def test_crea_alerta_y_copia_el_medico_del_paciente(self):
        alerta = self.crear_alerta()

        self.assertEqual(alerta.doctor, self.doctor)
        self.assertEqual(alerta.estado, AlertaDolor.ESTADO_NUEVA)
        self.assertEqual(alerta.correo_intentos, 0)

    def test_no_permite_mas_de_una_alerta_por_ocurrencia(self):
        self.crear_alerta()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.crear_alerta()


@override_settings(
    DEFAULT_FROM_EMAIL='pruebas@nexorev.local',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class EnviarCorreoAlertaTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.doctor = Usuario.objects.create(
            email='doctor-correo-alerta@example.com',
            nombre='Médico de prueba',
            role=Usuario.ROLE_DOCTOR,
            zona_horaria='America/El_Salvador',
        )
        self.paciente = Paciente.objects.create(
            nombre='Paciente para correo',
            email='paciente-correo-alerta@example.com',
            doctor=self.doctor,
        )
        self.numero_alerta = 0

    def crear_alerta(self, paciente=None):
        self.numero_alerta += 1
        paciente = paciente or self.paciente
        hoy = timezone.localdate()
        asignacion = RutinaAsignada.objects.create(
            paciente=paciente,
            video_id=f'video-correo-alerta-{self.numero_alerta}',
            titulo='Rutina de prueba',
            fecha_programada=hoy,
            fecha_inicio=hoy,
            fecha_fin=hoy,
        )
        ocurrencia = OcurrenciaRutina.objects.create(
            asignacion=asignacion,
            fecha=hoy,
            nivel_dolor=8,
            completada_en=timezone.now(),
            comentario='Comentario libre confidencial.',
        )
        return AlertaDolor.objects.create(
            paciente=paciente,
            ocurrencia=ocurrencia,
            nivel_dolor=8,
            regla=AlertaDolor.REGLA_UMBRAL,
        )

    def test_sends_alert_email_without_patient_comment(self):
        alerta = self.crear_alerta()

        enviar_correo_alerta(alerta)

        alerta.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, [self.doctor.email])
        self.assertEqual(mensaje.subject, 'Alerta de dolor - Nexo ReV')
        self.assertIn('Paciente para correo', mensaje.body)
        self.assertIn('8/10', mensaje.body)
        self.assertIn('Umbral de dolor', mensaje.body)
        self.assertIn('/principal/#dashboard', mensaje.body)
        fecha_local = timezone.localtime(
            alerta.creada_en,
            ZoneInfo(self.doctor.zona_horaria),
        ).strftime('%d/%m/%Y %H:%M')
        self.assertIn(fecha_local, mensaje.body)
        self.assertNotIn('Comentario libre confidencial.', mensaje.body)
        contenido_html, tipo_html = mensaje.alternatives[0]
        self.assertEqual(tipo_html, 'text/html')
        self.assertIn(fecha_local, contenido_html)
        self.assertIn('Comentario libre confidencial.', alerta.ocurrencia.comentario)
        self.assertNotIn('Comentario libre confidencial.', contenido_html)
        self.assertEqual(alerta.correo_intentos, 1)
        self.assertIsNotNone(alerta.correo_enviado_en)
        self.assertEqual(alerta.correo_error, '')

    def test_patient_without_doctor_records_error_without_sending(self):
        paciente = Paciente.objects.create(
            nombre='Paciente sin médico',
            email='paciente-sin-medico-correo@example.com',
        )
        alerta = self.crear_alerta(paciente=paciente)

        with patch('notificaciones.services.enviar_correo') as enviar:
            enviar_correo_alerta(alerta)

        enviar.assert_not_called()
        alerta.refresh_from_db()
        self.assertIn('no tiene un médico asignado', alerta.correo_error)
        self.assertEqual(alerta.correo_intentos, 0)
        self.assertEqual(mail.outbox, [])

    def test_inactive_doctor_records_error_without_sending(self):
        self.doctor.is_active = False
        self.doctor.save(update_fields=['is_active'])
        alerta = self.crear_alerta()

        with patch('notificaciones.services.enviar_correo') as enviar:
            enviar_correo_alerta(alerta)

        enviar.assert_not_called()
        alerta.refresh_from_db()
        self.assertIn('médico asignado está inactivo', alerta.correo_error)
        self.assertEqual(alerta.correo_intentos, 0)

    def test_command_retries_failed_alerts_and_is_idempotent(self):
        alerta = self.crear_alerta()
        alerta.correo_intentos = 1
        alerta.correo_error = 'Fallo anterior'
        alerta.save(update_fields=['correo_intentos', 'correo_error'])

        call_command('reintentar_alertas_pendientes')
        call_command('reintentar_alertas_pendientes')

        alerta.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(alerta.correo_intentos, 2)
        self.assertIsNotNone(alerta.correo_enviado_en)
        self.assertEqual(alerta.correo_error, '')

    def test_command_skips_alerts_at_attempt_limit(self):
        alerta = self.crear_alerta()
        alerta.correo_intentos = 5
        alerta.save(update_fields=['correo_intentos'])

        call_command('reintentar_alertas_pendientes')

        alerta.refresh_from_db()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(alerta.correo_intentos, 5)
        self.assertIsNone(alerta.correo_enviado_en)

    def test_command_dry_run_does_not_send_or_update_alerts(self):
        alerta = self.crear_alerta()
        output = StringIO()

        call_command(
            'reintentar_alertas_pendientes',
            dry_run=True,
            ahora='2099-01-01 00:00',
            stdout=output,
        )

        alerta.refresh_from_db()
        self.assertIn('1 alerta(s)', output.getvalue())
        self.assertEqual(mail.outbox, [])
        self.assertEqual(alerta.correo_intentos, 0)
        self.assertIsNone(alerta.correo_enviado_en)

    def test_command_uses_ahora_as_creation_cutoff(self):
        alerta = self.crear_alerta()
        output = StringIO()

        call_command(
            'reintentar_alertas_pendientes',
            dry_run=True,
            ahora='2000-01-01 00:00',
            stdout=output,
        )

        self.assertIn('0 alerta(s)', output.getvalue())
        self.assertEqual(mail.outbox, [])
        self.assertEqual(alerta.correo_intentos, 0)


class AlertasDolorApiTests(TestCase):
    def setUp(self):
        self.doctor = Usuario.objects.create(
            email='doctor-api-alertas@example.com',
            nombre='Médico API',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente = Paciente.objects.create(
            nombre='Paciente API',
            email='paciente-api-alertas@example.com',
            doctor=self.doctor,
        )
        self.otro_paciente = Paciente.objects.create(
            nombre='Segundo paciente API',
            email='segundo-paciente-api-alertas@example.com',
            doctor=self.doctor,
        )
        self.otro_doctor = Usuario.objects.create(
            email='otro-doctor-api-alertas@example.com',
            nombre='Otro médico API',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente_ajeno = Paciente.objects.create(
            nombre='Paciente ajeno API',
            email='paciente-ajeno-api-alertas@example.com',
            doctor=self.otro_doctor,
        )
        self.client_doctor = self.crear_cliente(self.doctor)
        self.client_paciente = self.crear_cliente(
            Usuario.objects.create(
                email='usuario-paciente-api-alertas@example.com',
                nombre='Usuario paciente API',
                role=Usuario.ROLE_PACIENTE,
            )
        )
        self.numero_alerta = 0
        self.list_url = reverse('notif_alertas')

    @staticmethod
    def crear_cliente(usuario):
        client = Client()
        session = client.session
        session['current_user'] = usuario.email
        session['current_user_role'] = usuario.role
        session.save()
        return client

    def crear_alerta(self, paciente=None, estado=AlertaDolor.ESTADO_NUEVA):
        self.numero_alerta += 1
        paciente = paciente or self.paciente
        hoy = timezone.localdate()
        asignacion = RutinaAsignada.objects.create(
            paciente=paciente,
            video_id=f'video-api-alerta-{self.numero_alerta}',
            titulo=f'Rutina API {self.numero_alerta}',
            fecha_programada=hoy,
            fecha_inicio=hoy,
            fecha_fin=hoy,
        )
        ocurrencia = OcurrenciaRutina.objects.create(
            asignacion=asignacion,
            fecha=hoy,
            nivel_dolor=8,
            completada_en=timezone.now(),
        )
        return AlertaDolor.objects.create(
            paciente=paciente,
            ocurrencia=ocurrencia,
            nivel_dolor=8,
            regla=AlertaDolor.REGLA_UMBRAL,
            estado=estado,
        )

    def test_list_filters_by_state_patient_and_local_dates(self):
        antigua = self.crear_alerta()
        antigua.creada_en = timezone.now() - timedelta(days=3)
        AlertaDolor.objects.filter(pk=antigua.pk).update(creada_en=antigua.creada_en)
        vista = self.crear_alerta(estado=AlertaDolor.ESTADO_VISTA)
        vista.creada_en = timezone.now() - timedelta(days=2)
        AlertaDolor.objects.filter(pk=vista.pk).update(creada_en=vista.creada_en)
        self.crear_alerta(paciente=self.otro_paciente)

        response = self.client_doctor.get(
            self.list_url,
            {
                'estado': AlertaDolor.ESTADO_VISTA,
                'paciente': str(self.paciente.pk),
                'fecha_desde': (timezone.localdate() - timedelta(days=2)).isoformat(),
                'fecha_hasta': (timezone.localdate() - timedelta(days=2)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['nuevas_count'], 2)
        self.assertEqual(payload['total'], 1)
        self.assertEqual([alerta['id'] for alerta in payload['alertas']], [vista.pk])
        self.assertEqual(payload['alertas'][0]['paciente_nombre'], self.paciente.nombre)
        self.assertEqual(payload['alertas'][0]['regla_display'], 'Umbral de dolor')

    def test_list_paginates_and_clamps_out_of_range_page_to_last_page(self):
        alertas = [self.crear_alerta() for _ in range(3)]

        response = self.client_doctor.get(
            self.list_url,
            {'page': '999', 'page_size': '1'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['total'], 3)
        self.assertEqual(payload['pages'], 3)
        self.assertEqual(payload['page'], 3)
        self.assertEqual(payload['page_size'], 1)
        self.assertEqual(payload['alertas'][0]['id'], alertas[0].pk)

    def test_numeric_page_below_range_also_resolves_to_last_page(self):
        self.crear_alerta()
        self.crear_alerta()

        response = self.client_doctor.get(
            self.list_url,
            {'page': '0', 'page_size': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['page'], 2)

    def test_list_caps_page_size_at_one_hundred(self):
        response = self.client_doctor.get(self.list_url, {'page_size': '101'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['page_size'], 100)

    def test_invalid_filters_and_pagination_return_json_400(self):
        invalid_queries = [
            {'estado': 'desactivada'},
            {'fecha_desde': 'ayer'},
            {'fecha_hasta': '2026-02-30'},
            {'page': 'uno'},
            {'page_size': 'muchos'},
            {'fecha_desde': '2026-12-02', 'fecha_hasta': '2026-12-01'},
        ]

        for params in invalid_queries:
            with self.subTest(params=params):
                response = self.client_doctor.get(self.list_url, params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['success'], False)
                self.assertIn('error', response.json())

    def test_patient_filter_rejects_foreign_or_missing_patient(self):
        for patient_id in (self.paciente_ajeno.pk, 999999):
            with self.subTest(patient_id=patient_id):
                response = self.client_doctor.get(self.list_url, {'paciente': str(patient_id)})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()['success'], False)

    def test_missing_session_is_401_and_patient_role_is_403_on_each_endpoint(self):
        alert = self.crear_alerta()
        vista_url = reverse('notif_alerta_vista', args=[alert.pk])
        atendida_url = reverse('notif_alerta_atendida', args=[alert.pk])

        missing_session = Client().get(self.list_url)
        self.assertEqual(missing_session.status_code, 401)
        self.assertEqual(missing_session.json()['success'], False)

        for response in (
            self.client_paciente.get(self.list_url),
            self.client_paciente.post(vista_url),
            self.client_paciente.post(atendida_url, {'nota': 'No permitido'}),
        ):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()['success'], False)

    def test_inactive_doctor_is_forbidden(self):
        self.doctor.is_active = False
        self.doctor.save(update_fields=['is_active'])

        response = self.client_doctor.get(self.list_url)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['success'], False)

    def test_alert_owned_by_another_doctor_returns_404_for_transitions(self):
        alert = self.crear_alerta(paciente=self.paciente_ajeno)

        for url in (
            reverse('notif_alerta_vista', args=[alert.pk]),
            reverse('notif_alerta_atendida', args=[alert.pk]),
        ):
            response = self.client_doctor.post(url, {'nota': ''})
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()['success'], False)

    def test_marking_new_alert_as_seen_is_idempotent(self):
        alert = self.crear_alerta()
        url = reverse('notif_alerta_vista', args=[alert.pk])

        first_response = self.client_doctor.post(url)
        alert.refresh_from_db()
        first_seen_at = alert.vista_en
        second_response = self.client_doctor.post(url)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.json()['success'])
        self.assertEqual(alert.estado, AlertaDolor.ESTADO_VISTA)
        self.assertEqual(alert.vista_en, first_seen_at)

    def test_attending_strips_note_and_records_actor_and_time(self):
        alert = self.crear_alerta(estado=AlertaDolor.ESTADO_VISTA)
        url = reverse('notif_alerta_atendida', args=[alert.pk])

        response = self.client_doctor.post(url, {'nota': '  Se contactó al paciente.  '})

        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.estado, AlertaDolor.ESTADO_ATENDIDA)
        self.assertEqual(alert.nota_atencion, 'Se contactó al paciente.')
        self.assertEqual(alert.atendida_por, self.doctor)
        self.assertIsNotNone(alert.atendida_en)

    def test_attended_alert_never_transitions_back_or_overwrites_attention_data(self):
        alert = self.crear_alerta(estado=AlertaDolor.ESTADO_ATENDIDA)
        alert.atendida_por = self.otro_doctor
        alert.atendida_en = timezone.now() - timedelta(hours=1)
        alert.nota_atencion = 'Nota original'
        alert.save(update_fields=['atendida_por', 'atendida_en', 'nota_atencion'])
        attended_at = alert.atendida_en
        vista_url = reverse('notif_alerta_vista', args=[alert.pk])
        attended_url = reverse('notif_alerta_atendida', args=[alert.pk])

        vista_response = self.client_doctor.post(vista_url)
        attended_response = self.client_doctor.post(attended_url, {'nota': 'Nota nueva'})

        alert.refresh_from_db()
        self.assertEqual(vista_response.status_code, 200)
        self.assertEqual(attended_response.status_code, 200)
        self.assertEqual(alert.estado, AlertaDolor.ESTADO_ATENDIDA)
        self.assertEqual(alert.atendida_por, self.otro_doctor)
        self.assertEqual(alert.atendida_en, attended_at)
        self.assertEqual(alert.nota_atencion, 'Nota original')

    def test_attending_rejects_notes_over_500_characters(self):
        alert = self.crear_alerta()

        response = self.client_doctor.post(
            reverse('notif_alerta_atendida', args=[alert.pk]),
            {'nota': 'x' * 501},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['success'], False)
        alert.refresh_from_db()
        self.assertEqual(alert.estado, AlertaDolor.ESTADO_NUEVA)
        self.assertEqual(alert.nota_atencion, '')

    def test_attending_rejects_non_text_note_and_accepts_json_note(self):
        alert = self.crear_alerta()
        url = reverse('notif_alerta_atendida', args=[alert.pk])

        invalid = self.client_doctor.post(
            url,
            data='{"nota": 4}',
            content_type='application/json',
        )
        valid = self.client_doctor.post(
            url,
            data='{"nota": "  Contactado  "}',
            content_type='application/json',
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(valid.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.nota_atencion, 'Contactado')


class RecordatorioFormTests(TestCase):
    def setUp(self):
        self.doctor = Usuario.objects.create(
            email='doctor-recordatorios@example.com',
            nombre='Médico recordatorios',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente = Paciente.objects.create(
            nombre='Paciente recordatorios',
            email='paciente-recordatorios@example.com',
            doctor=self.doctor,
        )

    def form_data(self, hora='08:30', dias=None, activo=True):
        return {
            'paciente': str(self.paciente.pk),
            'hora': hora,
            'dias_semana': ['0', '2'] if dias is None else dias,
            'activo': 'on' if activo else '',
        }

    def crear_recordatorio(self, hora, activo=True):
        return Recordatorio.objects.create(
            paciente=self.paciente,
            hora=hora,
            dias_semana=[0],
            activo=activo,
        )

    def test_valid_form_saves_days_as_unique_integers(self):
        form = RecordatorioForm(data=self.form_data())

        self.assertTrue(form.is_valid(), form.errors)
        recordatorio = form.save()
        self.assertEqual(recordatorio.dias_semana, [0, 2])
        self.assertTrue(recordatorio.activo)

    def test_rejects_invalid_time(self):
        form = RecordatorioForm(data=self.form_data(hora='25:61'))

        self.assertFalse(form.is_valid())
        self.assertIn('hora', form.errors)

    def test_requires_at_least_one_day_and_rejects_duplicate_days(self):
        empty_days = RecordatorioForm(data=self.form_data(dias=[]))
        duplicate_days = RecordatorioForm(data=self.form_data(dias=['1', '1']))

        self.assertFalse(empty_days.is_valid())
        self.assertIn('dias_semana', empty_days.errors)
        self.assertFalse(duplicate_days.is_valid())
        self.assertIn('dias_semana', duplicate_days.errors)

    def test_rejects_weekday_outside_zero_to_six(self):
        form = RecordatorioForm(data=self.form_data(dias=['7']))

        self.assertFalse(form.is_valid())
        self.assertIn('dias_semana', form.errors)

    def test_rejects_duplicate_active_time(self):
        self.crear_recordatorio('08:30:00')
        form = RecordatorioForm(data=self.form_data(hora='08:30'))

        self.assertFalse(form.is_valid())
        self.assertIn('hora', form.errors)

    def test_rejects_a_fourth_active_reminder(self):
        self.crear_recordatorio('07:00:00')
        self.crear_recordatorio('08:00:00')
        self.crear_recordatorio('09:00:00')
        form = RecordatorioForm(data=self.form_data(hora='10:00'))

        self.assertFalse(form.is_valid())
        self.assertIn('paciente', form.errors)

    def test_inactive_reminders_do_not_count_or_block_their_time(self):
        for _ in range(3):
            self.crear_recordatorio('08:30:00', activo=False)
        form = RecordatorioForm(data=self.form_data(hora='08:30'))

        self.assertTrue(form.is_valid(), form.errors)

    def test_database_unique_constraint_only_applies_to_active_times(self):
        self.crear_recordatorio('08:30:00')
        inactive = Recordatorio.objects.create(
            paciente=self.paciente,
            hora='08:30:00',
            dias_semana=[0],
            activo=False,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.crear_recordatorio('08:30:00')

        self.assertFalse(inactive.activo)


class RegistroRecordatorioTests(TestCase):
    def setUp(self):
        doctor = Usuario.objects.create(
            email='doctor-registro-recordatorio@example.com',
            nombre='Médico del registro',
            role=Usuario.ROLE_DOCTOR,
        )
        paciente = Paciente.objects.create(
            nombre='Paciente del registro',
            email='paciente-registro-recordatorio@example.com',
            doctor=doctor,
        )
        self.recordatorio = Recordatorio.objects.create(
            paciente=paciente,
            hora='09:00:00',
            dias_semana=[0],
        )

    def test_only_one_record_per_reminder_and_local_date(self):
        RegistroRecordatorio.objects.create(
            recordatorio=self.recordatorio,
            fecha=timezone.localdate(),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RegistroRecordatorio.objects.create(
                    recordatorio=self.recordatorio,
                    fecha=timezone.localdate(),
                )


class RecordatoriosApiTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create(
            email='paciente-api-recordatorios@example.com',
            nombre='Paciente API recordatorios',
            role=Usuario.ROLE_PACIENTE,
            zona_horaria='America/El_Salvador',
            recordatorios_activos=False,
        )
        self.paciente = Paciente.objects.create(
            usuario=self.usuario,
            nombre=self.usuario.nombre,
            email=self.usuario.email,
        )
        self.otro_usuario = Usuario.objects.create(
            email='otro-paciente-api-recordatorios@example.com',
            nombre='Otro paciente API',
            role=Usuario.ROLE_PACIENTE,
        )
        self.otro_paciente = Paciente.objects.create(
            usuario=self.otro_usuario,
            nombre=self.otro_usuario.nombre,
            email=self.otro_usuario.email,
        )
        self.doctor = Usuario.objects.create(
            email='doctor-api-recordatorios-crud@example.com',
            nombre='Médico API recordatorios',
            role=Usuario.ROLE_DOCTOR,
        )
        self.usuario_sin_perfil = Usuario.objects.create(
            email='paciente-sin-perfil-api@example.com',
            nombre='Paciente sin perfil',
            role=Usuario.ROLE_PACIENTE,
        )
        self.client_paciente = self.crear_cliente(self.usuario)
        self.client_otro_paciente = self.crear_cliente(self.otro_usuario)
        self.client_doctor = self.crear_cliente(self.doctor)
        self.client_sin_perfil = self.crear_cliente(self.usuario_sin_perfil)
        self.url = reverse('notif_recordatorios')

    @staticmethod
    def crear_cliente(usuario):
        client = Client()
        session = client.session
        session['current_user'] = usuario.email
        session['current_user_role'] = usuario.role
        session.save()
        return client

    @staticmethod
    def enviar_json(client, method, url, data=None):
        body = json.dumps(data or {})
        return getattr(client, method)(
            url,
            data=body,
            content_type='application/json',
        )

    def crear_recordatorio(self, paciente=None, hora='08:30:00', activo=True):
        return Recordatorio.objects.create(
            paciente=paciente or self.paciente,
            hora=hora,
            dias_semana=[0, 2],
            activo=activo,
        )

    def test_list_includes_timezone_global_preference_and_owned_records(self):
        recordatorio = self.crear_recordatorio()

        response = self.client_paciente.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['zona_horaria'], 'America/El_Salvador')
        self.assertFalse(payload['recordatorios_activos'])
        self.assertEqual([item['id'] for item in payload['recordatorios']], [recordatorio.pk])
        self.assertEqual(payload['recordatorios'][0]['dias_semana'], [0, 2])

    def test_create_edit_toggle_and_delete_record(self):
        created = self.enviar_json(
            self.client_paciente,
            'post',
            self.url,
            {'hora': '09:15', 'dias_semana': [1, 3]},
        )
        self.assertEqual(created.status_code, 201)
        recordatorio_id = created.json()['recordatorio']['id']
        self.assertEqual(created.json()['recordatorio']['hora'], '09:15')

        item_url = reverse('notif_recordatorio', args=[recordatorio_id])
        edited = self.enviar_json(
            self.client_paciente,
            'patch',
            item_url,
            {'hora': '10:30', 'dias_semana': [4, 5]},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()['recordatorio']['dias_semana'], [4, 5])
        self.assertEqual(edited.json()['recordatorio']['hora'], '10:30')

        active_url = reverse('notif_recordatorio_activo', args=[recordatorio_id])
        deactivated = self.enviar_json(
            self.client_paciente,
            'patch',
            active_url,
            {'activo': False},
        )
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()['recordatorio']['activo'])

        activated = self.enviar_json(
            self.client_paciente,
            'patch',
            active_url,
            {'activo': True},
        )
        self.assertEqual(activated.status_code, 200)
        self.assertTrue(activated.json()['recordatorio']['activo'])

        deleted = self.client_paciente.delete(item_url)
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()['success'])
        self.assertFalse(Recordatorio.objects.filter(pk=recordatorio_id).exists())

    def test_create_returns_400_for_form_validation_errors(self):
        invalid_payloads = [
            {'hora': '25:30', 'dias_semana': [0]},
            {'hora': '08:30', 'dias_semana': []},
            {'hora': '08:30', 'dias_semana': [1, 1]},
            {'hora': '08:30', 'dias_semana': [7]},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.enviar_json(
                    self.client_paciente,
                    'post',
                    self.url,
                    payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['success'])
                self.assertIn('error', response.json())

    def test_create_rejects_duplicate_active_time_and_fourth_active_reminder(self):
        self.crear_recordatorio(hora='08:30:00')
        duplicate = self.enviar_json(
            self.client_paciente,
            'post',
            self.url,
            {'hora': '08:30', 'dias_semana': [1]},
        )
        self.assertEqual(duplicate.status_code, 400)

        Recordatorio.objects.all().delete()
        for hora in ('07:00:00', '08:00:00', '09:00:00'):
            self.crear_recordatorio(hora=hora)
        fourth = self.enviar_json(
            self.client_paciente,
            'post',
            self.url,
            {'hora': '10:00', 'dias_semana': [1]},
        )
        self.assertEqual(fourth.status_code, 400)

    def test_toggle_requires_boolean_and_respects_active_limits(self):
        self.crear_recordatorio(hora='07:00:00')
        self.crear_recordatorio(hora='08:00:00')
        self.crear_recordatorio(hora='09:00:00')
        inactive = self.crear_recordatorio(hora='10:00:00', activo=False)
        url = reverse('notif_recordatorio_activo', args=[inactive.pk])

        invalid_type = self.enviar_json(
            self.client_paciente,
            'patch',
            url,
            {'activo': 1},
        )
        exceeds_limit = self.enviar_json(
            self.client_paciente,
            'patch',
            url,
            {'activo': True},
        )

        self.assertEqual(invalid_type.status_code, 400)
        self.assertEqual(exceeds_limit.status_code, 400)
        inactive.refresh_from_db()
        self.assertFalse(inactive.activo)

    def test_other_patient_record_returns_404_for_edit_toggle_and_delete(self):
        recordatorio = self.crear_recordatorio(paciente=self.otro_paciente)
        item_url = reverse('notif_recordatorio', args=[recordatorio.pk])
        active_url = reverse('notif_recordatorio_activo', args=[recordatorio.pk])

        responses = [
            self.enviar_json(
                self.client_paciente,
                'patch',
                item_url,
                {'hora': '10:00'},
            ),
            self.enviar_json(
                self.client_paciente,
                'patch',
                active_url,
                {'activo': False},
            ),
            self.client_paciente.delete(item_url),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertFalse(response.json()['success'])

    def test_doctor_is_forbidden_and_missing_session_is_unauthorized(self):
        recordatorio = self.crear_recordatorio()
        item_url = reverse('notif_recordatorio', args=[recordatorio.pk])
        active_url = reverse('notif_recordatorio_activo', args=[recordatorio.pk])

        doctor_responses = [
            self.client_doctor.get(self.url),
            self.enviar_json(
                self.client_doctor,
                'post',
                self.url,
                {'hora': '10:00', 'dias_semana': [1]},
            ),
            self.enviar_json(
                self.client_doctor,
                'patch',
                item_url,
                {'hora': '10:00'},
            ),
            self.enviar_json(
                self.client_doctor,
                'patch',
                active_url,
                {'activo': False},
            ),
            self.client_doctor.delete(item_url),
        ]
        for response in doctor_responses:
            self.assertEqual(response.status_code, 403)
            self.assertFalse(response.json()['success'])

        anonymous = Client()
        anonymous_responses = [
            anonymous.get(self.url),
            self.enviar_json(anonymous, 'post', self.url, {}),
            self.enviar_json(anonymous, 'patch', item_url, {'hora': '10:00'}),
            self.enviar_json(anonymous, 'patch', active_url, {'activo': False}),
            anonymous.delete(item_url),
        ]
        for response in anonymous_responses:
            self.assertEqual(response.status_code, 401)
            self.assertFalse(response.json()['success'])

    def test_patient_without_profile_gets_404(self):
        responses = [
            self.client_sin_perfil.get(self.url),
            self.enviar_json(
                self.client_sin_perfil,
                'post',
                self.url,
                {'hora': '10:00', 'dias_semana': [1]},
            ),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertFalse(response.json()['success'])


@override_settings(
    DEFAULT_FROM_EMAIL='pruebas@nexorev.local',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class EnviarRecordatoriosCommandTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.usuario = Usuario.objects.create(
            email='paciente-comando-recordatorio@example.com',
            nombre='Paciente para recordatorio',
            role=Usuario.ROLE_PACIENTE,
            zona_horaria='America/El_Salvador',
            recordatorios_activos=True,
        )
        self.paciente = Paciente.objects.create(
            usuario=self.usuario,
            nombre=self.usuario.nombre,
            email=self.usuario.email,
        )
        self.numero = 0

    def crear_recordatorio(self, hora='10:00:00', dias=None, paciente=None):
        paciente = paciente or self.paciente
        fecha = timezone.localdate()
        return Recordatorio.objects.create(
            paciente=paciente,
            hora=hora,
            dias_semana=dias if dias is not None else [fecha.weekday()],
        )

    def crear_ocurrencia(self, fecha, paciente=None, completada=False):
        self.numero += 1
        paciente = paciente or self.paciente
        asignacion = RutinaAsignada.objects.create(
            paciente=paciente,
            video_id=f'video-comando-recordatorio-{self.numero}',
            titulo=f'Rutina pendiente {self.numero}',
            fecha_programada=fecha,
            fecha_inicio=fecha,
            fecha_fin=fecha,
        )
        ocurrencia = OcurrenciaRutina.objects.create(
            asignacion=asignacion,
            fecha=fecha,
            completada_en=timezone.now() if completada else None,
            nivel_dolor=8,
            comentario='Comentario clínico que no debe incluirse.',
        )
        EjercicioRutinaAsignada.objects.create(
            asignacion=asignacion,
            video_id=f'ejercicio-comando-recordatorio-{self.numero}',
            titulo='Movilidad pendiente',
            orden=1,
            series=2,
            repeticiones='8',
        )
        return ocurrencia

    def ejecutar(self, utc_text, dry_run=False):
        call_command(
            'enviar_recordatorios',
            ahora=utc_text,
            dry_run=dry_run,
        )

    def test_sends_in_patient_timezone_and_email_has_only_pending_exercises(self):
        self.usuario.zona_horaria = 'Asia/Tokyo'
        self.usuario.save(update_fields=['zona_horaria'])
        fecha_local = datetime(2026, 2, 2).date()
        self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)

        self.ejecutar('2026-02-02 01:05')

        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, [self.usuario.email])
        self.assertIn('Movilidad pendiente', mensaje.body)
        self.assertIn('/principal/', mensaje.body)
        self.assertNotIn('Comentario clínico', mensaje.body)
        self.assertNotIn('8/10', mensaje.body)
        registro = RegistroRecordatorio.objects.get()
        self.assertEqual(registro.fecha, fecha_local)
        self.assertIsNotNone(registro.enviado_en)

    def test_midnight_grace_period_uses_scheduled_local_date(self):
        self.usuario.zona_horaria = 'America/El_Salvador'
        self.usuario.save(update_fields=['zona_horaria'])
        fecha_recordatorio = datetime(2026, 2, 2).date()
        self.crear_recordatorio(hora='23:55:00', dias=[0])
        self.crear_ocurrencia(fecha_recordatorio)

        self.ejecutar('2026-02-03 06:03')

        self.assertEqual(len(mail.outbox), 1)
        registro = RegistroRecordatorio.objects.get()
        self.assertEqual(registro.fecha, fecha_recordatorio)

    def test_spring_forward_nonexistent_hour_sends_at_first_valid_instant_once(self):
        self.usuario.zona_horaria = 'Europe/Madrid'
        self.usuario.save(update_fields=['zona_horaria'])
        fecha_local = datetime(2026, 3, 29).date()
        self.crear_recordatorio(hora='02:30:00', dias=[6])
        self.crear_ocurrencia(fecha_local)

        self.ejecutar('2026-03-29 01:05')
        self.ejecutar('2026-03-29 01:05')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(RegistroRecordatorio.objects.get().fecha, fecha_local)

    def test_fall_back_ambiguous_hour_sends_once_and_never_resends_after_first_fold(self):
        self.usuario.zona_horaria = 'Europe/Madrid'
        self.usuario.save(update_fields=['zona_horaria'])
        fecha_local = datetime(2026, 10, 25).date()
        self.crear_recordatorio(hora='02:30:00', dias=[6])
        self.crear_ocurrencia(fecha_local)

        self.ejecutar('2026-10-25 00:35')
        self.ejecutar('2026-10-25 01:35')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(RegistroRecordatorio.objects.get().fecha, fecha_local)

    def test_fall_back_second_fold_is_fallback_when_first_window_was_missed(self):
        self.usuario.zona_horaria = 'Europe/Madrid'
        self.usuario.save(update_fields=['zona_horaria'])
        fecha_local = datetime(2026, 10, 25).date()
        self.crear_recordatorio(hora='02:30:00', dias=[6])
        self.crear_ocurrencia(fecha_local)

        self.ejecutar('2026-10-25 01:35')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(RegistroRecordatorio.objects.get().fecha, fecha_local)

    def test_sends_inside_tolerance_but_not_at_ten_minute_boundary(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.save(update_fields=['zona_horaria'])
        self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)

        self.ejecutar('2026-02-02 10:09')

        self.assertEqual(len(mail.outbox), 1)

    def test_does_not_send_at_ten_minute_boundary(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.save(update_fields=['zona_horaria'])
        self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)

        self.ejecutar('2026-02-02 10:10')

        self.assertEqual(mail.outbox, [])
        self.assertFalse(RegistroRecordatorio.objects.exists())

    def test_second_run_does_not_send_duplicate(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.save(update_fields=['zona_horaria'])
        self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)

        self.ejecutar('2026-02-02 10:05')
        self.ejecutar('2026-02-02 10:05')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(RegistroRecordatorio.objects.count(), 1)

    def test_dry_run_does_not_reserve_or_send(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.save(update_fields=['zona_horaria'])
        self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)
        salida = StringIO()

        call_command(
            'enviar_recordatorios',
            ahora='2026-02-02 10:05',
            dry_run=True,
            stdout=salida,
        )

        self.assertIn('1 recordatorio(s)', salida.getvalue())
        self.assertEqual(mail.outbox, [])
        self.assertFalse(RegistroRecordatorio.objects.exists())

    def test_completed_routine_and_day_without_occurrence_do_not_send(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.save(update_fields=['zona_horaria'])
        self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local, completada=True)
        self.ejecutar('2026-02-02 10:05')

        self.assertEqual(mail.outbox, [])
        self.assertFalse(RegistroRecordatorio.objects.exists())

        Recordatorio.objects.all().delete()
        self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.ejecutar('2026-02-02 10:05')
        self.assertEqual(mail.outbox, [])
        self.assertFalse(RegistroRecordatorio.objects.exists())

    def test_inactive_preference_or_user_skips_sending(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.recordatorios_activos = False
        self.usuario.save(update_fields=['zona_horaria', 'recordatorios_activos'])
        self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)

        self.ejecutar('2026-02-02 10:05')

        self.assertEqual(mail.outbox, [])
        self.assertFalse(RegistroRecordatorio.objects.exists())

        self.usuario.recordatorios_activos = True
        self.usuario.is_active = False
        self.usuario.save(update_fields=['recordatorios_activos', 'is_active'])
        self.ejecutar('2026-02-02 10:05')
        self.assertEqual(mail.outbox, [])

    def test_patient_without_user_is_logged_and_skipped(self):
        paciente_sin_usuario = Paciente.objects.create(
            nombre='Paciente sin cuenta',
            email='paciente-sin-cuenta-recordatorio@example.com',
        )
        fecha_local = datetime(2026, 2, 2).date()
        self.crear_recordatorio(
            paciente=paciente_sin_usuario,
            hora='10:00:00',
            dias=[0],
        )
        self.crear_ocurrencia(fecha_local, paciente=paciente_sin_usuario)

        with self.assertLogs('notificaciones.services', level='WARNING') as logs:
            self.ejecutar('2026-02-02 10:05')

        self.assertTrue(any('no tiene usuario asociado' in line for line in logs.output))
        self.assertEqual(mail.outbox, [])
        self.assertFalse(RegistroRecordatorio.objects.exists())

    def test_email_failure_is_registered_and_retried_inside_window(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.save(update_fields=['zona_horaria'])
        recordatorio = self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)

        with patch(
            'notificaciones.services.enviar_correo',
            return_value=(False, 'SMTP no disponible'),
        ):
            self.ejecutar('2026-02-02 10:05')

        registro = RegistroRecordatorio.objects.get()
        self.assertIsNone(registro.enviado_en)
        self.assertEqual(registro.error, 'SMTP no disponible')
        self.assertIsNone(registro.procesando_en)

        self.ejecutar('2026-02-02 10:06')

        registro.refresh_from_db()
        self.assertIsNotNone(registro.enviado_en)
        self.assertEqual(registro.error, '')
        self.assertEqual(len(mail.outbox), 1)

    def test_active_processing_claim_prevents_another_execution_from_sending(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.save(update_fields=['zona_horaria'])
        recordatorio = self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)
        RegistroRecordatorio.objects.create(
            recordatorio=recordatorio,
            fecha=fecha_local,
            procesando_en=timezone.now(),
        )

        self.ejecutar('2026-02-02 10:05')

        self.assertEqual(mail.outbox, [])

    def test_stale_processing_claim_can_be_retried_inside_window(self):
        fecha_local = datetime(2026, 2, 2).date()
        self.usuario.zona_horaria = 'UTC'
        self.usuario.save(update_fields=['zona_horaria'])
        recordatorio = self.crear_recordatorio(hora='10:00:00', dias=[0])
        self.crear_ocurrencia(fecha_local)
        RegistroRecordatorio.objects.create(
            recordatorio=recordatorio,
            fecha=fecha_local,
            procesando_en=timezone.now() - timedelta(minutes=2),
        )

        self.ejecutar('2026-02-02 10:05')

        self.assertEqual(len(mail.outbox), 1)
        registro = RegistroRecordatorio.objects.get()
        self.assertIsNotNone(registro.enviado_en)


class ResumenSemanalTests(TestCase):
    def setUp(self):
        self.zona = ZoneInfo('America/El_Salvador')
        self.usuario = Usuario.objects.create(
            email='paciente-resumen-semanal@example.com',
            nombre='Paciente resumen',
            role=Usuario.ROLE_PACIENTE,
            zona_horaria=self.zona.key,
        )
        self.paciente = Paciente.objects.create(
            usuario=self.usuario,
            nombre=self.usuario.nombre,
            email=self.usuario.email,
        )
        self.numero = 0

    def fecha_hora_local(self, fecha, hora=time(12), zona=None):
        zona = zona or self.zona
        return datetime.combine(fecha, hora, tzinfo=zona)

    def crear_ocurrencia(self, fecha, completada=True, nivel_dolor=None, zona=None):
        self.numero += 1
        asignacion = RutinaAsignada.objects.create(
            paciente=self.paciente,
            video_id=f'video-resumen-{self.numero}',
            titulo=f'Rutina resumen {self.numero}',
            fecha_programada=fecha,
            fecha_inicio=fecha,
            fecha_fin=fecha,
        )
        return OcurrenciaRutina.objects.create(
            asignacion=asignacion,
            fecha=fecha,
            completada_en=(
                self.fecha_hora_local(fecha, zona=zona)
                if completada
                else None
            ),
            nivel_dolor=nivel_dolor,
        )

    def crear_evaluacion(
        self,
        fecha,
        nivel_dolor,
        metrica='',
        valor_actual=None,
        unidad='',
        zona=None,
    ):
        evaluacion = EvaluacionClinica.objects.create(
            paciente=self.paciente,
            nivel_dolor=nivel_dolor,
            metrica=metrica,
            valor_actual=valor_actual,
            unidad=unidad,
        )
        EvaluacionClinica.objects.filter(pk=evaluacion.pk).update(
            fecha=self.fecha_hora_local(fecha, zona=zona),
        )
        evaluacion.refresh_from_db()
        return evaluacion

    def crear_objetivo(
        self,
        nombre,
        metrica,
        valor_objetivo,
        creado_en,
        direccion=ObjetivoTerapeutico.DIRECCION_MAYOR,
        unidad='',
    ):
        objetivo = ObjetivoTerapeutico.objects.create(
            paciente=self.paciente,
            nombre=nombre,
            metrica=metrica,
            direccion=direccion,
            valor_objetivo=Decimal(str(valor_objetivo)),
            unidad=unidad,
        )
        ObjetivoTerapeutico.objects.filter(pk=objetivo.pk).update(
            creado_en=creado_en,
        )
        objetivo.refresh_from_db()
        return objetivo

    def test_complete_week_counts_routines_sessions_pain_activity_and_alerts(self):
        monday = date(2026, 3, 2)
        for day_offset, pain in enumerate((2, 4)):
            self.crear_ocurrencia(
                monday - timedelta(days=7) + timedelta(days=day_offset),
                nivel_dolor=pain,
            )

        occurrences = []
        for day_offset, pain in enumerate((3, 5, 4, 6, 2, None, None)):
            occurrence = self.crear_ocurrencia(
                monday + timedelta(days=day_offset),
                completada=day_offset < 5,
                nivel_dolor=pain,
            )
            occurrences.append(occurrence)

        for state in (
            Sesion.ESTADO_PROGRAMADA,
            Sesion.ESTADO_COMPLETADA,
            Sesion.ESTADO_CANCELADA,
            Sesion.ESTADO_NO_ASISTIO,
        ):
            Sesion.objects.create(
                paciente=self.paciente,
                fecha=self.fecha_hora_local(monday + timedelta(days=2)),
                objetivo='Sesión semanal',
                estado=state,
            )

        self.crear_objetivo(
            'Aumentar fuerza',
            'Fuerza',
            10,
            self.fecha_hora_local(monday - timedelta(days=1)),
            unidad='kg',
        )
        self.crear_evaluacion(
            monday + timedelta(days=6),
            nivel_dolor=3,
            metrica='fuerza',
            valor_actual=12,
            unidad='KG',
        )
        alerta = AlertaDolor.objects.create(
            paciente=self.paciente,
            ocurrencia=occurrences[1],
            nivel_dolor=5,
            regla=AlertaDolor.REGLA_SUBIDA,
        )
        AlertaDolor.objects.filter(pk=alerta.pk).update(
            creada_en=self.fecha_hora_local(monday + timedelta(days=4)),
        )

        resumen = resumen_semanal(self.paciente, monday + timedelta(days=3))

        self.assertEqual(resumen['semana'], {
            'inicio': '2026-03-02',
            'fin': '2026-03-08',
        })
        self.assertEqual(resumen['rutinas']['programadas'], 7)
        self.assertEqual(resumen['rutinas']['completadas'], 5)
        self.assertEqual(resumen['rutinas']['adherencia_pct'], 71.43)
        self.assertEqual(resumen['eva']['promedio'], 4.0)
        self.assertEqual(resumen['eva']['promedio_semana_anterior'], 3.0)
        self.assertEqual(resumen['eva']['variacion'], 1.0)
        self.assertEqual(resumen['ultima_evaluacion']['nivel_dolor'], 3)
        self.assertEqual(
            resumen['sesiones']['por_estado'],
            {
                Sesion.ESTADO_PROGRAMADA: 1,
                Sesion.ESTADO_COMPLETADA: 1,
                Sesion.ESTADO_CANCELADA: 1,
                Sesion.ESTADO_NO_ASISTIO: 1,
            },
        )
        self.assertEqual(resumen['dias_con_actividad'], 5)
        self.assertEqual(resumen['alertas_dolor']['total'], 1)
        self.assertEqual(resumen['alertas_dolor']['items'][0]['regla'], 'subida')
        self.assertEqual(resumen['objetivos_cumplidos'], 1)
        self.assertEqual(resumen['objetivos_total'], 1)

    def test_empty_week_has_explicit_empty_values_and_no_division_by_zero(self):
        resumen = resumen_semanal(self.paciente, date(2026, 3, 2))

        self.assertEqual(resumen['rutinas']['programadas'], 0)
        self.assertEqual(resumen['rutinas']['completadas'], 0)
        self.assertIsNone(resumen['rutinas']['adherencia_pct'])
        self.assertIsNone(resumen['eva']['promedio'])
        self.assertIsNone(resumen['eva']['promedio_semana_anterior'])
        self.assertIsNone(resumen['eva']['variacion'])
        self.assertIsNone(resumen['ultima_evaluacion'])
        self.assertTrue(all(
            cantidad == 0
            for cantidad in resumen['sesiones']['por_estado'].values()
        ))
        self.assertEqual(resumen['dias_con_actividad'], 0)
        self.assertEqual(resumen['alertas_dolor'], {'total': 0, 'items': []})
        self.assertEqual(resumen['objetivos_cumplidos'], 0)
        self.assertEqual(resumen['objetivos_total'], 0)

    def test_partial_week_uses_only_completed_occurrences_with_registered_pain(self):
        monday = date(2026, 3, 2)
        self.crear_ocurrencia(monday, completada=True, nivel_dolor=5)
        self.crear_ocurrencia(monday + timedelta(days=1), completada=False, nivel_dolor=None)

        resumen = resumen_semanal(self.paciente, monday)

        self.assertEqual(resumen['rutinas']['programadas'], 2)
        self.assertEqual(resumen['rutinas']['completadas'], 1)
        self.assertEqual(resumen['rutinas']['adherencia_pct'], 50.0)
        self.assertEqual(resumen['eva']['promedio'], 5.0)
        self.assertIsNone(resumen['eva']['variacion'])
        self.assertEqual(resumen['dias_con_actividad'], 1)

    def test_monday_and_sunday_are_included_but_next_monday_is_excluded(self):
        monday = date(2026, 6, 1)
        sunday = monday + timedelta(days=6)
        next_monday = sunday + timedelta(days=1)
        monday_occurrence = self.crear_ocurrencia(monday, nivel_dolor=2)
        sunday_occurrence = self.crear_ocurrencia(sunday, nivel_dolor=4)
        self.crear_ocurrencia(next_monday, nivel_dolor=8)

        monday_evaluation = self.crear_evaluacion(
            monday,
            2,
            zona=self.zona,
        )
        sunday_evaluation = self.crear_evaluacion(
            sunday,
            4,
            zona=self.zona,
        )
        next_monday_evaluation = self.crear_evaluacion(
            next_monday,
            9,
            zona=self.zona,
        )
        EvaluacionClinica.objects.filter(pk=monday_evaluation.pk).update(
            fecha=self.fecha_hora_local(monday, time.min),
        )
        EvaluacionClinica.objects.filter(pk=sunday_evaluation.pk).update(
            fecha=self.fecha_hora_local(sunday, time.max),
        )
        EvaluacionClinica.objects.filter(pk=next_monday_evaluation.pk).update(
            fecha=self.fecha_hora_local(next_monday, time.min),
        )
        for fecha in (
            self.fecha_hora_local(monday, time.min),
            self.fecha_hora_local(sunday, time.max),
            self.fecha_hora_local(next_monday, time.min),
        ):
            Sesion.objects.create(
                paciente=self.paciente,
                fecha=fecha,
                objetivo='Límite semanal',
                estado=Sesion.ESTADO_PROGRAMADA,
            )

        for occurrence, fecha in (
            (monday_occurrence, self.fecha_hora_local(monday, time.min)),
            (sunday_occurrence, self.fecha_hora_local(sunday, time.max)),
        ):
            alerta = AlertaDolor.objects.create(
                paciente=self.paciente,
                ocurrencia=occurrence,
                nivel_dolor=occurrence.nivel_dolor,
                regla=AlertaDolor.REGLA_UMBRAL,
            )
            AlertaDolor.objects.filter(pk=alerta.pk).update(creada_en=fecha)

        next_monday_alert = AlertaDolor.objects.create(
            paciente=self.paciente,
            ocurrencia=OcurrenciaRutina.objects.get(asignacion__fecha_programada=next_monday),
            nivel_dolor=8,
            regla=AlertaDolor.REGLA_UMBRAL,
        )
        AlertaDolor.objects.filter(pk=next_monday_alert.pk).update(
            creada_en=self.fecha_hora_local(next_monday, time.min),
        )

        resumen = resumen_semanal(self.paciente, sunday)

        self.assertEqual(resumen['semana']['inicio'], monday.isoformat())
        self.assertEqual(resumen['rutinas']['programadas'], 2)
        self.assertEqual(resumen['eva']['promedio'], 3.0)
        self.assertEqual(resumen['ultima_evaluacion']['nivel_dolor'], 4)
        self.assertEqual(resumen['sesiones']['por_estado']['programada'], 2)
        self.assertEqual(resumen['alertas_dolor']['total'], 2)

    def test_dst_week_uses_local_datetime_boundaries(self):
        zona_dst = ZoneInfo('America/New_York')
        self.usuario.zona_horaria = zona_dst.key
        self.usuario.save(update_fields=['zona_horaria'])
        monday = date(2026, 3, 2)
        sunday = date(2026, 3, 8)
        next_monday = sunday + timedelta(days=1)

        for fecha, hora in (
            (sunday, time(1, 59)),
            (sunday, time(3, 0)),
            (next_monday, time.min),
        ):
            Sesion.objects.create(
                paciente=self.paciente,
                fecha=self.fecha_hora_local(fecha, hora, zona_dst),
                objetivo='Semana DST',
                estado=Sesion.ESTADO_PROGRAMADA,
            )
        evaluacion_incluida = self.crear_evaluacion(
            sunday,
            4,
            zona=zona_dst,
        )
        evaluacion_excluida = self.crear_evaluacion(
            next_monday,
            9,
            zona=zona_dst,
        )
        EvaluacionClinica.objects.filter(pk=evaluacion_incluida.pk).update(
            fecha=self.fecha_hora_local(sunday, time.max, zona_dst),
        )
        EvaluacionClinica.objects.filter(pk=evaluacion_excluida.pk).update(
            fecha=self.fecha_hora_local(next_monday, time.min, zona_dst),
        )

        resumen = resumen_semanal(self.paciente, sunday)

        self.assertEqual(resumen['semana']['inicio'], monday.isoformat())
        self.assertEqual(resumen['sesiones']['por_estado']['programada'], 2)
        self.assertEqual(resumen['ultima_evaluacion']['nivel_dolor'], 4)
        self.assertEqual(resumen['zona_usada'], 'America/New_York')
        self.assertFalse(resumen['zona_es_respaldo'])

    def test_objectives_use_latest_evaluation_as_of_week_end_and_only_existing_goals(self):
        monday = date(2026, 5, 4)
        sunday = monday + timedelta(days=6)
        self.crear_objetivo(
            'Fuerza alcanzada',
            'fuerza',
            20,
            self.fecha_hora_local(monday - timedelta(days=20)),
            unidad='kg',
        )
        self.crear_objetivo(
            'Equilibrio sin evaluación',
            'equilibrio',
            10,
            self.fecha_hora_local(monday - timedelta(days=2)),
            unidad='s',
        )
        self.crear_objetivo(
            'Objetivo futuro',
            'fuerza',
            100,
            self.fecha_hora_local(sunday + timedelta(days=1)),
            unidad='kg',
        )
        self.crear_evaluacion(
            monday - timedelta(days=10),
            nivel_dolor=4,
            metrica='Fuerza',
            valor_actual=25,
            unidad='KG',
        )
        self.crear_evaluacion(
            sunday + timedelta(days=1),
            nivel_dolor=1,
            metrica='fuerza',
            valor_actual=0,
            unidad='kg',
        )

        resumen = resumen_semanal(self.paciente, monday)

        self.assertEqual(resumen['objetivos_total'], 2)
        self.assertEqual(resumen['objetivos_cumplidos'], 1)
        objetivos = {
            objetivo['nombre']: objetivo['cumplido']
            for objetivo in resumen['objetivos_detalle']
        }
        self.assertTrue(objetivos['Fuerza alcanzada'])
        self.assertFalse(objetivos['Equilibrio sin evaluación'])
        self.assertIsNone(resumen['ultima_evaluacion'])

    def test_objective_equality_matches_patient_progress_rule_in_both_directions(self):
        from princpal.views import patient_progress_payload

        monday = date(2026, 5, 4)
        for nombre, metrica, direccion, unidad in (
            ('Alcanzar valor', 'fuerza', ObjetivoTerapeutico.DIRECCION_MAYOR, 'kg'),
            ('Reducir a valor', 'dolor', ObjetivoTerapeutico.DIRECCION_MENOR, 'puntos'),
        ):
            self.crear_objetivo(
                nombre,
                metrica,
                10,
                self.fecha_hora_local(monday - timedelta(days=1)),
                direccion=direccion,
                unidad=unidad,
            )
            self.crear_evaluacion(
                monday + timedelta(days=1),
                nivel_dolor=4,
                metrica=metrica,
                valor_actual=10,
                unidad=unidad,
            )

        resumen = resumen_semanal(self.paciente, monday)
        esperado = {
            objetivo['name']: objetivo['completed']
            for objetivo in patient_progress_payload(self.paciente)['goals']
        }
        obtenido = {
            objetivo['nombre']: objetivo['cumplido']
            for objetivo in resumen['objetivos_detalle']
        }

        self.assertEqual(obtenido, esperado)
        self.assertEqual(obtenido, {
            'Alcanzar valor': True,
            'Reducir a valor': True,
        })

    def test_zone_fallbacks_and_explicit_zone_priority(self):
        monday = date(2026, 3, 2)
        self.assertEqual(
            resumen_semanal(self.paciente, monday, zona='America/New_York')['zona_usada'],
            'America/New_York',
        )
        self.assertFalse(
            resumen_semanal(self.paciente, monday, zona='America/New_York')['zona_es_respaldo'],
        )

        self.usuario.zona_horaria = 'Zona/Desconocida'
        self.usuario.save(update_fields=['zona_horaria'])
        with self.assertLogs('notificaciones.services', level='WARNING') as logs:
            resumen_invalido = resumen_semanal(self.paciente, monday)
        self.assertTrue(any(str(self.paciente.pk) in line for line in logs.output))
        self.assertEqual(resumen_invalido['zona_usada'], settings.TIME_ZONE)
        self.assertTrue(resumen_invalido['zona_es_respaldo'])

        paciente_sin_usuario = Paciente.objects.create(
            nombre='Paciente sin usuario',
            email='paciente-sin-usuario-resumen@example.com',
        )
        resumen_sin_usuario = resumen_semanal(paciente_sin_usuario, monday)
        self.assertEqual(resumen_sin_usuario['zona_usada'], settings.TIME_ZONE)
        self.assertTrue(resumen_sin_usuario['zona_es_respaldo'])

    def test_inicio_de_semana_normalizes_dates_and_aware_datetimes(self):
        monday = date(2026, 3, 2)
        sunday = monday + timedelta(days=6)

        self.assertEqual(inicio_de_semana(monday, self.zona), monday)
        self.assertEqual(inicio_de_semana(sunday, self.zona), monday)
        self.assertEqual(
            inicio_de_semana(
                datetime(2026, 3, 9, 3, 30, tzinfo=ZoneInfo('UTC')),
                self.zona,
            ),
            monday,
        )


@override_settings(
    DEFAULT_FROM_EMAIL='pruebas@nexorev.local',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    RESUMEN_SEMANAL_DIA=6,
    RESUMEN_SEMANAL_HORA=20,
)
class EnviarResumenesSemanalesCommandTests(TestCase):
    instante_corte_el_salvador = '2026-03-09 02:00'

    def setUp(self):
        mail.outbox.clear()
        self.numero = 0
        self.paciente = self.crear_paciente(
            'America/El_Salvador',
            'paciente-resumen-comando@example.com',
        )

    def crear_paciente(
        self,
        zona,
        email,
        resumen_semanal_activo=True,
        is_active=True,
    ):
        self.numero += 1
        usuario = Usuario.objects.create(
            email=email,
            nombre=f'Paciente resumen {self.numero}',
            role=Usuario.ROLE_PACIENTE,
            zona_horaria=zona,
            resumen_semanal_activo=resumen_semanal_activo,
            is_active=is_active,
        )
        return Paciente.objects.create(
            usuario=usuario,
            nombre=usuario.nombre,
            email=email,
        )

    def ejecutar(self, ahora=None, dry_run=False, stdout=None):
        opciones = {'dry_run': dry_run}
        if ahora is not None:
            opciones['ahora'] = ahora
        if stdout is not None:
            opciones['stdout'] = stdout
        call_command('enviar_resumenes_semanales', **opciones)

    def test_sends_empty_week_summary_and_is_idempotent_after_missed_schedule(self):
        self.ejecutar(self.instante_corte_el_salvador)
        self.ejecutar('2026-03-09 03:00')

        self.assertEqual(len(mail.outbox), 1)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, [self.paciente.usuario.email])
        self.assertIn('Tu resumen semanal', mensaje.subject)
        self.assertIn('Rutinas programadas: 0', mensaje.body)
        self.assertIn('sin registros', mensaje.body)
        self.assertIn('/principal/', mensaje.body)
        self.assertEqual(len(mensaje.alternatives), 1)
        self.assertIn('text/html', mensaje.alternatives[0][1])

        envio = EnvioResumenSemanal.objects.get()
        self.assertEqual(envio.semana_inicio, date(2026, 3, 2))
        self.assertIsNotNone(envio.enviado_en)
        self.assertEqual(envio.error, '')

    def test_same_utc_instant_uses_each_patients_local_schedule(self):
        otro_paciente = self.crear_paciente(
            'America/Los_Angeles',
            'paciente-resumen-los-angeles@example.com',
        )
        EnvioResumenSemanal.objects.create(
            paciente=otro_paciente,
            semana_inicio=date(2026, 2, 23),
            enviado_en=timezone.now(),
        )

        self.ejecutar(self.instante_corte_el_salvador)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.paciente.usuario.email])
        self.assertTrue(
            EnvioResumenSemanal.objects.filter(
                paciente=self.paciente,
                semana_inicio=date(2026, 3, 2),
                enviado_en__isnull=False,
            ).exists()
        )
        self.assertFalse(
            EnvioResumenSemanal.objects.filter(
                paciente=otro_paciente,
                semana_inicio=date(2026, 3, 2),
            ).exists()
        )

    def test_disabled_preference_and_inactive_user_are_skipped(self):
        self.paciente.usuario.resumen_semanal_activo = False
        self.paciente.usuario.save(update_fields=['resumen_semanal_activo'])
        self.ejecutar(self.instante_corte_el_salvador)
        self.assertFalse(EnvioResumenSemanal.objects.exists())
        self.assertEqual(mail.outbox, [])

        self.paciente.usuario.resumen_semanal_activo = True
        self.paciente.usuario.is_active = False
        self.paciente.usuario.save(
            update_fields=['resumen_semanal_activo', 'is_active'],
        )
        self.ejecutar(self.instante_corte_el_salvador)
        self.assertFalse(EnvioResumenSemanal.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_patient_without_user_is_logged_and_skipped(self):
        paciente_sin_usuario = Paciente.objects.create(
            nombre='Paciente sin cuenta',
            email='paciente-sin-cuenta-resumen@example.com',
        )

        with self.assertLogs(
            'notificaciones.management.commands.enviar_resumenes_semanales',
            level='WARNING',
        ) as logs:
            self.ejecutar(self.instante_corte_el_salvador)

        self.assertTrue(any(
            str(paciente_sin_usuario.pk) in line
            for line in logs.output
        ))
        self.assertFalse(
            EnvioResumenSemanal.objects.filter(
                paciente=paciente_sin_usuario,
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.paciente.usuario.email])

    def test_failed_email_is_recorded_and_retried_on_next_run(self):
        with patch(
            'notificaciones.services.enviar_correo',
            return_value=(False, 'SMTP no disponible'),
        ):
            self.ejecutar(self.instante_corte_el_salvador)

        envio = EnvioResumenSemanal.objects.get(paciente=self.paciente)
        self.assertIsNone(envio.enviado_en)
        self.assertEqual(envio.error, 'SMTP no disponible')
        self.assertEqual(mail.outbox, [])

        self.ejecutar('2026-03-09 03:00')

        envio.refresh_from_db()
        self.assertIsNotNone(envio.enviado_en)
        self.assertEqual(envio.error, '')
        self.assertEqual(len(mail.outbox), 1)

    def test_dry_run_does_not_create_records_or_send(self):
        salida = StringIO()

        self.ejecutar(
            self.instante_corte_el_salvador,
            dry_run=True,
            stdout=salida,
        )

        self.assertIn('1 resumen(es) semanal(es)', salida.getvalue())
        self.assertFalse(EnvioResumenSemanal.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_utc_suffixes_are_accepted(self):
        for ahora in (
            '2026-03-09 02:00Z',
            '2026-03-09 02:00+00:00',
        ):
            salida = StringIO()
            self.ejecutar(ahora, dry_run=True, stdout=salida)
            self.assertIn('1 resumen(es) semanal(es)', salida.getvalue())
        self.assertFalse(EnvioResumenSemanal.objects.exists())

    def test_invalid_datetime_and_non_utc_offset_raise_clear_command_errors(self):
        for ahora in (
            '09/03/2026 02:00',
            '2026-03-09 02:00-06:00',
        ):
            with self.subTest(ahora=ahora):
                with self.assertRaises(CommandError) as error:
                    self.ejecutar(ahora)
                self.assertIn('2026-03-09 02:00', str(error.exception))

    def test_database_allows_only_one_record_per_patient_and_week(self):
        EnvioResumenSemanal.objects.create(
            paciente=self.paciente,
            semana_inicio=date(2026, 3, 2),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EnvioResumenSemanal.objects.create(
                    paciente=self.paciente,
                    semana_inicio=date(2026, 3, 2),
                )


class ReporteSemanalApiTests(TestCase):
    def setUp(self):
        self.doctor = Usuario.objects.create(
            email='doctor-api-reporte@example.com',
            nombre='Médico reporte',
            role=Usuario.ROLE_DOCTOR,
            zona_horaria='America/El_Salvador',
        )
        self.paciente = self.crear_paciente(
            'paciente-reporte@example.com',
            'America/El_Salvador',
            self.doctor,
        )
        self.segundo_paciente = self.crear_paciente(
            'segundo-paciente-reporte@example.com',
            'America/New_York',
            self.doctor,
        )
        otro_doctor = Usuario.objects.create(
            email='otro-doctor-api-reporte@example.com',
            nombre='Otro médico',
            role=Usuario.ROLE_DOCTOR,
        )
        self.paciente_ajeno = self.crear_paciente(
            'paciente-ajeno-reporte@example.com',
            'America/El_Salvador',
            otro_doctor,
        )
        self.client_doctor = self.crear_cliente(self.doctor)
        self.client_paciente = self.crear_cliente(
            Usuario.objects.create(
                email='usuario-paciente-api-reporte@example.com',
                nombre='Usuario paciente',
                role=Usuario.ROLE_PACIENTE,
            )
        )
        self.url = reverse('notif_reporte_semanal')

    @staticmethod
    def crear_paciente(email, zona, doctor):
        usuario = Usuario.objects.create(
            email=f'usuario-{email}',
            nombre=f'Cuenta {email}',
            role=Usuario.ROLE_PACIENTE,
            zona_horaria=zona,
        )
        return Paciente.objects.create(
            usuario=usuario,
            nombre=f'Paciente {email}',
            email=email,
            doctor=doctor,
        )

    @staticmethod
    def crear_cliente(usuario):
        client = Client()
        session = client.session
        session['current_user'] = usuario.email
        session['current_user_role'] = usuario.role
        session.save()
        return client

    def consultar(self, ids=None, semana=None, formato=None):
        parametros = []
        if ids is not None:
            parametros.extend(('pacientes', str(paciente_id)) for paciente_id in ids)
        if semana is not None:
            parametros.append(('semana', semana))
        if formato is not None:
            parametros.append(('formato', formato))
        url = self.url
        if parametros:
            url = f'{url}?{urlencode(parametros)}'
        return self.client_doctor.get(url)

    def test_without_patient_parameter_returns_only_all_owned_patients(self):
        respuesta = self.consultar()

        self.assertEqual(respuesta.status_code, 200)
        ids = [fila['paciente_id'] for fila in respuesta.json()['pacientes']]
        self.assertEqual(ids, [self.paciente.pk, self.segundo_paciente.pk])
        self.assertNotIn(self.paciente_ajeno.pk, ids)

        respuesta_vacia = self.consultar(ids=[''])
        self.assertEqual(respuesta_vacia.status_code, 200)
        self.assertEqual(
            [fila['paciente_id'] for fila in respuesta_vacia.json()['pacientes']],
            ids,
        )

    def test_one_multiple_and_duplicate_patient_ids_preserve_requested_order(self):
        respuesta_uno = self.consultar(ids=[self.segundo_paciente.pk])
        self.assertEqual(
            [fila['paciente_id'] for fila in respuesta_uno.json()['pacientes']],
            [self.segundo_paciente.pk],
        )

        respuesta_varios = self.consultar(ids=[
            self.segundo_paciente.pk,
            self.paciente.pk,
            self.segundo_paciente.pk,
        ])
        self.assertEqual(respuesta_varios.status_code, 200)
        self.assertEqual(
            [fila['paciente_id'] for fila in respuesta_varios.json()['pacientes']],
            [self.segundo_paciente.pk, self.paciente.pk],
        )

    def test_invalid_patient_values_and_more_than_two_hundred_ids_return_400(self):
        for valor in ('texto', '-1', '0'):
            with self.subTest(valor=valor):
                respuesta = self.consultar(ids=[valor])
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(set(respuesta.json()), {'success', 'error'})

        respuesta = self.consultar(ids=[self.paciente.pk] * 201)
        self.assertEqual(respuesta.status_code, 400)

    def test_foreign_missing_and_mixed_patient_ids_return_same_403(self):
        respuesta_ajeno = self.consultar(ids=[self.paciente_ajeno.pk])
        respuesta_inexistente = self.consultar(ids=[99999999])
        respuesta_mixta = self.consultar(ids=[
            self.paciente.pk,
            self.paciente_ajeno.pk,
        ])

        self.assertEqual(respuesta_ajeno.status_code, 403)
        self.assertEqual(respuesta_inexistente.status_code, 403)
        self.assertEqual(respuesta_mixta.status_code, 403)
        self.assertEqual(respuesta_ajeno.json(), respuesta_inexistente.json())
        self.assertNotIn('pacientes', respuesta_mixta.json())

    def test_invalid_week_returns_400(self):
        respuesta = self.consultar(semana='no-es-fecha')

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(set(respuesta.json()), {'success', 'error'})

    def test_week_date_normalizes_to_monday_and_empty_summaries_are_explicit(self):
        respuesta = self.consultar(
            ids=[self.paciente.pk],
            semana='2026-03-05',
        )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos['semana'], {
            'inicio': '2026-03-02',
            'fin': '2026-03-08',
        })
        self.assertEqual(datos['totales']['rutinas_programadas'], 0)
        self.assertEqual(datos['totales']['rutinas_completadas'], 0)
        self.assertIsNone(datos['totales']['adherencia_pct'])
        self.assertEqual(datos['totales']['alertas_dolor'], 0)
        resumen = datos['pacientes'][0]['resumen']
        self.assertEqual(resumen['rutinas']['programadas'], 0)
        self.assertEqual(resumen['alertas_dolor'], {'total': 0, 'items': []})

    def test_totals_sum_patient_weekly_metrics(self):
        monday = date(2026, 3, 2)
        instante_local = datetime(
            2026,
            3,
            2,
            12,
            tzinfo=ZoneInfo('America/El_Salvador'),
        )
        asignacion = RutinaAsignada.objects.create(
            paciente=self.paciente,
            video_id='video-api-reporte',
            titulo='Rutina de reporte',
            fecha_programada=monday,
            fecha_inicio=monday,
            fecha_fin=monday,
        )
        ocurrencia = OcurrenciaRutina.objects.create(
            asignacion=asignacion,
            fecha=monday,
            completada_en=instante_local,
            nivel_dolor=5,
        )
        Sesion.objects.create(
            paciente=self.paciente,
            fecha=instante_local,
            objetivo='Sesión de reporte',
            estado=Sesion.ESTADO_COMPLETADA,
        )
        alerta = AlertaDolor.objects.create(
            paciente=self.paciente,
            ocurrencia=ocurrencia,
            nivel_dolor=5,
            regla=AlertaDolor.REGLA_UMBRAL,
        )
        AlertaDolor.objects.filter(pk=alerta.pk).update(creada_en=instante_local)

        respuesta = self.consultar(
            ids=[self.paciente.pk, self.segundo_paciente.pk],
            semana='2026-03-02',
        )

        totales = respuesta.json()['totales']
        self.assertEqual(totales['pacientes'], 2)
        self.assertEqual(totales['rutinas_programadas'], 1)
        self.assertEqual(totales['rutinas_completadas'], 1)
        self.assertEqual(totales['adherencia_pct'], 100.0)
        self.assertEqual(
            totales['sesiones_por_estado'][Sesion.ESTADO_COMPLETADA],
            1,
        )
        self.assertEqual(totales['dias_con_actividad'], 1)
        self.assertEqual(totales['alertas_dolor'], 1)

    def test_default_week_is_the_last_complete_week_in_doctors_timezone(self):
        with patch(
            'notificaciones.views.timezone.localdate',
            return_value=date(2026, 3, 9),
        ):
            respuesta = self.consultar(ids=[self.paciente.pk])

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['semana'], {
            'inicio': '2026-03-02',
            'fin': '2026-03-08',
        })

    def test_patient_role_is_forbidden_and_missing_session_is_unauthorized(self):
        respuesta_paciente = self.client_paciente.get(self.url)
        respuesta_sin_sesion = Client().get(self.url)

        self.assertEqual(respuesta_paciente.status_code, 403)
        self.assertEqual(respuesta_sin_sesion.status_code, 401)

    def test_inactive_doctor_is_forbidden(self):
        self.doctor.is_active = False
        self.doctor.save(update_fields=['is_active'])

        self.assertEqual(self.client_doctor.get(self.url).status_code, 403)

    def crear_ocurrencia_reporte(self, paciente, fecha, numero, nivel_dolor=None):
        asignacion = RutinaAsignada.objects.create(
            paciente=paciente,
            video_id=f'video-export-reporte-{numero}',
            titulo=f'Rutina exportación {numero}',
            fecha_programada=fecha,
            fecha_inicio=fecha,
            fecha_fin=fecha,
        )
        completada_en = (
            datetime.combine(
                fecha,
                time(12, tzinfo=ZoneInfo('America/El_Salvador')),
            )
            if nivel_dolor is not None
            else None
        )
        return OcurrenciaRutina.objects.create(
            asignacion=asignacion,
            fecha=fecha,
            completada_en=completada_en,
            nivel_dolor=nivel_dolor,
        )

    def crear_datos_exportacion(self):
        self.paciente.nombre = 'José Ñandú ' + ('Paciente-largo-' * 8)
        self.paciente.email = 'correo-privado-reporte@example.com'
        self.paciente.telefono = '555-0199'
        self.paciente.save(update_fields=['nombre', 'email', 'telefono'])
        self.crear_ocurrencia_reporte(
            self.paciente,
            date(2026, 2, 23),
            1,
            nivel_dolor=6,
        )
        self.crear_ocurrencia_reporte(
            self.paciente,
            date(2026, 3, 2),
            2,
            nivel_dolor=4,
        )
        self.crear_ocurrencia_reporte(
            self.paciente,
            date(2026, 3, 3),
            3,
        )

    @override_settings(
        DEFAULT_FROM_EMAIL='pruebas@nexorev.local',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_adherence_matches_json_xlsx_pdf_and_patient_email(self):
        self.crear_datos_exportacion()
        json_response = self.consultar(
            ids=[self.paciente.pk],
            semana='2026-03-02',
        )
        self.assertEqual(json_response.status_code, 200)
        payload = json_response.json()
        resumen = payload['pacientes'][0]['resumen']
        self.assertEqual(resumen['rutinas']['adherencia_pct'], 50.0)
        self.assertEqual(resumen['eva']['promedio'], 4.0)
        self.assertEqual(resumen['eva']['variacion'], -2.0)

        xlsx_response = self.consultar(
            ids=[self.paciente.pk],
            semana='2026-03-02',
            formato='xlsx',
        )
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn(
            'reporte-semanal-2026-03-02-2026-03-08.xlsx',
            xlsx_response['Content-Disposition'],
        )
        workbook = load_workbook(BytesIO(xlsx_response.content), data_only=False)
        sheet = workbook['Reporte semanal']
        patient_row = next(
            index
            for index in range(1, sheet.max_row + 1)
            if sheet.cell(index, 1).value == self.paciente.nombre
        )
        self.assertEqual(sheet.cell(patient_row, 3).value, 50.0)
        self.assertEqual(sheet.cell(patient_row, 3).number_format, '0.00"%"')
        self.assertEqual(sheet.cell(patient_row, 4).value, 4.0)
        self.assertEqual(sheet.cell(patient_row, 5).value, -2.0)
        exported_text = '\n'.join(
            str(cell.value)
            for row in sheet.iter_rows()
            for cell in row
            if cell.value is not None
        )
        self.assertNotIn(self.paciente.email, exported_text)
        self.assertNotIn(self.paciente.telefono, exported_text)
        self.assertNotIn(self.paciente.usuario.email, exported_text)

        pdf_response = self.consultar(
            ids=[self.paciente.pk],
            semana='2026-03-02',
            formato='pdf',
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertTrue(pdf_response.content.startswith(b'%PDF-'))
        self.assertIn(b'%%EOF', pdf_response.content)
        self.assertIn(b'startxref', pdf_response.content)
        self.assertIn(
            'reporte-semanal-2026-03-02-2026-03-08.pdf',
            pdf_response['Content-Disposition'],
        )
        decompressed_streams = []
        for match in re.finditer(
            rb'stream\n(.*?)endstream',
            pdf_response.content,
            re.DOTALL,
        ):
            encoded = match.group(1).strip()
            if encoded.endswith(b'~>'):
                encoded = base64.a85decode(b'<~' + encoded, adobe=True)
            decompressed_streams.append(zlib.decompress(encoded))
        pdf_text = b'\n'.join(decompressed_streams)
        self.assertIn(b'50.00%', pdf_text)
        self.assertIn(b'4.00', pdf_text)
        self.assertIn(b'-2.00', pdf_text)
        self.assertIn(b'Paciente-largo-', pdf_text)
        self.assertGreater(pdf_text.count(b'Paciente-largo-'), 1)
        self.assertIn(b'<00E9>', pdf_text)
        self.assertIn(b'<00D1>', pdf_text)
        self.assertIn(b'<00FA>', pdf_text)
        self.assertNotIn(self.paciente.email.encode(), pdf_text)
        self.assertNotIn(self.paciente.telefono.encode(), pdf_text)
        self.assertNotIn(self.paciente.usuario.email.encode(), pdf_text)

        self.assertTrue(enviar_resumen_semanal(self.paciente, date(2026, 3, 2)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Adherencia: 50.00%', mail.outbox[0].body)

    def test_xlsx_neutralizes_formula_like_patient_names(self):
        for prefix in ('=', '+', '-', '@'):
            with self.subTest(prefix=prefix):
                self.paciente.nombre = f'{prefix}2+2'
                self.paciente.save(update_fields=['nombre'])
                response = self.consultar(
                    ids=[self.paciente.pk],
                    semana='2026-03-02',
                    formato='xlsx',
                )
                self.assertEqual(response.status_code, 200)
                sheet = load_workbook(
                    BytesIO(response.content),
                    data_only=False,
                )['Reporte semanal']
                patient_cell = next(
                    sheet.cell(index, 1)
                    for index in range(1, sheet.max_row + 1)
                    if sheet.cell(index, 1).value == f"'{prefix}2+2"
                )
                self.assertEqual(patient_cell.data_type, 's')

    def test_export_formats_reject_invalid_values_and_foreign_patients(self):
        invalid_format = self.consultar(
            ids=[self.paciente.pk],
            formato='csv',
        )
        self.assertEqual(invalid_format.status_code, 400)
        self.assertEqual(set(invalid_format.json()), {'success', 'error'})

        for formato in ('pdf', 'xlsx'):
            with self.subTest(formato=formato):
                response = self.consultar(
                    ids=[self.paciente_ajeno.pk],
                    formato=formato,
                )
                self.assertEqual(response.status_code, 403)


class ExportDependencyTests(SimpleTestCase):
    def assert_missing_dependency_response(self, export_function, dependency, formato):
        original_import = builtins.__import__

        def block_optional_dependency(name, *args, **kwargs):
            if name == dependency or name.startswith(f'{dependency}.'):
                raise ModuleNotFoundError(f"No module named '{dependency}'")
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=block_optional_dependency):
            response = export_function({})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(json.loads(response.content.decode('utf-8')), {
            'success': False,
            'error': (
                f'No se puede generar el archivo {formato}: '
                f'la dependencia {dependency} no está disponible.'
            ),
        })

    def test_missing_openpyxl_returns_json_500(self):
        self.assert_missing_dependency_response(
            exportar_reporte_xlsx,
            'openpyxl',
            'Excel',
        )

    def test_missing_reportlab_returns_json_500(self):
        self.assert_missing_dependency_response(
            exportar_reporte_pdf,
            'reportlab',
            'PDF',
        )


class RunLocalCommandTests(SimpleTestCase):
    def test_starts_runserver_without_the_auto_reloader(self):
        server = MagicMock()
        server.poll.side_effect = [None, 0, 0]

        with (
            patch(
                'notificaciones.management.commands.run_local.subprocess.Popen',
                return_value=server,
            ) as mocked_popen,
            patch('notificaciones.management.commands.run_local.time.sleep'),
        ):
            call_command('run_local', '127.0.0.1:8081', stdout=StringIO())

        server_command = mocked_popen.call_args.args[0]
        self.assertIn('runserver', server_command)
        self.assertIn('--noreload', server_command)
        self.assertEqual(server_command[-1], '127.0.0.1:8081')
        self.assertEqual(mocked_popen.call_args.kwargs['cwd'], settings.BASE_DIR)

    def test_runs_notification_jobs_immediately_while_server_is_running(self):
        from notificaciones.management.commands.run_local import Command

        server = MagicMock()
        server.poll.side_effect = [None, None, None, None, None, 0]

        with (
            patch(
                'notificaciones.management.commands.run_local.call_command',
            ) as mocked_call_command,
            patch('notificaciones.management.commands.run_local.time.sleep'),
        ):
            Command()._run_jobs(server)

        self.assertEqual(
            [call.args[0] for call in mocked_call_command.call_args_list],
            [
                'enviar_recordatorios',
                'reintentar_alertas_pendientes',
                'enviar_resumenes_semanales',
            ],
        )