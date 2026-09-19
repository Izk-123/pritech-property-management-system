# apps/property/leases/apps.py
from django.apps import AppConfig

class LeasesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.property.leases'
    label = 'leases'