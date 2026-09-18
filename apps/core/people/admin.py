from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Person, PersonPropertyRole


@admin.register(Person)
class PersonAdmin(ModelAdmin):
    list_display = ('full_name', 'phone_primary', 'email', 'nationality',
                    'is_blacklisted')
    list_filter = ('nationality', 'preferred_language', 'is_blacklisted')
    search_fields = ('full_name', 'phone_primary', 'id_number', 'email')
    fieldsets = (
        ('Identity', {
            'fields': ('full_name', 'id_type', 'id_number',
                       'date_of_birth', 'nationality'),
        }),
        ('Contact', {
            'fields': ('phone_primary', 'phone_secondary', 'email',
                       'address', 'district'),
        }),
        ('Preferences', {
            'fields': ('preferred_language',),
        }),
        ('Risk', {
            'fields': ('is_blacklisted', 'blacklist_reason'),
        }),
    )


@admin.register(PersonPropertyRole)
class PersonPropertyRoleAdmin(ModelAdmin):
    list_display = ('person', 'property', 'role', 'is_active',
                    'start_date', 'end_date')
    list_filter = ('role', 'is_active')
    search_fields = ('person__full_name', 'property__name')
    list_select_related = ('person', 'property')
    autocomplete_fields = ('person', 'property')