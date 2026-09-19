from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Reservation, ReservationRoom


@admin.register(Reservation)
class ReservationAdmin(ModelAdmin):
    list_display = (
        'reservation_number', 'primary_guest', 'property',
        'check_in', 'check_out', 'status',
    )
    list_filter = ('status', 'source', 'property')
    search_fields = (
        'reservation_number', 'primary_guest__full_name',
        'primary_guest__phone_primary',
    )
    list_select_related = ('primary_guest', 'property')
    autocomplete_fields = ('primary_guest', 'property', 'rate_plan')
    readonly_fields = ('reservation_number',)
    date_hierarchy = 'check_in'


@admin.register(ReservationRoom)
class ReservationRoomAdmin(ModelAdmin):
    list_display = ('reservation', 'unit', 'rate_per_night', 'rate_currency')
    list_select_related = ('reservation', 'unit')
    autocomplete_fields = ('reservation', 'unit')