from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    list_display = (
        'email', 'first_name', 'middle_name', 'last_name',
        'is_staff', 'is_platform_admin', 'is_active',
    )
    list_filter = ('is_staff', 'is_superuser', 'is_platform_admin', 'is_active')
    search_fields = (
        'email', 'first_name', 'middle_name', 'last_name', 'phone',
    )
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal', {
            'fields': ('first_name', 'middle_name', 'last_name',
                       'phone'),
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser',
                       'is_platform_admin', 'groups', 'user_permissions'),
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined'),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'first_name', 'last_name',
                       'password1', 'password2', 'is_staff', 'is_platform_admin'),
        }),
    )