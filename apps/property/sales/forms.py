from django import forms

from apps.shared.forms import FormControlMixin
from .models import SaleListing, SaleOffer, SaleAgreement


class SaleListingForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = SaleListing
        fields = [
            'property', 'unit', 'asking_price', 'minimum_price',
            'currency', 'description', 'agent',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6}),
        }
        help_texts = {
            'minimum_price': 'Lowest price you would accept (kept confidential)',
            'description': 'Marketing copy — will be visible to prospective buyers',
            'agent': 'Primary agent responsible for this listing',
        }


class SaleOfferForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = SaleOffer
        fields = ['buyer', 'offer_amount', 'currency', 'conditions', 'notes']
        widgets = {
            'conditions': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'conditions': 'Any conditions attached to the offer (financing, inspection, etc.)',
        }


class SaleAgreementForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = SaleAgreement
        fields = [
            'buyer', 'seller', 'sale_price', 'currency',
            'deposit_amount', 'payment_type', 'completion_date',
        ]
        widgets = {
            'completion_date': forms.DateInput(attrs={'type': 'date'}),
        }

    installment_count = forms.IntegerField(
        min_value=1, max_value=120, initial=12,
        label='Number of installments',
        help_text='Only applies when payment type is Installment Plan',
        required=False,
    )