# apps/core/properties/admin.py
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from apps.shared.tenants.admin_mixins import TenantScopedAdminMixin

from .models import (
    Amenity,
    Property,
    PropertyImage,
    StaffPropertyAssignment,
    Unit,
)


class PropertyImageInline(TabularInline):
    model = PropertyImage
    fk_name = 'property'
    extra = 1
    fields = ('image', 'caption', 'is_cover', 'order')
    ordering = ('order', '-is_cover')


class UnitImageInline(TabularInline):
    model = PropertyImage
    fk_name = 'unit'
    extra = 1
    fields = ('image', 'caption', 'is_cover', 'order')
    ordering = ('order', '-is_cover')


@admin.register(Amenity)
class AmenityAdmin(ModelAdmin):
    list_display = ('name', 'category', 'icon')
    list_filter = ('category',)
    search_fields = ('name',)


@admin.register(Property)
class PropertyAdmin(ModelAdmin):
    list_display = (
        'name', 'property_type', 'district', 'region', 'status', 'is_public',
    )
    list_filter = ('property_type', 'region', 'status', 'is_public')
    search_fields = ('name', 'district', 'address')
    prepopulated_fields = {'public_slug': ('name',)}
    inlines = [PropertyImageInline]
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
        ('Public Listing', {
            'fields': ('is_public', 'public_slug'),
            'description': (
                'Control whether this property appears on the public '
                'listing page. The slug is auto-generated from the name '
                'when left blank.'
            ),
        }),
    )


@admin.register(Unit)
class UnitAdmin(ModelAdmin):
    list_display = (
        'identifier', 'property', 'unit_type', 'capacity_adults',
        'base_rate_mwk', 'status', 'is_public',
    )
    list_filter = ('unit_type', 'status', 'property', 'is_public')
    search_fields = ('identifier', 'property__name')
    list_select_related = ('property',)
    filter_horizontal = ('amenities',)
    autocomplete_fields = ('property',)
    inlines = [UnitImageInline]
    fieldsets = (
        ('Identity', {
            'fields': ('property', 'unit_type', 'identifier', 'floor'),
        }),
        ('Capacity', {
            'fields': ('capacity_adults', 'capacity_children', 'bed_count'),
        }),
        ('Pricing', {
            'fields': ('base_rate_mwk', 'base_rate_usd'),
        }),
        ('Amenities', {
            'fields': ('amenities',),
        }),
        ('Status', {
            'fields': ('status', 'is_active', 'is_public'),
        }),
    )


@admin.register(StaffPropertyAssignment)
class StaffPropertyAssignmentAdmin(TenantScopedAdminMixin, ModelAdmin):
    list_display = ('user', 'property', 'is_active', 'assigned_at')
    list_filter = ('is_active', 'property')
    search_fields = ('user__email', 'property__name')
    list_select_related = ('user', 'property', 'assigned_by')
    autocomplete_fields = ('user', 'property', 'assigned_by')
    readonly_fields = ('assigned_at',)


@admin.register(PropertyImage)
class PropertyImageAdmin(ModelAdmin):
    list_display = (
        '__str__', 'property', 'unit', 'is_cover', 'order', 'created_at',
    )
    list_filter = ('is_cover',)
    search_fields = ('caption', 'property__name', 'unit__identifier')
    list_select_related = ('property', 'unit')
    autocomplete_fields = ('property', 'unit')
    readonly_fields = ('created_at', 'updated_at')