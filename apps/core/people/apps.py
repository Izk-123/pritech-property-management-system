from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core.people'
    label = 'people'
    verbose_name = 'People'