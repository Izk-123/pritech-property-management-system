# apps/hospitality/reservations/forms.py
"""
Reservation forms.

Two forms:

  ReservationForm   — create and edit a booking. Includes the unit
                      assignment so the room is held from the moment
                      the reservation is confirmed.

  CheckInForm       — the check-in wizard step. Pre-selects the
                      reserved room and lets the receptionist confirm
                      or change it.

Notes on the unit queryset
--------------------------
Django cannot compute ``available_units()`` in ``__init__`` unless
both ``property`` and the two dates are known. On GET that's rarely
the case (the user hasn't picked anything yet). Rather than build a
cascading AJAX widget, we take the pragmatic approach:

  * If property + dates are present (bound POST, or initial values
    from a prefilled create), the queryset is ``available_units()``.
  * If only property is present, the queryset is all active units of
    that property; ``clean()`` will reject a conflicting choice.

A future iteration can swap the unit select for an HTMX endpoint
that reloads the options on property/date change.
"""
from datetime import date

from django import forms
from django.core.exceptions import ValidationError

from apps.shared.forms import FormControlMixin

from .models import Reservation
from .services import available_units


def _parse_date(value):
    """Return a date, or None. Accepts ISO strings and date objects."""
    if value is None or value == '':
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


class ReservationForm(FormControlMixin, forms.ModelForm):
    """
    ModelForm for Reservation plus unit assignment.

    ``unit`` is not a Reservation model field — it's the concrete
    Room the guest will occupy. On save, the calling view creates a
    ReservationRoom linking them. Making it part of the form is what
    lets availability be checked at the same time the reservation is
    saved.
    """

    unit = forms.ModelChoiceField(
        queryset=None,   # set per-instance in __init__
        label='Room',
        empty_label='— Select a room —',
        help_text='The guest will occupy this room. Available for the '
                  'dates above.',
    )
    rate_per_night = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=0,
        label='Rate per night (MWK)',
        required=False,
        help_text='Leave blank to use the room\'s base rate.',
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # The unit field's queryset is populated below depending on
        # what we know about the property and dates.
        from apps.core.properties.models import Property, Unit

        property_obj = None
        check_in = None
        check_out = None

        if self.is_bound:
            # POST — the property and dates come from the submitted data.
            property_id = self.data.get('property')
            if property_id:
                try:
                    property_obj = Property.objects.get(pk=property_id)
                except (Property.DoesNotExist, ValueError, TypeError):
                    property_obj = None
            check_in = _parse_date(self.data.get('check_in'))
            check_out = _parse_date(self.data.get('check_out'))
        else:
            # GET — prefer initial, fall back to instance (edit view).
            property_obj = self.initial.get('property') or (
                self.instance.property if self.instance.pk else None
            )
            check_in = self.initial.get('check_in') or (
                self.instance.check_in if self.instance.pk else None
            )
            check_out = self.initial.get('check_out') or (
                self.instance.check_out if self.instance.pk else None
            )

            # Edit view: pre-select the room already assigned.
            if self.instance.pk:
                first_room = self.instance.rooms.first()
                if first_room:
                    self.initial.setdefault('unit', first_room.unit_id)
                    self.initial.setdefault(
                        'rate_per_night', first_room.rate_per_night,
                    )

        # Decide the unit queryset.
        if property_obj and check_in and check_out:
            # Full information — offer only rooms that are actually
            # free for the requested window.
            self.fields['unit'].queryset = available_units(
                property=property_obj,
                check_in=check_in,
                check_out=check_out,
                include_unit_ids=(
                    list(self.instance.rooms.values_list('unit_id', flat=True))
                    if self.instance.pk else None
                ),
            )
        elif property_obj:
            # Property known, dates not yet validated — show all
            # active rooms. clean() will reject a conflicting pick.
            self.fields['unit'].queryset = Unit.objects.filter(
                property=property_obj, is_active=True,
            ).order_by('identifier')
        else:
            # Nothing to go on — leave the field empty.
            self.fields['unit'].queryset = Unit.objects.none()

    # ── Field-level validation ─────────────────────────────────

    def clean_unit(self):
        """
        The unit must belong to the property on the form.

        If the property changes after the unit is picked, this
        catches it before the create view tries to save. Also used
        as a second-pass availability check when the queryset was
        not restricted (dates missing at __init__ time).
        """
        unit = self.cleaned_data.get('unit')
        property_obj = self.cleaned_data.get('property')

        if not unit:
            return unit
        if property_obj and unit.property_id != property_obj.pk:
            raise ValidationError(
                'The selected room does not belong to the selected property.'
            )

        check_in = self.cleaned_data.get('check_in')
        check_out = self.cleaned_data.get('check_out')

        if property_obj and check_in and check_out and check_out > check_in:
            conflicting_ids = Reservation.find_conflicting_unit_ids(
                property=property_obj,
                check_in=check_in,
                check_out=check_out,
                exclude_reservation=self.instance if self.instance.pk else None,
            )
            if unit.pk in conflicting_ids:
                raise ValidationError(
                    'That room is already booked for these dates. '
                    'Pick a different room or change the dates.'
                )
        return unit

    def clean_rate_per_night(self):
        """
        Default to the selected unit's base rate when blank.

        We can't do this in ``__init__`` because the unit isn't
        known until clean_unit runs. Doing it here means callers
        always get a rate — no fallback logic needed at the call site.
        """
        rate = self.cleaned_data.get('rate_per_night')
        if rate:
            return rate
        unit = self.cleaned_data.get('unit')
        if unit and hasattr(unit, 'base_rate_mwk'):
            return unit.base_rate_mwk
        return rate

    def clean(self):
        cleaned = super().clean()
        check_in = cleaned.get('check_in')
        check_out = cleaned.get('check_out')
        if check_in and check_out and check_out <= check_in:
            raise ValidationError('Check-out must be after check-in.')
        return cleaned


class CheckInForm(FormControlMixin, forms.Form):
    """
    Assign one or more available units to a reservation at check-in.

    The reserved room (if any) is included in the queryset even though
    it may show as "conflicting" against the reservation itself —
    ``available_units()`` supports an ``include_unit_ids`` argument
    for exactly this case.
    """

    def __init__(self, *args, reservation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.reservation = reservation

        # Rooms already assigned to this reservation are always
        # allowed, even though they appear in find_conflicting_unit_ids
        # (they conflict with the reservation itself).
        include = list(
            reservation.rooms.values_list('unit_id', flat=True)
        )

        units = available_units(
            property=reservation.property,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            include_unit_ids=include,
        )

        # Pre-select the reserved room if there's exactly one.
        initial_unit = include[0] if len(include) == 1 else None
        initial_rate = (
            reservation.rooms.first().rate_per_night
            if reservation.rooms.exists() else None
        )

        self.fields['unit'] = forms.ModelChoiceField(
            queryset=units,
            label='Assign unit',
            empty_label='— Select an available unit —',
            help_text='Only units available for the full stay are shown.',
            initial=initial_unit,
        )
        self.fields['rate'] = forms.DecimalField(
            max_digits=12, decimal_places=2,
            label='Rate per night (MWK)',
            min_value=0,
            help_text='Applied to each night of the stay.',
            initial=initial_rate,
        )
        # Re-apply classes for fields added after super().__init__.
        self._apply_widget_classes()

    def get_unit_assignments(self):
        return [{
            'unit': self.cleaned_data['unit'],
            'rate': self.cleaned_data['rate'],
        }]