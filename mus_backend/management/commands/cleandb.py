from django.core.management.base import BaseCommand
from mus_backend.update_all import clean_all

class Command(BaseCommand):
    help = 'clean MUS DB -- removes duplicates from mongodb'

    def handle(self, *args, **kwargs):
        print('running the command!')
        clean_all()