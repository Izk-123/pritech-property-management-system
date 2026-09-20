from django.apps import AppConfig


class ForexConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.compliance.forex'
    label = 'forex'
    verbose_name = 'Foreign Exchange'