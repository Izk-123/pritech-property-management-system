"""
Admin configuration for Tenant and Domain.

Phase 8:   added a Localization fieldset for default_language.
Phase 9.1: added a Modules fieldset for the JSONField that records
           which business modules a tenant uses (Hospitality,
           Property Sales, Property Rentals).

The Tenant change form is where an operator will spend time when
provisioning or adjusting a workspace, so the fieldsets are ordered
by what matters most: identity → status → contact → modules →
localization → metadata.
"""
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import Domain, Tenant
from .admin_mixins import PublicSchemaOnlyAdminMixin


@admin.register(Tenant)
class TenantAdmin(PublicSchemaOnlyAdminMixin, ModelAdmin):
    """
    Tenant administration.

    Fieldsets map onto the model's own sections and the Phase 8/9.1
    additions. `modules` and `default_language` are the two fields
    that affect tenant-visible behavior; everything else is metadata.
    """
    list_display = (
        'name', 'schema_name', 'plan', 'is_active',
        'on_trial', 'paid_until',
        'modules_display',
        'default_language',
        'created_at',
    )
    list_filter = (
        'plan', 'is_active', 'on_trial', 'default_language',
    )
    search_fields = (
        'name', 'schema_name', 'contact_email', 'contact_name',
    )
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Identity', {
            'fields': ('name', 'schema_name', 'plan'),
        }),
        ('Status', {
            'fields': ('is_active', 'on_trial', 'paid_until'),
        }),
        ('Contact', {
            'fields': ('contact_name', 'contact_email', 'contact_phone'),
        }),

        # Phase 9.1 — which business modules the tenant uses. Drives
        # conditional navigation in the tenant header and (later)
        # feature gating. Multi-select in the admin.
        ('Modules', {
            'fields': ('modules',),
            'description': (
                'Select the business modules this tenant uses. '
                'Controls which sections appear in the tenant '
                'navigation and which features are enabled. '
                'A hotel typically picks Hospitality only; a '
                'landlord picks one or both Property modules.'
            ),
        }),

        # Phase 8 — per-tenant default UI language
        ('Localization', {
            'fields': ('default_language',),
            'description': (
                'Default UI language for this tenant. Staff can still '
                'switch per-session using the language switcher in the header.'
            ),
        }),

        ('Metadata', {
            'fields': ('created_at',),
        }),
    )

    @display(description='Modules')
    def modules_display(self, obj):
        """
        Render the JSON list of enabled modules as a compact,
        human-readable string. Long lists are truncated so the
        list page stays scannable.

        Empty list → em-dash so the column doesn't look blank.
        """
        modules = obj.modules or []
        if not modules:
            return '—'

        # Get the human-readable labels from the TextChoices
        label_map = dict(Tenant.Module.choices)
        labels = [label_map.get(m, m) for m in modules]
        joined = ', '.join(labels)

        # Truncate for the list page; the change form shows everything.
        return joined if len(joined) <= 60 else joined[:57] + '…'


# ─────────────────────────────────────────────────────────────────────
# Domain
# ─────────────────────────────────────────────────────────────────────

@admin.register(Domain)
class DomainAdmin(PublicSchemaOnlyAdminMixin, ModelAdmin):
    """
    Hostname → Tenant mapping.

    This is the routing table that django-tenants consults on every
    request. Add a Domain row per subdomain you want to serve.
    """
    list_display = ('domain', 'tenant', 'is_primary')
    list_filter = ('is_primary',)
    search_fields = ('domain', 'tenant__name', 'tenant__schema_name')
    list_select_related = ('tenant',)
    autocomplete_fields = ('tenant',)