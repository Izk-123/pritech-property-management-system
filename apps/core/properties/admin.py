from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from .models import Amenity, Property, Unit


@admin.register(Amenity)
class AmenityAdmin(ModelAdmin):
    list_display = ('name', 'category', 'icon')
    list_filter = ('category',)
    search_fields = ('name',)


@admin.register(Property)
class PropertyAdmin(ModelAdmin):
    list_display = ('name', 'property_type', 'district', 'region', 'status')
    list_filter = ('property_type', 'region', 'status')
    search_fields = ('name', 'district', 'address')
    prepopulated_fields = {}  # No slugs yet
    fieldsets = (
        ('Identity', {
            'fields': ('name', 'property_type', 'status'),
        }),
        ('Location', {
            'fields': ('address', 'district', 'region',
                       'gps_latitude', 'gps_longitude'),
        }),
        ('Contact', {
            'fields': ('phone', 'email'),
        }),
        ('Details', {
            'fields': ('description',),
        }),
    )


@admin.register(Unit)
class UnitAdmin(ModelAdmin):
    list_display = (
        'identifier', 'property', 'unit_type', 'capacity_adults',
        'base_rate_mwk', 'status',
    )
    list_filter = ('unit_type', 'status', 'property')
    search_fields = ('identifier', 'property__name')
    list_select_related = ('property',)
    filter_horizontal = ('amenities',)
    autocomplete_fields = ('property',)