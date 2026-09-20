from django import forms
from .models import Person


class PersonForm(forms.ModelForm):
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

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('is_blacklisted') and not cleaned.get('blacklist_reason'):
            self.add_error(
                'blacklist_reason',
                'Please provide a reason for blacklisting.',
            )
        return cleaned