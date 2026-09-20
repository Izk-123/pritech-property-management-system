from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import PayChanguTransaction


@admin.register(PayChanguTransaction)
class PayChanguTransactionAdmin(ModelAdmin):
    list_display = (
        'charge_id', 'amount', 'currency', 'method',
        'status', 'created_at',
    )
    list_filter = ('status', 'method', 'currency')
    search_fields = ('charge_id', 'ref_id', 'payer_mobile')
    readonly_fields = ('verification_data', 'webhook_received_at', 'verified_at')