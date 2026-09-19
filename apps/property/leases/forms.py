from django import forms
from django.core.exceptions import ValidationError

from apps.shared.forms import FormControlMixin
from .models import Lease


class LeaseForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = Lease
        fields = [
            'tenant', 'unit', 'landlord', 'start_date', 'end_date',
            'rent_free_until', 'rent_amount', 'rent_currency',
            'payment_frequency', 'payment_due_day', 'escalation_percent',
            'deposit_amount', 'grace_period_days',
            'late_fee_percent', 'late_fee_fixed',
            'auto_renew', 'renewal_notice_days',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'rent_free_until': forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'start_date': 'When the tenancy begins',
            'end_date': 'When the tenancy ends',
            'rent_free_until': 'Optional — leave blank if rent starts immediately',
            'payment_due_day': 'Day of month rent is due (1–28)',
            'escalation_percent': 'Annual rent increase (%)',
            'grace_period_days': 'Days after due date before late fees apply',
            'renewal_notice_days': 'Days before end date to send renewal notice',
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end <= start:
            raise ValidationError('End date must be after start date.')

        rent_free = cleaned.get('rent_free_until')
        if rent_free and start and rent_free < start:
            raise ValidationError('Rent-free end must be on or after start date.')

        return cleaned


class LeaseRenewalForm(FormControlMixin, forms.Form):
    new_end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='New end date',
        help_text='When the renewed lease will expire',
    )
    new_rent_amount = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        label='New rent amount',
        min_value=0,
        help_text='Leave blank to apply the escalation percentage automatically',
    )


class LeaseTerminationForm(FormControlMixin, forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        label='Reason for termination',
        help_text='Recorded in the audit log for compliance',
    )