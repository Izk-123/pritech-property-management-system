from django import forms

from apps.shared.forms import FormControlMixin
from .models import MaintenanceRequest


class MaintenanceRequestForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = ['unit', 'category', 'priority', 'title', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
        }
        help_texts = {
            'title': 'Short summary — e.g., "Leaking kitchen tap"',
            'description': 'Describe the issue in detail, including location and any access notes',
        }


class MaintenanceAssignForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = ['assigned_to', 'assigned_to_name']
        help_texts = {
            'assigned_to': 'Internal staff member (system user)',
            'assigned_to_name': 'External contractor name — use if not a system user',
        }


class MaintenanceCompleteForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = ['parts_cost', 'labour_cost', 'resolution_notes']
        widgets = {
            'resolution_notes': forms.Textarea(attrs={'rows': 5}),
        }
        help_texts = {
            'parts_cost': 'Cost of any parts or materials used (MWK)',
            'labour_cost': 'Labour charge, if any (MWK)',
            'resolution_notes': 'What was done to resolve the issue',
        }