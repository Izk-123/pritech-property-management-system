from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import FCYBankAccount, RBMReturn


@admin.register(FCYBankAccount)
class FCYBankAccountAdmin(ModelAdmin):
    list_display = (
        'bank_name', 'account_number', 'currency',
        'property', 'is_active',
    )
    list_filter = ('currency', 'is_active', 'property')


@admin.register(RBMReturn)
class RBMReturnAdmin(ModelAdmin):
    list_display = (
        'property', 'return_month', 'currency',
        'total_receipts', 'net_foreign_currency',
        'submitted_to_rbm',
    )
    list_filter = ('currency', 'submitted_to_rbm', 'return_month')
    list_select_related = ('property',)