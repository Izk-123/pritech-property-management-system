from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import HousekeepingTask


@admin.register(HousekeepingTask)
class HousekeepingTaskAdmin(ModelAdmin):
    list_display = (
        'unit', 'task_type', 'status', 'priority',
        'assigned_to', 'started_at', 'completed_at',
    )
    list_filter = ('task_type', 'status', 'priority')
    search_fields = ('unit__identifier', 'unit__property__name', 'notes')
    list_select_related = ('unit', 'unit__property', 'assigned_to', 'inspected_by')
    autocomplete_fields = ('unit', 'assigned_to', 'inspected_by')
    readonly_fields = ('started_at', 'completed_at')
    date_hierarchy = 'created_at'