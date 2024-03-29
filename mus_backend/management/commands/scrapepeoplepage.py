from django.core.management.base import BaseCommand
from mus_backend.update_all import update_people_page_data
from loguru import logger

class Command(BaseCommand):
    help = 'scrape people.utwente.nl for author data'

    def handle(self, *args, **kwargs):
        logger.info('running command: update_people_page_data()')
        update_people_page_data()