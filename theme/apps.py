from django.apps import AppConfig


class ThemeConfig(AppConfig):
    name = 'theme'
    
    def ready(self):
            from django.conf import settings
            if not hasattr(settings, 'TAILWIND_USE_STANDALONE_BINARY'):
                settings.TAILWIND_USE_STANDALONE_BINARY = True