from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notificaciones.models import AlertaDolor
from notificaciones.services import enviar_correo_alerta


class Command(BaseCommand):
    help = 'Reintenta el envío de correos de alertas de dolor pendientes.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra cuántas alertas se procesarían, sin enviar correos.',
        )
        parser.add_argument(
            '--ahora',
            help='Fecha/hora de referencia con formato AAAA-MM-DD HH:MM.',
        )

    def handle(self, *args, **options):
        ahora = self._parse_ahora(options.get('ahora'))
        alertas = AlertaDolor.objects.filter(
            correo_enviado_en__isnull=True,
            doctor__isnull=False,
            doctor__is_active=True,
            correo_intentos__lt=5,
            creada_en__lte=ahora,
        ).select_related('doctor', 'paciente').order_by('creada_en', 'pk')

        if options['dry_run']:
            self.stdout.write(
                f"Simulación: se reintentarían {alertas.count()} alerta(s) pendiente(s)."
            )
            return

        procesadas = 0
        for alerta in alertas.iterator():
            enviar_correo_alerta(alerta)
            procesadas += 1
        self.stdout.write(f'Se procesaron {procesadas} alerta(s) pendiente(s).')

    @staticmethod
    def _parse_ahora(valor):
        if not valor:
            return timezone.now()
        try:
            fecha_hora = datetime.strptime(valor, '%Y-%m-%d %H:%M')
        except ValueError as error:
            raise CommandError(
                'El formato de --ahora debe ser AAAA-MM-DD HH:MM.'
            ) from error
        return timezone.make_aware(fecha_hora, timezone.get_default_timezone())
