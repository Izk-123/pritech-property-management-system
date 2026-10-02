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


class PublicSchemaOnlyMixin(TenantContextMixin):
    """
    Restrict view to the public schema only.
    Useful for signup, tenant management, and marketing pages.

    Uses dispatch() rather than UserPassesTestMixin so it composes safely
    with other access mixins (LoginRequiredMixin, PlatformAdminRequiredMixin).
    Tenant-schema users hitting a public-only page get redirected home;
    anonymous users get redirected to login.
    """

    def dispatch(self, request, *args, **kwargs):
        if not self.is_public_schema():
            from django.shortcuts import redirect
            if request.user.is_authenticated:
                return redirect('home')
            return redirect('login')
        return super().dispatch(request, *args, **kwargs)


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

# ─────────────────────────────────────────────────────────────────────
# Phase 10 — Subscription enforcement
# ─────────────────────────────────────────────────────────────────────

class SubscriptionRequiredMixin:
    """
    Redirect suspended or cancelled tenants to the billing page.
    Applied to every authenticated view.

    Also updates request.tenant.subscription if it exists so downstream
    code doesn't hit the DB again.
    """

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, 'user', None)
        tenant = getattr(request, 'tenant', None)

        # Public schema or anonymous users — no subscription to check
        if not tenant or tenant.schema_name == 'public':
            return super().dispatch(request, *args, **kwargs)

        # Platform admins bypass
        if user and user.is_authenticated and (
            user.is_platform_admin or user.is_superuser
        ):
            return super().dispatch(request, *args, **kwargs)

        subscription = getattr(tenant, 'subscription', None)
        if subscription is None:
            # Tenant has no subscription row — treat as free trial fallback
            return super().dispatch(request, *args, **kwargs)

        # Compute the current access state once
        request.subscription = subscription
        request.subscription_state = _subscription_banner_state(subscription)

        # Suspended → send to billing
        if subscription.is_suspended:
            from django.shortcuts import redirect
            return redirect('billing:dashboard')

        return super().dispatch(request, *args, **kwargs)


class TenantStaffRequiredMixin(SubscriptionRequiredMixin, StaffRequiredMixin):
    """Staff-only view that also enforces an active subscription."""


def _subscription_banner_state(subscription):
    """
    Return a dict describing what banner (if any) the UI should show.
    """
    if subscription.status == subscription.Status.TRIAL:
        days = subscription.trial_days_remaining
        return {
            'kind': 'trial',
            'days_remaining': days,
            'message': (
                f'Free trial · {days} day{"s" if days != 1 else ""} remaining'
            ),
            'show': True,
        }
    if subscription.status == subscription.Status.PAST_DUE:
        return {
            'kind': 'past_due',
            'days_remaining': 0,
            'message': 'Payment overdue — please pay to avoid suspension.',
            'show': True,
        }
    if 0 < subscription.days_until_period_end <= 7:
        return {
            'kind': 'renewal',
            'days_remaining': subscription.days_until_period_end,
            'message': (
                f'Subscription renews in '
                f'{subscription.days_until_period_end} day'
                f'{"s" if subscription.days_until_period_end != 1 else ""}'
            ),
            'show': True,
        }
    return {'show': False}