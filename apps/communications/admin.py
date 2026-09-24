from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import InboundMessage, NotificationLog, NotificationTemplate


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(ModelAdmin):
    list_display = ('event', 'channel', 'language', 'name', 'is_active')
    list_filter = ('channel', 'event', 'language', 'is_active')
    search_fields = ('name', 'body')
    fieldsets = (
        ('Identity', {
            'fields': ('event', 'channel', 'language'),
        }),
        ('Content', {
            'fields': ('name', 'body'),
        }),
        ('Status', {
            'fields': ('is_active',),
        }),
    )


@admin.register(NotificationLog)
class NotificationLogAdmin(ModelAdmin):
    list_display = (
        'created_at', 'channel', 'event', 'person',
        'recipient', 'status',
    )
    list_filter = ('channel', 'status', 'event', 'created_at')
    search_fields = ('recipient', 'person__full_name', 'provider_message_id')
    list_select_related = ('person',)
    readonly_fields = (
        'created_at', 'updated_at', 'provider_message_id',
        'sent_at', 'delivered_at', 'error_message', 'body_preview',
    )
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(InboundMessage)
class InboundMessageAdmin(ModelAdmin):
    list_display = (
        'created_at', 'from_number', 'person',
        'body_preview', 'is_read', 'replied',
    )
    list_filter = ('is_read', 'replied', 'created_at')
    search_fields = ('from_number', 'body', 'person__full_name')
    list_select_related = ('person',)
    readonly_fields = (
        'created_at', 'updated_at', 'from_number', 'body',
        'provider_message_id',
    )

    def body_preview(self, obj):
        return obj.body[:80]
    body_preview.short_description = 'Message'