from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import MaintenanceRequest


@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(ModelAdmin):
    list_display = (
        'title', 'unit', 'category', 'priority',
        'status', 'assigned_to', 'total_cost',
    )
    list_filter = ('category', 'priority', 'status')
    search_fields = ('title', 'description', 'unit__identifier')
    list_select_related = ('unit', 'assigned_to')
    autocomplete_fields = ('unit', 'submitted_by', 'assigned_to')
    readonly_fields = ('acknowledged_at', 'completed_at', 'verified_at')