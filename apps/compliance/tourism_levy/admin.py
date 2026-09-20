from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import TourismLevyConfig, TourismLevyRecord


@admin.register(TourismLevyConfig)
class TourismLevyConfigAdmin(ModelAdmin):
    list_display = ('property', 'levy_percent', 'is_active', 'effective_from')
    list_filter = ('is_active',)


@admin.register(TourismLevyRecord)
class TourismLevyRecordAdmin(ModelAdmin):
    list_display = (
        'folio', 'property', 'room_charge_amount',
        'levy_rate', 'levy_amount', 'period_month', 'is_remitted',
    )
    list_filter = ('is_remitted', 'property', 'period_month')
    search_fields = ('folio__reservation__reservation_number',)
    list_select_related = ('folio', 'property')