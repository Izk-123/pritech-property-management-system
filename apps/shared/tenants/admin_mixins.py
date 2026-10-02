"""
Admin mixins that enforce tenant / platform boundaries.

Two problems this file solves:

1. Every model in SHARED_APPS lives in the `public` schema — one table
   visible to every tenant request. Django admin's permission system
   currently protects them, but only because the tenant-admin role
   happens to lack those permissions. Any bulk permission grant, any
   new shared app, any superuser flag accidentally applied to a tenant
   admin would break that. PublicSchemaOnlyAdminMixin makes the rule
   explicit: these admins 403 on every tenant subdomain.

2. Tenant-schema models with FK(shared_users.User) render dropdowns
   from User.objects.all() — every user in the database, regardless
   of which tenant they belong to. TenantScopedAdminMixin rewrites the
   queryset for those FKs to only the current tenant's active members.

Both mixins work on top of any ModelAdmin subclass, including
django-unfold.admin.ModelAdmin and third-party admins like
auditlog.LogEntryAdmin.
"""
from django_tenants.utils import get_public_schema_name


# ─────────────────────────────────────────────────────────────────────
# Public-schema-only admins
# ─────────────────────────────────────────────────────────────────────

class PublicSchemaOnlyAdminMixin:
    """
    Refuse every admin action unless the request is on the public schema.

    Apply as the FIRST base class of any ModelAdmin whose model lives in
    SHARED_APPS (Tenant, Domain, User, UserTenantMembership, AuthAuditLog,
    auditlog.LogEntry, celery beat/results, axes, sites, ...).

    Effects:
      • The app disappears entirely from the tenant admin index.
      • Direct URL hits return 403.
      • The admin still works fully on the public schema (pms.pritechmw.com).
    """

    def _on_public_schema(self, request):
        tenant = getattr(request, 'tenant', None)
        return (
            tenant is None
            or tenant.schema_name == get_public_schema_name()
        )

    def has_module_permission(self, request):
        return self._on_public_schema(request) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self._on_public_schema(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self._on_public_schema(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self._on_public_schema(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self._on_public_schema(request) and super().has_delete_permission(request, obj)


# ─────────────────────────────────────────────────────────────────────
# Tenant-scoped admins (for models with FK to User)
# ─────────────────────────────────────────────────────────────────────

class TenantScopedAdminMixin:
    """
    Scope every FK-to-User form field to the current tenant's members.

    Apply as the FIRST base class of any ModelAdmin whose model has one
    or more ForeignKey(shared_users.User) fields — see the diagnostic
    output for the full list.

    On the public schema, no scoping is applied (superusers managing the
    platform see everything). On a tenant subdomain, dropdowns show only
    that tenant's active UserTenantMembership users.

    Covers:
      • ModelAdmin form dropdowns (formfield_for_foreignkey)
      • Inlines (same hook, called per-formfield)
      • M2M fields pointing at User (formfield_for_manytomany)

    Does NOT cover autocomplete widgets — those use the related admin's
    get_queryset(), which the scoped UserAdmin in apps/shared/users/admin.py
    handles separately.
    """

    def _tenant(self, request):
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant.schema_name == get_public_schema_name():
            return None
        return tenant

    def _scoped_users(self, tenant):
        from apps.shared.users.models import User
        return User.objects.filter(
            tenant_memberships__tenant=tenant,
            tenant_memberships__is_active=True,
        ).distinct()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        tenant = self._tenant(request)
        if tenant is not None:
            related = getattr(db_field, 'related_model', None)
            if related is not None and related._meta.label == 'shared_users.User':
                kwargs['queryset'] = self._scoped_users(tenant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        tenant = self._tenant(request)
        if tenant is not None:
            related = getattr(db_field, 'related_model', None)
            if related is not None and related._meta.label == 'shared_users.User':
                kwargs['queryset'] = self._scoped_users(tenant)
        return super().formfield_for_manytomany(db_field, request, **kwargs)