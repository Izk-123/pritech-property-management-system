from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Subscription, SubscriptionChange, SubscriptionInvoice,
    SubscriptionPayment, SubscriptionPlan,
)


class InvoiceInline(TabularInline):
    model = SubscriptionInvoice
    extra = 0
    fields = ('invoice_number', 'period_start', 'period_end',
              'amount', 'currency', 'status')
    readonly_fields = ('invoice_number',)


class ChangeInline(TabularInline):
    model = SubscriptionChange
    extra = 0
    fields = ('kind', 'from_plan', 'to_plan', 'note', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(ModelAdmin):
    list_display = ('name', 'tier', 'interval', 'price_mwk',
                    'max_properties', 'max_units', 'is_active')
    list_filter = ('tier', 'interval', 'is_active', 'is_public')
    ordering = ('display_order', 'price_mwk')


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ('tenant', 'plan', 'status',
                    'current_period_end', 'trial_ends_at')
    list_filter = ('status', 'plan')
    search_fields = ('tenant__name', 'tenant__schema_name')
    readonly_fields = ('created_at', 'updated_at', 'last_payment_at')
    inlines = [InvoiceInline, ChangeInline]


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(ModelAdmin):
    list_display = ('invoice_number', 'tenant', 'amount', 'currency',
                    'due_date', 'status')
    list_filter = ('status', 'currency')
    search_fields = ('invoice_number', 'tenant__name')
    readonly_fields = ('invoice_number',)


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(ModelAdmin):
    list_display = ('invoice', 'amount', 'currency', 'method', 'received_at')
    list_filter = ('method', 'currency')


@admin.register(SubscriptionChange)
class SubscriptionChangeAdmin(ModelAdmin):
    list_display = ('subscription', 'kind', 'from_plan', 'to_plan', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('created_at',)