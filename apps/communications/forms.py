from django import forms

from apps.shared.forms import FormControlMixin
from .models import NotificationTemplate, InboundMessage


class NotificationTemplateForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = NotificationTemplate
        fields = ['event', 'channel', 'language', 'name', 'body', 'is_active']
        widgets = {
            'body': forms.Textarea(attrs={'rows': 6}),
        }


class InboundReplyForm(FormControlMixin, forms.Form):
    """Reply to an inbound WhatsApp message."""

    body = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Type a reply…',
        }),
        label='Reply',
    )