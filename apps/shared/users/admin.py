"""
Admin configuration for the User model and its siblings.

Three models:

  User                    — global identity, public schema
  UserTenantMembership    — RBAC link between User and Tenant
  AuthAuditLog            — read-only audit trail of auth events

Phase 8:   expanded User fieldsets (personal, address, preferences,
           platform role), read-only AuthAuditLog with superuser-only
           delete.
Phase 9.1: surfaces phone verification state (phone_verified /
           phone_verified_at) so support staff can tell at a glance
           whether a user is cleared to transact.
Phase 9.3: tenant scoping. On a tenant subdomain, UserAdmin and
           UserTenantMembershipAdmin only expose that tenant's members,
           and platform-level fields become read-only.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django_tenants.utils import get_public_schema_name
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.shared.tenants.admin_mixins import (
    PublicSchemaOnlyAdminMixin,
    TenantScopedAdminMixin,
)

from .models import AuthAuditLog, User, UserTenantMembership


def _current_tenant(request):
    """Return the tenant for tenant-subdomain requests, None on public."""
    tenant = getattr(request, 'tenant', None)
    if tenant is None or tenant.schema_name == get_public_schema_name():
        return None
    return tenant


class _TenantScopedUserAdminMixin:
    """
    Scope UserAdmin to members of the current tenant.

    * get_queryset: list/change/delete views and the autocomplete
      endpoint only see active members of this tenant.
    * Platform-level fields (superuser flag, platform role, groups,
      raw permissions, last_tenant) are read-only on tenant
      subdomains. Without this a tenant admin could tick
      "is_superuser" on their own account.
    """
    TENANT_READONLY = (
        'is_superuser', 'is_platform_admin',
        'groups', 'user_permissions', 'last_tenant',
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = _current_tenant(request)
        if tenant is None:
            return qs
        return qs.filter(
            tenant_memberships__tenant=tenant,
            tenant_memberships__is_active=True,
        ).distinct()

    def get_readonly_fields(self, request, obj=None):
        ro = tuple(super().get_readonly_fields(request, obj))
        if _current_tenant(request) is not None:
            ro += tuple(f for f in self.TENANT_READONLY if f not in ro)
        return ro

    def get_autocomplete_fields(self, request):
        # last_tenant autocomplete would hit TenantAdmin, which is
        # public-only and 403s on tenant subdomains.
        if _current_tenant(request) is not None:
            return ()
        return super().get_autocomplete_fields(request)


class _TenantScopedMembershipAdminMixin:
    """Scope UserTenantMembershipAdmin to the current tenant."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = _current_tenant(request)
        if tenant is None:
            return qs
        return qs.filter(tenant=tenant)

    def get_autocomplete_fields(self, request):
        fields = tuple(super().get_autocomplete_fields(request))
        if _current_tenant(request) is not None:
            fields = tuple(f for f in fields if f != 'tenant')
        return fields

    def get_list_filter(self, request):
        filters = tuple(super().get_list_filter(request))
        if _current_tenant(request) is not None:
            # The 'tenant' filter would list every tenant's name.
            filters = tuple(f for f in filters if f != 'tenant')
        return filters

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        tenant = _current_tenant(request)
        if tenant is not None and db_field.name == 'tenant':
            from apps.shared.tenants.models import Tenant
            kwargs['queryset'] = Tenant.objects.filter(pk=tenant.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ─────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────

@admin.register(User)
class UserAdmin(_TenantScopedUserAdminMixin, BaseUserAdmin, ModelAdmin):
    """
    Extends Django's stock UserAdmin with the extra Pritech fields.

    Sections mirror the model's natural groupings so it's obvious
    where a new field should go:

      Personal     — identity, DOB, ID documents
      Contact      — phone numbers + verification state
      Address      — postal address fields
      Preferences  — language + timezone
      Permissions  — Django auth flags + platform role
      Tenant ctx   — last accessed tenant / IP
      Metadata     — timestamps
    """
    list_display = (
        'email', 'full_name_display', 'phone',
        'phone_verified_display',
        'is_staff', 'is_platform_admin', 'is_active',
    )
    list_filter = (
        'is_staff', 'is_superuser', 'is_platform_admin',
        'is_active', 'preferred_language', 'phone_verified',
    )
    search_fields = (
        'email', 'first_name', 'middle_name', 'last_name',
        'phone', 'national_id',
    )
    ordering = ('email',)
    readonly_fields = (
        'last_login', 'date_joined', 'created_at',
        'updated_at', 'last_login_ip',
    )
    autocomplete_fields = ('last_tenant',)

    fieldsets = (
        (None, {
            'fields': ('email', 'username', 'password'),
        }),
        ('Personal', {
            'fields': (
                'first_name', 'middle_name', 'last_name',
                'date_of_birth', 'gender', 'national_id', 'avatar',
            ),
        }),
        ('Contact', {
            'fields': (
                'phone', 'alternate_phone',
                # Phase 9.1 — verification state lives next to the phone
                # it describes so the two aren't separated in the UI.
                'phone_verified', 'phone_verified_at',
            ),
        }),
        ('Address', {
            'fields': (
                'address_line1', 'address_line2',
                'city', 'district', 'country',
            ),
        }),
        ('Preferences', {
            'fields': ('preferred_language', 'timezone'),
        }),
        ('Permissions', {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'is_platform_admin',
                'groups', 'user_permissions',
            ),
        }),
        ('Tenant context', {
            'fields': ('last_tenant', 'last_login_ip'),
        }),
        ('Metadata', {
            'fields': ('last_login', 'date_joined',
                       'created_at', 'updated_at'),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'username',
                'first_name', 'middle_name', 'last_name',
                'password1', 'password2',
                'is_staff', 'is_platform_admin',
            ),
        }),
    )

    @display(description='Name', ordering='last_name')
    def full_name_display(self, obj):
        return obj.full_name

    @display(
        description='Phone verified',
        ordering='phone_verified',
        label={
            True: 'success',
            False: 'warning',
        },
    )
    def phone_verified_display(self, obj):
        return obj.phone_verified


# ─────────────────────────────────────────────────────────────────────
# UserTenantMembership
# ─────────────────────────────────────────────────────────────────────

@admin.register(UserTenantMembership)
class UserTenantMembershipAdmin(
    _TenantScopedMembershipAdminMixin,
    TenantScopedAdminMixin,   # scopes 'user' / 'invited_by' on POST validation too
    ModelAdmin,
):
    """
    The RBAC table. One row per (user, tenant) pair.

    Not a lot of customisation — but autocomplete and list_select_related
    keep the list page fast even with thousands of memberships.
    """
    list_display = (
        'user', 'tenant', 'role', 'is_active',
        'joined_at', 'expires_at',
    )
    list_filter = ('role', 'is_active', 'tenant')
    search_fields = (
        'user__email', 'user__first_name', 'user__last_name',
        'tenant__name', 'tenant__schema_name',
    )
    list_select_related = ('user', 'tenant', 'invited_by')
    autocomplete_fields = ('user', 'tenant', 'invited_by')
    readonly_fields = ('joined_at',)
    date_hierarchy = 'joined_at'


# ─────────────────────────────────────────────────────────────────────
# AuthAuditLog
# ─────────────────────────────────────────────────────────────────────

@admin.register(AuthAuditLog)
class AuthAuditLogAdmin(PublicSchemaOnlyAdminMixin, ModelAdmin):
    """
    Read-only audit trail.

    Write happens from signal handlers in apps/shared/users/signals.py.
    Editing or deleting from admin would undermine the audit guarantee,
    so only superusers can delete (for GDPR / data-subject requests).

    The `details` JSON column is searchable — because Postgres casts
    it to text on icontains — so support staff can hunt for
    "no_membership_for_tenant" or a specific tenant schema.
    """
    list_display = (
        'created_at', 'event_type', 'user_display',
        'tenant', 'ip_address',
    )
    list_filter = ('event_type', 'tenant', 'created_at')
    search_fields = (
        'user__email', 'ip_address',
        'details',
    )
    list_select_related = ('user', 'tenant')
    readonly_fields = (
        'user', 'tenant', 'event_type', 'ip_address',
        'user_agent', 'details', 'created_at',
    )
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        # Audit rows are written by signals, never manually.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete audit logs (data-subject requests).
        # super() keeps the public-schema-only guard in force: this
        # override would otherwise shadow the mixin completely.
        return request.user.is_superuser and super().has_delete_permission(request, obj)

    @display(description='User')
    def user_display(self, obj):
        return obj.user.email if obj.user else '(anonymous)'