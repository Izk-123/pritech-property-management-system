from django.apps import AppConfig


class PropertiesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core.properties'
    label = 'properties'
    verbose_name = 'Properties & Units'