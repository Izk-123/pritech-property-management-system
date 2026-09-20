from django import forms

from apps.shared.forms import FormControlMixin
from .models import Person


class PersonForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = Person
        fields = [
            'full_name', 'id_type', 'id_number', 'date_of_birth',
            'nationality', 'phone_primary', 'phone_secondary', 'email',
            'address', 'district', 'preferred_language',
            'is_blacklisted', 'blacklist_reason',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'blacklist_reason': forms.Textarea(attrs={'rows': 2}),
        }
        help_texts = {
            'full_name': 'As it appears on the ID document',
            'id_number': 'National ID, passport, or driver\u2019s licence number',
            'phone_primary': 'Primary contact number — used for SMS notifications',
            'phone_secondary': 'Optional alternate number',
            'preferred_language': 'Used for messages and printed documents',
            'blacklist_reason': 'Required if the person is flagged as blacklisted',
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('is_blacklisted') and not cleaned.get('blacklist_reason'):
            self.add_error(
                'blacklist_reason',
                'Please provide a reason for blacklisting.',
            )
        return cleaned