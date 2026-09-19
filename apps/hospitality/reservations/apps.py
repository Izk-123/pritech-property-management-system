from django.apps import AppConfig

class ReservationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hospitality.reservations'
    label = 'reservations'

    def ready(self):
        from . import signals  # noqa