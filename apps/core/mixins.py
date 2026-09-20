"""
Shared mixins for views across the Pritech PMS platform.

These mixins handle:
- Tenant schema awareness (public vs tenant)
- Platform admin access control
- Staff access control
- Property-level scoping for multi-property tenants
"""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


# ─────────────────────────────────────────────────────────────────────
# Tenant awareness
# ─────────────────────────────────────────────────────────────────────

class TenantContextMixin:
    """
    Adds tenant context to the view.

    django-tenants sets `request.tenant` automatically. This mixin
    exposes it via `self.tenant` and adds helper flags to the context.
    """

    def get_tenant(self):
        return getattr(self.request, 'tenant', None)

    def is_public_schema(self):
        tenant = self.get_tenant()
        return not tenant or tenant.schema_name == 'public'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.get_tenant()
        ctx['tenant'] = tenant
        ctx['is_public_schema'] = self.is_public_schema()
        return ctx


class PublicSchemaOnlyMixin(TenantContextMixin, UserPassesTestMixin):
    """
    Restrict view to the public schema only.
    Useful for signup, tenant management, and marketing pages.
    """

    def test_func(self):
        if not self.is_public_schema():
            return False
        return super().test_func() if hasattr(super(), 'test_func') else True

    def handle_no_permission(self):
        if self.request.user.is_authenticated and not self.is_public_schema():
            # Redirect tenant users to their dashboard
            from django.shortcuts import redirect
            return redirect('home')
        return super().handle_no_permission()


class TenantSchemaOnlyMixin(TenantContextMixin):
    """
    Restrict view to tenant schemas (not public).
    """

    def dispatch(self, request, *args, **kwargs):
        if self.is_public_schema():
            raise PermissionDenied(
                'This view is only available within a tenant workspace.'
            )
        return super().dispatch(request, *args, **kwargs)


# ─────────────────────────────────────────────────────────────────────
# Access control
# ─────────────────────────────────────────────────────────────────────

class PlatformAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Only platform admins (users with `is_platform_admin=True` or superusers)
    can access this view. Used for tenant management.
    """

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (
            user.is_platform_admin or user.is_superuser
        )

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(
                'You do not have permission to access the platform admin.'
            )
        return super().handle_no_permission()


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Only staff users can access this view.
    Staff = users with `is_staff=True`.
    """

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(
                'Staff access required. Contact your administrator.'
            )
        return super().handle_no_permission()


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Only superusers can access this view.
    """

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser


# ─────────────────────────────────────────────────────────────────────
# QuerySet scoping
# ─────────────────────────────────────────────────────────────────────

class TenantScopedQuerySetMixin:
    """
    With schema-based multi-tenancy, `django-tenants` already isolates
    data at the PostgreSQL `search_path` level. This mixin is provided
    for future use — e.g., if you ever need to query across tenants
    from the public schema using `.schema()` or `schema_context()`.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        # In schema isolation, the search_path already restricts
        # the queryset to the current tenant. No extra filtering needed.
        return qs


class PropertyScopedQuerySetMixin:
    """
    Filter querysets by the user's assigned properties.

    A staff member assigned to one property should not see data
    from another property within the same tenant.

    Relies on a `StaffPropertyAssignment` model (to be added when
    you need per-property scoping). If no assignments exist for the
    user, they see all properties.
    """

    def get_assigned_property_ids(self):
        user = self.request.user
        if not user.is_authenticated:
            return []
        # If the user is a superuser or platform admin, no scoping
        if user.is_superuser or user.is_platform_admin:
            return None  # None means "no filter"

        # Try to load staff assignments if the model exists
        try:
            from apps.core.properties.models import StaffPropertyAssignment
        except ImportError:
            return None  # No model → no scoping

        return list(
            StaffPropertyAssignment.objects.filter(
                user=user, is_active=True,
            ).values_list('property_id', flat=True)
        )

    def get_queryset(self):
        qs = super().get_queryset()
        assigned = self.get_assigned_property_ids()

        if assigned is None:
            return qs  # No scoping applied

        if not assigned:
            # Staff with no assignments → see nothing
            return qs.none()

        # Apply filter based on the model's property field
        if hasattr(qs.model, 'property'):
            return qs.filter(property_id__in=assigned)
        if hasattr(qs.model, 'unit'):
            return qs.filter(unit__property_id__in=assigned)
        if hasattr(qs.model, 'reservation'):
            return qs.filter(reservation__property_id__in=assigned)

        return qs