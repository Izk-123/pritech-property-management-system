from django import forms
from django.contrib.contenttypes.models import ContentType
from .models import Document


class DocumentUploadForm(forms.ModelForm):
    """
    Upload form with a target selection.

    The 'target_type' choice determines the content_type, and
    'target_id' specifies the object_id.
    """

    TARGET_CHOICES = [
        ('people.person', 'Person'),
        ('properties.property', 'Property'),
        ('properties.unit', 'Unit'),
        ('leases.lease', 'Lease'),
        ('sales.saleagreement', 'Sale Agreement'),
        ('reservations.reservation', 'Reservation'),
    ]

    target_type = forms.ChoiceField(
        choices=TARGET_CHOICES,
        label='Attach to',
        help_text='What is this document attached to?',
    )
    target_id = forms.IntegerField(
        label='Target ID',
        help_text='The ID of the record this document belongs to.',
    )

    class Meta:
        model = Document
        fields = ['doc_type', 'title', 'file', 'expiry_date', 'notes']
        widgets = {
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        target_type = cleaned.get('target_type')
        target_id = cleaned.get('target_id')

        if not target_type or not target_id:
            return cleaned

        # Parse "app_label.model_name" and resolve the ContentType
        try:
            app_label, model_name = target_type.split('.')
            ct = ContentType.objects.get(
                app_label=app_label, model=model_name,
            )
        except (ValueError, ContentType.DoesNotExist):
            self.add_error(
                'target_type',
                'Invalid target type. Contact support.',
            )
            return cleaned

        # Verify the target object exists
        model_class = ct.model_class()
        if model_class and not model_class.objects.filter(pk=target_id).exists():
            self.add_error(
                'target_id',
                f'No {ct.name} with ID {target_id} exists.',
            )
            return cleaned

        cleaned['content_type'] = ct
        cleaned['object_id'] = target_id
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.content_type = self.cleaned_data['content_type']
        instance.object_id = self.cleaned_data['object_id']
        if commit:
            instance.save()
        return instance