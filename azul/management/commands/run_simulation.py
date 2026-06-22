from django.core.management.base import BaseCommand

from azul.sim_runner import run_simulation


class Command(BaseCommand):
    help = 'Run a bot-vs-bot simulation'

    def add_arguments(self, parser):
        parser.add_argument('sim_id', type=int, help='Simulation ID')

    def handle(self, *args, **options):
        sim_id = options['sim_id']
        self.stdout.write('Running simulation %d...' % sim_id)
        run_simulation(sim_id)
        self.stdout.write(self.style.SUCCESS('Done'))
