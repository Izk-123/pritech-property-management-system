from django import forms
from django.core.validators import RegexValidator
from .models import Tenant


SUBDOMAIN_VALIDATOR = RegexValidator(
    regex=r'^[a-z0-9][a-z0-9-]{1,62}$',
    message='Subdomain must be 2-63 characters, lowercase letters, '
            'numbers, and hyphens only, starting with a letter or number.',
)

RESERVED_SUBDOMAINS = {
    'www', 'admin', 'api', 'app', 'mail', 'public',
    'static', 'media', 'dashboard', 'signup', 'login',
    'billing', 'support', 'help', 'docs', 'status',
}


class TenantForm(forms.ModelForm):
    """Form for creating or editing a tenant."""

    subdomain = forms.SlugField(
        max_length=63,
        validators=[SUBDOMAIN_VALIDATOR],
        help_text='This becomes the URL: subdomain.pms.pritechmw.com',
        required=False,  # Only required on create
    )

    class Meta:
        model = Tenant
        fields = [
            'name', 'plan', 'is_active', 'on_trial', 'paid_until',
            'contact_name', 'contact_email', 'contact_phone',
        ]
        widgets = {
            'paid_until': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Editing an existing tenant — prefill subdomain from schema
            self.fields['subdomain'].initial = self.instance.schema_name
            self.fields['subdomain'].help_text = (
                'Changing the subdomain will change the URL. '
                'Existing data is preserved.'
            )

    def clean_subdomain(self):
        subdomain = self.cleaned_data.get('subdomain')
        if not subdomain:
            if self.instance and self.instance.pk:
                return self.instance.schema_name
            raise forms.ValidationError('Subdomain is required.')

        subdomain = subdomain.lower()

        if subdomain in RESERVED_SUBDOMAINS:
            raise forms.ValidationError('This subdomain is reserved.')

        # Check uniqueness (excluding current instance on edit)
        qs = Tenant.objects.filter(schema_name=subdomain)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('This subdomain is already taken.')

        return subdomain

    def save(self, commit=True):
        instance = super().save(commit=False)
        subdomain = self.cleaned_data.get('subdomain')
        if subdomain and not instance.schema_name:
            instance.schema_name = subdomain
        if commit:
            instance.save()
        return instance


class TenantSignupForm(forms.Form):
    """Public signup form for new tenants."""

    organization_name = forms.CharField(
        max_length=255,
        label='Organization name',
        widget=forms.TextInput(attrs={'placeholder': 'Lakeview Lodge'}),
    )
    subdomain = forms.SlugField(
        max_length=63,
        validators=[SUBDOMAIN_VALIDATOR],
        label='Workspace URL',
        help_text='Lowercase letters, numbers, and hyphens. '
                  'Your URL: subdomain.pms.pritechmw.com',
        widget=forms.TextInput(attrs={'placeholder': 'lakeview'}),
    )
    contact_name = forms.CharField(max_length=255, label='Your name')
    contact_email = forms.EmailField(label='Email')
    contact_phone = forms.CharField(max_length=20, required=False)
    plan = forms.ChoiceField(
        choices=Tenant.Plan.choices,
        initial=Tenant.Plan.STARTER,
    )
    admin_password = forms.CharField(
        min_length=10,
        widget=forms.PasswordInput,
        label='Admin password',
        help_text='Minimum 10 characters.',
    )
    accept_terms = forms.BooleanField(
        label='I accept the terms of service',
    )

    def clean_subdomain(self):
        subdomain = self.cleaned_data['subdomain'].lower()
        if subdomain in RESERVED_SUBDOMAINS:
            raise forms.ValidationError('This subdomain is reserved.')
        if Tenant.objects.filter(schema_name=subdomain).exists():
            raise forms.ValidationError('This subdomain is already taken.')
        return subdomain

    def clean_contact_email(self):
        email = self.cleaned_data['contact_email'].lower()
        from apps.shared.users.models import User
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                'An account with this email already exists. '
                'Please sign in or use a different email.'
            )
        return email