from django.apps import AppConfig

class HousekeepingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hospitality.housekeeping'
    label = 'housekeeping'

    def ready(self):
        from . import signals  # noqa