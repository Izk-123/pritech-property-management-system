from django import forms
from django.utils import timezone

from apps.shared.forms import FormControlMixin
from .models import RentInvoiceLine, RentPayment


class RentInvoiceLineForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = RentInvoiceLine
        fields = ['line_type', 'description', 'amount',
                  'meter_reading_previous', 'meter_reading_current', 'meter_rate']
        help_texts = {
            'meter_reading_previous': 'Previous meter value (water/electricity lines only)',
            'meter_reading_current': 'Current meter value',
            'meter_rate': 'Cost per unit consumed',
        }


class RentPaymentForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = RentPayment
        fields = ['method', 'amount', 'currency', 'reference']
        widgets = {
            'reference': forms.TextInput(attrs={
                'placeholder': 'e.g., MP240115001234',
            }),
        }
        help_texts = {
            'reference': 'Airtel Money / Mpamba / bank transaction ID',
        }


class InvoiceGenerationForm(FormControlMixin, forms.Form):
    period_start = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Billing period start',
    )
    period_end = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Billing period end',
    )
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Due date',
        help_text='Usually the lease payment due day of the month',
    )

    def __init__(self, *args, lease=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lease = lease
        if lease and not self.is_bound:
            today = timezone.now().date()
            self.fields['period_start'].initial = today.replace(day=1)
            self.fields['period_end'].initial = today.replace(day=28)
            self.fields['due_date'].initial = today.replace(
                day=lease.payment_due_day
            )