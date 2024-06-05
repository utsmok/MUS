import os

from django.apps import AppConfig


class MUSWizard(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mus_wizard"
    path = os.path.dirname(os.path.abspath(__file__))
