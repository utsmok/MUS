from django.apps import AppConfig
import os

class XClassRefactorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "xclass_refactor"
    path = os.path.dirname(os.path.abspath(__file__))
