# apps/compliance/eis/apps.py
from django.apps import AppConfig


class EISConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.compliance.eis'
    label = 'eis'
    verbose_name = 'MRA EIS'