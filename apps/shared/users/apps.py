from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.shared.users'
    label = 'shared_users'

    def ready(self):
        # Register the Chichewa language with Django
        from django.conf.locale import LANG_INFO
        LANG_INFO.setdefault('ny', {
            'bidi': False,
            'code': 'ny',
            'name': 'Chichewa',
            'name_local': 'Chichewa',
        })

        # Register auth event signal handlers (AZ-10)
        from . import signals  # noqa: F401