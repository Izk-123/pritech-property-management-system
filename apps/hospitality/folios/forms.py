from django import forms

from apps.shared.forms import FormControlMixin
from .models import FolioCharge, FolioPayment


class FolioChargeForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = FolioCharge
        fields = ['charge_type', 'description', 'amount', 'currency']
        widgets = {
            'description': forms.TextInput(attrs={
                'placeholder': 'e.g., Dinner at restaurant',
            }),
        }
        help_texts = {
            'amount': 'Amount to post to the guest folio',
        }


class FolioPaymentForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = FolioPayment
        fields = ['method', 'amount', 'currency', 'reference']
        widgets = {
            'reference': forms.TextInput(attrs={
                'placeholder': 'Mobile money / bank reference',
            }),
        }
        help_texts = {
            'reference': 'Airtel Money / Mpamba / bank transaction ID',
        }