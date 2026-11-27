import logging
import re
from datetime import datetime, timezone as datetime_timezone

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notificaciones.models import EnvioResumenSemanal
from notificaciones.services import (
    enviar_resumen_semanal,
    semana_resumen_pendiente,
)
from princpal.models import Paciente


logger = logging.getLogger(__name__)
FORMATO_AHORA = 'AAAA-MM-DD HH:MM'
EJEMPLO_AHORA = '"2026-03-09 02:00" o "2026-03-09 02:00Z"'


class Command(BaseCommand):
    help = 'Envía el resumen de la semana anterior según la zona horaria del paciente.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra cuántos resúmenes se enviarían, sin crear registros ni enviar.',
        )
        parser.add_argument(
            '--ahora',
            help=(
                'Fecha/hora de referencia UTC: AAAA-MM-DD HH:MM; acepta sufijo Z '
                'o +00:00. Ejemplo: "2026-03-09 02:00Z".'
            ),
        )

    def handle(self, *args, **options):
        ahora_utc = self._parse_ahora(options.get('ahora'))
        pacientes = Paciente.objects.select_related('usuario').order_by('pk')
        procesables = 0

        for paciente in pacientes.iterator():
            usuario = paciente.usuario
            if usuario is None:
                logger.warning(
                    'Se omite paciente_id=%s al enviar resúmenes semanales: '
                    'no tiene usuario asociado.',
                    paciente.pk,
                )
                continue
            if not usuario.is_active or not usuario.resumen_semanal_activo:
                continue

            semana_inicio = semana_resumen_pendiente(paciente, ahora_utc)
            if semana_inicio is None or EnvioResumenSemanal.objects.filter(
                paciente=paciente,
                semana_inicio=semana_inicio,
                enviado_en__isnull=False,
            ).exists():
                continue

            if options['dry_run']:
                procesables += 1
            elif enviar_resumen_semanal(paciente, semana_inicio):
                procesables += 1

        if options['dry_run']:
            self.stdout.write(
                f'Simulación: se enviarían {procesables} resumen(es) semanal(es).'
            )
        else:
            self.stdout.write(f'Se procesaron {procesables} resumen(es) semanal(es).')

    @staticmethod
    def _parse_ahora(valor):
        if not valor:
            return timezone.now().astimezone(datetime_timezone.utc)

        valor_base = valor
        if valor.endswith('Z'):
            valor_base = valor[:-1]
        elif valor.endswith('+00:00'):
            valor_base = valor[:-6]
        elif re.search(r'[+-]\d{2}:\d{2}$', valor):
            raise CommandError(
                '--ahora solo acepta UTC; no se permiten desfases distintos de '
                f'+00:00. Ejemplo válido: {EJEMPLO_AHORA}.'
            )

        if not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', valor_base):
            raise CommandError(
                f'Formato inválido para --ahora. Usa {FORMATO_AHORA} en UTC, '
                f'por ejemplo {EJEMPLO_AHORA}.'
            )
        try:
            fecha_hora = datetime.strptime(valor_base, '%Y-%m-%d %H:%M')
        except ValueError as error:
            raise CommandError(
                f'Fecha/hora inválida para --ahora. Usa {FORMATO_AHORA} en UTC, '
                f'por ejemplo {EJEMPLO_AHORA}.'
            ) from error
        return fecha_hora.replace(tzinfo=datetime_timezone.utc)
