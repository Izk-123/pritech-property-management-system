from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import ForexRate, CurrencyLock


@admin.register(ForexRate)
class ForexRateAdmin(ModelAdmin):
    list_display = (
        'quote_currency', 'rate', 'source',
        'effective_from', 'effective_to',
    )
    list_filter = ('quote_currency', 'source')


@admin.register(CurrencyLock)
class CurrencyLockAdmin(ModelAdmin):
    list_display = (
        'from_currency', 'to_currency',
        'locked_rate', 'locked_at',
    )
    list_filter = ('from_currency', 'to_currency')