from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Tenant, Domain


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    list_display = (
        'name', 'schema_name', 'plan', 'is_active',
        'on_trial', 'paid_until', 'default_language', 'created_at',
    )
    list_filter = ('plan', 'is_active', 'on_trial', 'default_language')
    search_fields = ('name', 'schema_name', 'contact_email', 'contact_name')
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


@admin.register(Domain)
class DomainAdmin(ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
    list_filter = ('is_primary',)
    search_fields = ('domain', 'tenant__name', 'tenant__schema_name')
    list_select_related = ('tenant',)
    autocomplete_fields = ('tenant',)