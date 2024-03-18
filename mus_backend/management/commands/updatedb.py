from django.core.management.base import BaseCommand
from mus_backend.update_all import update_all

class Command(BaseCommand):
    help = 'Update MUS DB by first filling MongoDB from APIS and then processing into postgresql'

    def handle(self, *args, **kwargs):
        print('running the command!')
        update_all()