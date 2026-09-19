from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import RatePlan, PricingSeason


@admin.register(RatePlan)
class RatePlanAdmin(ModelAdmin):
    list_display = (
        'name', 'property', 'policy', 'deposit_percentage',
        'cancellation_hours', 'is_active',
    )
    list_filter = ('policy', 'is_active', 'property')
    search_fields = ('name', 'property__name')
    list_select_related = ('property',)
    autocomplete_fields = ('property',)


@admin.register(PricingSeason)
class PricingSeasonAdmin(ModelAdmin):
    list_display = (
        'name', 'property', 'start_date', 'end_date',
        'multiplier', 'fixed_rate_mwk',
    )
    list_filter = ('property',)
    search_fields = ('name', 'property__name')
    list_select_related = ('property',)
    autocomplete_fields = ('property',)
    date_hierarchy = 'start_date'