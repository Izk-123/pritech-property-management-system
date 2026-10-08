from django.apps import AppConfig


class GuestPortalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hospitality.guest_portal'
    label = 'guest_portal'
    verbose_name = 'Guest Portal'
