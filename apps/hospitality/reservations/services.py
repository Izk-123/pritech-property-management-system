from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Reservation, ReservationRoom
from apps.hospitality.folios.models import Folio
from apps.core.properties.models import Unit


class CheckInError(ValidationError):
    pass


@transaction.atomic
def check_in_reservation(reservation, unit_assignments, user=None):
    """
    Check in a reservation.

    Args:
        reservation: Reservation instance (must be CONFIRMED)
        unit_assignments: list of dicts [{'unit': Unit, 'rate': Decimal}, ...]
        user: User performing the check-in

    Returns:
        The updated Reservation
    """
    if reservation.status != Reservation.Status.CONFIRMED:
        raise CheckInError(
            f'Cannot check in a reservation with status {reservation.status}.'
        )

    if not unit_assignments:
        raise CheckInError('At least one unit must be assigned.')

    now = timezone.now()

    for assignment in unit_assignments:
        unit = assignment['unit']
        rate = assignment['rate']

        if unit.status != Unit.Status.AVAILABLE:
            raise CheckInError(
                f'Unit {unit.identifier} is not available '
                f'(status: {unit.status}).'
            )

        # Verify the unit is actually free for the reservation dates
        conflicts = Reservation.find_conflicting_unit_ids(
            property=reservation.property,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            exclude_reservation=reservation,
        )
        if unit.id in conflicts:
            raise CheckInError(
                f'Unit {unit.identifier} is already booked for these dates.'
            )

        ReservationRoom.objects.create(
            reservation=reservation,
            unit=unit,
            rate_per_night=rate,
            actual_check_in=now,
        )
        unit.status = Unit.Status.OCCUPIED
        unit.save(update_fields=['status', 'updated_at'])

    reservation.status = Reservation.Status.CHECKED_IN
    reservation.save(update_fields=['status', 'updated_at'])

    # Create the folio if it doesn't exist
    Folio.objects.get_or_create(
        reservation=reservation,
        defaults={'currency': reservation.deposit_currency},
    )

    return reservation


@transaction.atomic
def check_out_reservation(reservation, user=None):
    """
    Check out a reservation. Requires folio balance to be zero (or overridden).
    Triggers housekeeping via the post_save signal.
    """
    if reservation.status != Reservation.Status.CHECKED_IN:
        raise CheckInError(
            f'Cannot check out a reservation with status {reservation.status}.'
        )

    folio = getattr(reservation, 'folio', None)
    if folio and folio.balance != 0:
        raise CheckInError(
            f'Folio has an outstanding balance of {folio.balance}. '
            f'Settle or write off before check-out.'
        )

    if folio:
        folio.status = Folio.Status.SETTLED
        folio.settled_at = timezone.now()
        folio.save(update_fields=['status', 'settled_at', 'updated_at'])

    reservation.status = Reservation.Status.CHECKED_OUT
    reservation.save(update_fields=['status', 'updated_at'])

    return reservation


@transaction.atomic
def cancel_reservation(reservation, reason='', user=None):
    """Cancel a reservation and release any assigned units."""
    if reservation.status in (
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CHECKED_OUT,
    ):
        raise CheckInError('Cannot cancel a reservation that has checked in.')

    for rr in reservation.rooms.all():
        rr.unit.status = Unit.Status.AVAILABLE
        rr.unit.save(update_fields=['status', 'updated_at'])

    reservation.status = Reservation.Status.CANCELLED
    reservation.special_requests = (
        f'{reservation.special_requests}\nCancelled: {reason}'.strip()
    )
    reservation.save(update_fields=['status', 'special_requests', 'updated_at'])

    return reservation

def available_units(property, check_in, check_out, unit_type=None):
    """
    Return queryset of units available for the given date range.
    """
    conflicting_ids = Reservation.find_conflicting_unit_ids(
        property=property,
        check_in=check_in,
        check_out=check_out,
    )

    qs = Unit.objects.filter(
        property=property,
        is_active=True,
        status=Unit.Status.AVAILABLE,
    ).exclude(id__in=conflicting_ids)

    if unit_type:
        qs = qs.filter(unit_type=unit_type)

    return qs.prefetch_related('amenities')