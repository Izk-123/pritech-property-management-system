from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.shared.users'
    label = 'shared_users'
    
    def ready(self):
        # Teach Django about language codes it doesn't ship with.
        # Must run before any template calls get_language_info_list.
        from django.conf.locale import LANG_INFO

        LANG_INFO.setdefault('ny', {
            'bidi': False,
            'code': 'ny',
            'name': 'Chichewa',
            'name_local': 'Chichewa',
        })