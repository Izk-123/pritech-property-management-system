from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.realtime'
    label = 'realtime'
    verbose_name = 'Real-Time'

    def ready(self):
        # Register signal handlers that broadcast model changes
        # to WebSocket groups.
        from . import signals  # noqa: F401