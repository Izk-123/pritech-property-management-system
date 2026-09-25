"""
Save this as: apps/core/apps.py

This is the missing wire-up. `django.contrib.admin.site` is a lazy
proxy that instantiates whatever `default_site` the registered
"django.contrib.admin" AppConfig points to. By subclassing AdminConfig
here and swapping the INSTALLED_APPS entry (see settings.py note
below), `admin.site` — and therefore `admin.site.urls` in both
urls.py and urls_public.py — automatically becomes a PritechAdminSite
instance. No changes needed to urls.py itself.

Without this, PritechAdminSite.get_app_list() (tenant-app filtering)
and UNFOLD['DASHBOARD_CALLBACK'] (dashboard_callback) never run —
which is exactly why the app-list page renders as a bare, unstyled
link dump instead of Unfold's card layout.
"""
from django.contrib.admin.apps import AdminConfig


class PritechAdminConfig(AdminConfig):
    default_site = 'apps.core.admin_site.PritechAdminSite'
