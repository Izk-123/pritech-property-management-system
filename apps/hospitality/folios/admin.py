from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Folio, FolioCharge, FolioPayment


class FolioChargeInline(admin.TabularInline):
    model = FolioCharge
    extra = 0
    readonly_fields = ('created_at',)


class FolioPaymentInline(admin.TabularInline):
    model = FolioPayment
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Folio)
class FolioAdmin(ModelAdmin):
    list_display = ('reservation', 'status', 'currency', 'settled_at')
    list_filter = ('status', 'currency')
    search_fields = (
        'reservation__reservation_number',
        'reservation__primary_guest__full_name',
    )
    list_select_related = ('reservation', 'reservation__primary_guest')
    readonly_fields = ('settled_at',)
    inlines = [FolioChargeInline, FolioPaymentInline]


@admin.register(FolioCharge)
class FolioChargeAdmin(ModelAdmin):
    list_display = ('folio', 'charge_type', 'amount', 'currency', 'created_at')
    list_filter = ('charge_type', 'currency')
    search_fields = ('description', 'folio__reservation__reservation_number')
    list_select_related = ('folio',)
    autocomplete_fields = ('folio', 'posted_by')


@admin.register(FolioPayment)
class FolioPaymentAdmin(ModelAdmin):
    list_display = ('folio', 'method', 'amount', 'currency', 'reference', 'created_at')
    list_filter = ('method', 'currency')
    search_fields = ('reference', 'folio__reservation__reservation_number')
    list_select_related = ('folio',)
    autocomplete_fields = ('folio', 'received_by')