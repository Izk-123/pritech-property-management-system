from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    list_display = ('email', 'first_name', 'middle_name', 'last_name', 'is_staff', 'is_platform_admin')
    search_fields = ('email', 'first_name', 'middle_name', 'last_name')
    ordering = ('email',)