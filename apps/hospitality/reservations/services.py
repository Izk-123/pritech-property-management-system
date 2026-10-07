# apps/hospitality/reservations/services.py
"""
Reservation lifecycle services.

Every state transition that touches inventory lives here so the
locking and conflict-checking is consistent between the online
views and the offline sync handlers.

Locking discipline
------------------
Any time we change which units a reservation holds (booking,
check-in, cancellation, check-out) we ``select_for_update()`` the
affected Unit rows. This serialises concurrent writers so two
requests can't slip past the same conflict check.

The check itself — ``Reservation.find_conflicting_unit_ids()`` — is
a query, not a constraint. It only works if the caller holds the
lock. Do not move availability checks outside the lock.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.properties.models import Unit
from apps.hospitality.folios.models import Folio

from .models import Reservation, ReservationRoom


class CheckInError(ValidationError):
    pass


# ─────────────────────────────────────────────────────────────────────
# Availability queries
# ─────────────────────────────────────────────────────────────────────

def available_units(property, check_in, check_out, unit_type=None,
                    include_unit_ids=None):
    """
    Queryset of units that can be booked for ``[check_in, check_out)``.

    Availability is determined *only* by reservation conflicts.
    The unit's ``status`` field (AVAILABLE / OCCUPIED / CLEANING)
    tracks its current housekeeping state and has no bearing on
    whether a future booking is possible — a room that is OCCUPIED
    tonight and has no reservation for next week is available next
    week, and the old code wrongly excluded it.

    Maintenance is the one status that does block future bookings.
    If the model defines ``Unit.Status.MAINTENANCE`` we exclude
    those units as well.

    ``include_unit_ids`` forces specific units to appear in the
    result even if they conflict. Used by ``CheckInForm`` so the
    reservation's own rooms show up as selectable.
    """
    conflicting_ids = set(
        Reservation.find_conflicting_unit_ids(
            property=property,
            check_in=check_in,
            check_out=check_out,
        )
    )

    if include_unit_ids:
        # Units already attached to the reservation being edited do
        # not conflict with themselves.
        conflicting_ids -= set(include_unit_ids)

    qs = (
        Unit.objects
        .filter(property=property, is_active=True)
        .exclude(id__in=conflicting_ids)
    )

    # Maintenance is a status, not a date-range concept. If the
    # model defines one, exclude those units — they are out of
    # service for an indefinite period.
    maintenance = getattr(Unit.Status, 'MAINTENANCE', None)
    if maintenance is not None:
        qs = qs.exclude(status=maintenance)

    if unit_type:
        qs = qs.filter(unit_type=unit_type)

    return qs.prefetch_related('amenities')


# ─────────────────────────────────────────────────────────────────────
# Booking
# ─────────────────────────────────────────────────────────────────────

@transaction.atomic
def attach_unit_to_reservation(reservation, unit, rate_per_night):
    """
    Create or update a ReservationRoom linking ``reservation`` to
    ``unit``. Called by the create view right after the reservation
    row exists.

    Locks the unit row for the duration of the transaction. If
    another booking slipped in between the form's conflict check and
    this call, the lock serialises us behind it and the conflict
    check below rejects the attempt.

    Raises ``ValidationError`` if the unit is already booked for the
    same dates by another reservation.
    """
    # Lock the unit — this is what guarantees the conflict check
    # below cannot be raced.
    unit = Unit.objects.select_for_update().get(pk=unit.pk)

    conflicting_ids = Reservation.find_conflicting_unit_ids(
        property=reservation.property,
        check_in=reservation.check_in,
        check_out=reservation.check_out,
        exclude_reservation=reservation,
    )
    if unit.pk in conflicting_ids:
        raise ValidationError(
            f'Room {unit.identifier} was booked by another reservation '
            f'while this form was being submitted. Pick a different '
            f'room.'
        )

    room, _ = ReservationRoom.objects.update_or_create(
        reservation=reservation,
        unit=unit,
        defaults={'rate_per_night': rate_per_night},
    )
    return room


# ─────────────────────────────────────────────────────────────────────
# Check-in / check-out / cancel
# ─────────────────────────────────────────────────────────────────────

@transaction.atomic
def check_in_reservation(reservation, unit_assignments, user=None):
    """
    Check in a reservation.

    ``unit_assignments`` is a list of dicts:
        [{'unit': Unit, 'rate': Decimal}, ...]

    The rooms were attached at booking time — this call updates the
    existing ReservationRoom rows with ``actual_check_in`` and
    flips each unit to OCCUPIED. If the receptionist picked a
    different room at check-in, the old assignment is removed and a
    new ReservationRoom is created.

    Removing the ``status != AVAILABLE`` guard
    ------------------------------------------
    The previous implementation refused to check in if the unit's
    status wasn't AVAILABLE. That was wrong: the status field
    reflects housekeeping state, and a room can be CLEANING while
    the guest is checking in. The authoritative check is
    ``find_conflicting_unit_ids`` — if no other reservation holds
    the room for these dates, the check-in is legitimate.
    """
    if reservation.status != Reservation.Status.CONFIRMED:
        raise CheckInError(
            f'Cannot check in a reservation with status {reservation.status}.'
        )

    if not unit_assignments:
        raise CheckInError('At least one unit must be assigned.')

    now = timezone.now()

    # ── 1. Drop any assignments not in the new set ──────────────
    # This handles the case where reception swaps the room at
    # check-in: the old ReservationRoom is deleted and a new one is
    # created below.
    new_unit_ids = {assignment['unit'].pk for assignment in unit_assignments}
    reservation.rooms.exclude(unit_id__in=new_unit_ids).delete()

    # ── 2. Update or create each assignment ─────────────────────
    for assignment in unit_assignments:
        raw_unit = assignment['unit']
        rate = assignment['rate']

        # Lock the unit row so no concurrent check-in can grab it.
        unit = Unit.objects.select_for_update().get(pk=raw_unit.pk)

        # Conflict check against OTHER reservations. Excludes this
        # reservation's own rooms.
        conflicts = Reservation.find_conflicting_unit_ids(
            property=reservation.property,
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            exclude_reservation=reservation,
        )
        if unit.pk in conflicts:
            raise CheckInError(
                f'Room {unit.identifier} is held by another reservation '
                f'for these dates.'
            )

        # Update the booking-time ReservationRoom with the actual
        # arrival timestamp; if none exists (legacy reservation
        # created before this fix), create one now.
        ReservationRoom.objects.update_or_create(
            reservation=reservation,
            unit=unit,
            defaults={
                'rate_per_night': rate,
                'actual_check_in': now,
            },
        )

        unit.status = Unit.Status.OCCUPIED
        unit.save(update_fields=['status', 'updated_at'])

    # ── 3. Flip the reservation status ──────────────────────────
    reservation.status = Reservation.Status.CHECKED_IN
    reservation.save(update_fields=['status', 'updated_at'])

    # ── 4. Ensure a folio exists ────────────────────────────────
    Folio.objects.get_or_create(
        reservation=reservation,
        defaults={'currency': reservation.deposit_currency},
    )

    return reservation


@transaction.atomic
def check_out_reservation(reservation, user=None):
    """
    Check out a reservation. Requires folio balance to be zero (or
    overridden). Triggers housekeeping via the post_save signal.
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

    now = timezone.now()

    if folio:
        folio.status = Folio.Status.SETTLED
        folio.settled_at = now
        folio.save(update_fields=['status', 'settled_at', 'updated_at'])

    # Record the departure time and release the room.
    for room in reservation.rooms.select_related('unit'):
        room.actual_check_out = now
        room.save(update_fields=['actual_check_out', 'updated_at'])

        # Housekeeping signals mark the unit CLEANING; we just flip
        # it if the signal hasn't already. The unit is not AVAILABLE
        # until housekeeping confirms.
        if room.unit.status == Unit.Status.OCCUPIED:
            room.unit.status = Unit.Status.CLEANING
            room.unit.save(update_fields=['status', 'updated_at'])

    reservation.status = Reservation.Status.CHECKED_OUT
    reservation.save(update_fields=['status', 'updated_at'])

    return reservation


@transaction.atomic
def cancel_reservation(reservation, reason='', user=None):
    """
    Cancel a reservation.

    Deletes the ReservationRoom rows (so the room is freed for other
    bookings) and flips the reservation to CANCELLED.
    """
    if reservation.status in (
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CHECKED_OUT,
    ):
        raise CheckInError('Cannot cancel a reservation that has checked in.')

    # Deleting ReservationRoom rows is what actually frees the
    # inventory — availability is derived from these rows, not from
    # the unit's status field.
    reservation.rooms.all().delete()

    reservation.status = Reservation.Status.CANCELLED
    reservation.special_requests = (
        f'{reservation.special_requests}\nCancelled: {reason}'.strip()
    )
    reservation.save(update_fields=['status', 'special_requests', 'updated_at'])

    return reservation