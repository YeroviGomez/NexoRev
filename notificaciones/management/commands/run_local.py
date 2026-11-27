import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


JOBS = {
    'enviar_recordatorios': 5 * 60,
    'reintentar_alertas_pendientes': 5 * 60,
    'enviar_resumenes_semanales': 60 * 60,
}


class Command(BaseCommand):
    help = 'Inicia el servidor local de Nexo y sus tareas periódicas de notificación.'

    def add_arguments(self, parser):
        parser.add_argument(
            'addrport',
            nargs='?',
            default='127.0.0.1:8000',
            help='Dirección y puerto del servidor, como en runserver.',
        )

    def handle(self, *args, **options):
        manage_py = Path(settings.BASE_DIR) / 'manage.py'
        server_command = [
            sys.executable,
            str(manage_py),
            'runserver',
            '--noreload',
            options['addrport'],
        ]
        try:
            server = subprocess.Popen(server_command, cwd=settings.BASE_DIR)
        except OSError as error:
            raise CommandError('No se pudo iniciar el servidor local de Django.') from error

        try:
            time.sleep(1)
            exit_code = server.poll()
            if exit_code is not None:
                raise CommandError(
                    f'El servidor local terminó al iniciar con código {exit_code}.'
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Nexo está disponible en http://{options["addrport"]}/'
                )
            )
            self.stdout.write('Presiona Ctrl+C para detener el servidor y las tareas.')
            self._run_jobs(server)
        except KeyboardInterrupt:
            self.stdout.write('\nDeteniendo Nexo...')
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()

    def _run_jobs(self, server):
        next_runs = {name: 0 for name in JOBS}
        while server.poll() is None:
            now = time.monotonic()
            for name, interval in JOBS.items():
                if server.poll() is not None:
                    break
                if now >= next_runs[name]:
                    call_command(name)
                    next_runs[name] = time.monotonic() + interval

            if server.poll() is not None:
                break

            next_run = min(next_runs.values())
            wait_seconds = min(max(next_run - time.monotonic(), 0), 1)
            time.sleep(wait_seconds)
