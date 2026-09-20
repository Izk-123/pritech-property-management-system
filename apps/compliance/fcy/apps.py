from django.apps import AppConfig


class FCYConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.compliance.fcy'
    label = 'fcy'
    verbose_name = 'Foreign Currency (RBM)'