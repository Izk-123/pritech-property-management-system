from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core.sync'
    label = 'sync'
    verbose_name = 'Offline Sync'

    def ready(self):
        from . import handlers  # noqa: F401