from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import (
    SaleListing, SaleOffer, SaleAgreement,
    SaleInstallment, SaleCommission,
)


class SaleOfferInline(TabularInline):
    model = SaleOffer
    extra = 0
    fields = ('buyer', 'offer_amount', 'status', 'conditions')


class SaleInstallmentInline(TabularInline):
    model = SaleInstallment
    extra = 0
    fields = ('installment_number', 'due_date', 'amount', 'amount_paid', 'is_paid')


class SaleCommissionInline(TabularInline):
    model = SaleCommission
    extra = 0
    fields = ('agent', 'commission_percent', 'commission_amount', 'is_paid')


@admin.register(SaleListing)
class SaleListingAdmin(ModelAdmin):
    list_display = (
        'property', 'unit', 'asking_price', 'currency',
        'status', 'agent', 'listing_date',
    )
    list_filter = ('status', 'currency')
    search_fields = ('property__name', 'description')
    list_select_related = ('property', 'unit', 'agent')
    autocomplete_fields = ('property', 'unit', 'agent')
    inlines = [SaleOfferInline]


@admin.register(SaleOffer)
class SaleOfferAdmin(ModelAdmin):
    list_display = ('buyer', 'listing', 'offer_amount', 'status')
    list_filter = ('status',)
    list_select_related = ('buyer', 'listing')
    autocomplete_fields = ('buyer', 'listing')


@admin.register(SaleAgreement)
class SaleAgreementAdmin(ModelAdmin):
    list_display = (
        'agreement_number', 'buyer', 'sale_price',
        'deposit_paid', 'payment_type', 'completion_date',
    )
    list_filter = ('payment_type', 'currency')
    search_fields = ('agreement_number', 'buyer__full_name')
    list_select_related = ('buyer', 'listing')
    autocomplete_fields = ('buyer', 'seller', 'listing')
    readonly_fields = ('agreement_number',)
    inlines = [SaleInstallmentInline, SaleCommissionInline]