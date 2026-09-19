from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Lease, LeaseUnit


@admin.register(Lease)
class LeaseAdmin(ModelAdmin):
    list_display = (
        'lease_number', 'tenant', 'unit', 'status',
        'start_date', 'end_date', 'rent_amount',
    )
    list_filter = ('status', 'payment_frequency', 'rent_currency')
    search_fields = (
        'lease_number', 'tenant__full_name',
        'unit__identifier', 'unit__property__name',
    )
    list_select_related = ('tenant', 'unit', 'unit__property')
    autocomplete_fields = ('tenant', 'unit', 'landlord')
    readonly_fields = ('lease_number',)
    date_hierarchy = 'start_date'
    fieldsets = (
        ('Identity', {
            'fields': ('lease_number', 'status', 'tenant', 'unit', 'landlord'),
        }),
        ('Term', {
            'fields': ('start_date', 'end_date', 'rent_free_until'),
        }),
        ('Rent', {
            'fields': (
                'rent_amount', 'rent_currency', 'payment_frequency',
                'payment_due_day', 'escalation_percent',
            ),
        }),
        ('Deposit', {
            'fields': (
                'deposit_amount', 'deposit_received',
                'deposit_refunded', 'deposit_deductions',
            ),
        }),
        ('Late Fees', {
            'fields': ('grace_period_days', 'late_fee_percent', 'late_fee_fixed'),
        }),
        ('Renewal', {
            'fields': ('auto_renew', 'renewal_notice_days'),
        }),
        ('Documents', {
            'fields': ('document',),
        }),
    )


@admin.register(LeaseUnit)
class LeaseUnitAdmin(ModelAdmin):
    list_display = ('lease', 'unit', 'rent_share')
    list_select_related = ('lease', 'unit')
    autocomplete_fields = ('lease', 'unit')