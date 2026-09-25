from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import AuthAuditLog, User, UserTenantMembership


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    list_display = (
        'email', 'full_name_display', 'phone',
        'is_staff', 'is_platform_admin', 'is_active',
    )
    list_filter = (
        'is_staff', 'is_superuser', 'is_platform_admin',
        'is_active', 'preferred_language',
    )
    search_fields = (
        'email', 'first_name', 'middle_name', 'last_name',
        'phone', 'national_id',
    )
    ordering = ('email',)
    readonly_fields = ('last_login', 'date_joined', 'created_at',
                       'updated_at', 'last_login_ip')
    autocomplete_fields = ('last_tenant',)

    fieldsets = (
        (None, {
            'fields': ('email', 'username', 'password'),
        }),
        ('Personal', {
            'fields': (
                'first_name', 'middle_name', 'last_name',
                'date_of_birth', 'gender', 'national_id', 'avatar',
            ),
        }),
        ('Contact', {
            'fields': (
                'phone', 'alternate_phone',
            ),
        }),
        ('Address', {
            'fields': (
                'address_line1', 'address_line2',
                'city', 'district', 'country',
            ),
        }),
        ('Preferences', {
            'fields': ('preferred_language', 'timezone'),
        }),
        ('Permissions', {
            'fields': (
                'is_active', 'is_staff', 'is_superuser',
                'is_platform_admin',
                'groups', 'user_permissions',
            ),
        }),
        ('Tenant context', {
            'fields': ('last_tenant', 'last_login_ip'),
        }),
        ('Metadata', {
            'fields': ('last_login', 'date_joined',
                       'created_at', 'updated_at'),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'username',
                'first_name', 'middle_name', 'last_name',
                'password1', 'password2',
                'is_staff', 'is_platform_admin',
            ),
        }),
    )

    @display(description='Name', ordering='last_name')
    def full_name_display(self, obj):
        return obj.full_name


@admin.register(UserTenantMembership)
class UserTenantMembershipAdmin(ModelAdmin):
    list_display = (
        'user', 'tenant', 'role', 'is_active',
        'joined_at', 'expires_at',
    )
    list_filter = ('role', 'is_active', 'tenant')
    search_fields = (
        'user__email', 'user__first_name', 'user__last_name',
        'tenant__name', 'tenant__schema_name',
    )
    list_select_related = ('user', 'tenant', 'invited_by')
    autocomplete_fields = ('user', 'tenant', 'invited_by')
    readonly_fields = ('joined_at',)
    date_hierarchy = 'joined_at'


@admin.register(AuthAuditLog)
class AuthAuditLogAdmin(ModelAdmin):
    list_display = (
        'created_at', 'event_type', 'user_display',
        'tenant', 'ip_address',
    )
    list_filter = ('event_type', 'tenant', 'created_at')
    search_fields = (
        'user__email', 'ip_address',
        'details',
    )
    list_select_related = ('user', 'tenant')
    readonly_fields = (
        'user', 'tenant', 'event_type', 'ip_address',
        'user_agent', 'details', 'created_at',
    )
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete audit logs
        return request.user.is_superuser

    @display(description='User')
    def user_display(self, obj):
        return obj.user.email if obj.user else '(anonymous)'