from django import forms
from django.core.exceptions import ValidationError

from apps.shared.forms import FormControlMixin
from .models import Reservation
from .services import available_units


class ReservationForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = Reservation
        fields = [
            'primary_guest', 'property', 'source',
            'check_in', 'check_out', 'adults', 'children',
            'rate_plan', 'special_requests',
        ]
        widgets = {
            'check_in': forms.DateInput(attrs={'type': 'date'}),
            'check_out': forms.DateInput(attrs={'type': 'date'}),
            'special_requests': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'check_in': 'Guest arrival date',
            'check_out': 'Guest departure date',
            'adults': 'Number of adults (12+)',
            'children': 'Number of children under 12',
        }

    def clean(self):
        cleaned = super().clean()
        check_in = cleaned.get('check_in')
        check_out = cleaned.get('check_out')
        if check_in and check_out and check_out <= check_in:
            raise ValidationError('Check-out must be after check-in.')
        return cleaned


class CheckInForm(FormControlMixin, forms.Form):
    """Assign one or more available units to a reservation at check-in."""

    def __init__(self, *args, reservation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.reservation = reservation

        units = available_units(
            property=reservation.property,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
        )

        self.fields['unit'] = forms.ModelChoiceField(
            queryset=units,
            label='Assign unit',
            empty_label='— Select an available unit —',
            help_text='Only units available for the full stay are shown.',
        )
        self.fields['rate'] = forms.DecimalField(
            max_digits=12, decimal_places=2,
            label='Rate per night (MWK)',
            min_value=0,
            help_text='Applied to each night of the stay.',
        )
        # Re-apply classes for fields added after super().__init__
        self._apply_widget_classes()

    def get_unit_assignments(self):
        return [{
            'unit': self.cleaned_data['unit'],
            'rate': self.cleaned_data['rate'],
        }]