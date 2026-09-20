from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import EISTerminal, EISInvoiceLog, EISProductMapping


@admin.register(EISTerminal)
class EISTerminalAdmin(ModelAdmin):
    list_display = (
        'terminal_code', 'property', 'tin', 'status',
        'last_config_sync', 'activated_at',
    )
    list_filter = ('status', 'property')
    search_fields = ('terminal_code', 'tin', 'trading_name')
    list_select_related = ('property',)
    readonly_fields = ('last_config_sync', 'activated_at')


@admin.register(EISInvoiceLog)
class EISInvoiceLogAdmin(ModelAdmin):
    list_display = (
        'invoice_number', 'terminal', 'submission_status',
        'mra_invoice_number', 'retry_count', 'created_at',
    )
    list_filter = ('submission_status', 'terminal')
    search_fields = ('invoice_number', 'mra_invoice_number')
    list_select_related = ('terminal',)
    readonly_fields = (
        'mra_invoice_number', 'mra_validation_url',
        'mra_qr_signature', 'synced_at',
    )


@admin.register(EISProductMapping)
class EISProductMappingAdmin(ModelAdmin):
    list_display = (
        'internal_code', 'description', 'mra_product_code',
        'is_approved', 'property',
    )
    list_filter = ('is_approved', 'property')
    search_fields = ('internal_code', 'description', 'mra_product_code')