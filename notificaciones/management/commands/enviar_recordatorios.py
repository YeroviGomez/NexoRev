from datetime import datetime, timezone as datetime_timezone

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notificaciones.models import Recordatorio
from notificaciones.services import procesar_recordatorio


class Command(BaseCommand):
    help = 'Envía los recordatorios de rutina pendientes en la hora local del paciente.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra cuántos recordatorios se enviarían, sin reservar ni enviar.',
        )
        parser.add_argument(
            '--ahora',
            help='Fecha/hora de referencia UTC con formato AAAA-MM-DD HH:MM.',
        )

    def handle(self, *args, **options):
        ahora_utc = self._parse_ahora(options.get('ahora'))
        recordatorios = Recordatorio.objects.filter(
            activo=True,
        ).select_related(
            'paciente',
            'paciente__usuario',
        ).order_by(
            'pk',
        )

        procesables = 0
        for recordatorio in recordatorios.iterator():
            if procesar_recordatorio(
                recordatorio,
                ahora_utc,
                dry_run=options['dry_run'],
            ):
                procesables += 1

        if options['dry_run']:
            self.stdout.write(
                f'Simulación: se enviarían {procesables} recordatorio(s).'
            )
        else:
            self.stdout.write(f'Se procesaron {procesables} recordatorio(s).')

    @staticmethod
    def _parse_ahora(valor):
        if not valor:
            return timezone.now()
        try:
            fecha_hora = datetime.strptime(valor, '%Y-%m-%d %H:%M')
        except ValueError as error:
            raise CommandError(
                'El formato de --ahora debe ser AAAA-MM-DD HH:MM en UTC.'
            ) from error
        return fecha_hora.replace(tzinfo=datetime_timezone.utc)
