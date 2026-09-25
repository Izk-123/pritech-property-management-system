"""Schema-aware AdminSite for Pritech PMS.

Inherits from Unfold's admin site so we keep the command palette,
search endpoint, dashboard template, and every other Unfold feature.
On top of that, hides every app that lives only in a tenant schema
when the current request is on the public schema.
"""
from unfold.sites import UnfoldAdminSite


class PritechAdminSite(UnfoldAdminSite):
    """Unfold admin with public-schema app filtering."""

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label=app_label)

        # Lazy imports — this runs per request, after apps are loaded.
        from django.conf import settings
        from django_tenants.utils import get_public_schema_name

        tenant = getattr(request, 'tenant', None)
        is_public = (
            tenant is None
            or tenant.schema_name == get_public_schema_name()
        )
        if not is_public:
            return app_list

        tenant_app_labels = {
            app.rsplit('.', 1)[-1]
            for app in settings.TENANT_APPS
            if app not in settings.SHARED_APPS
        }
        return [
            app for app in app_list
            if app['app_label'] not in tenant_app_labels
        ]