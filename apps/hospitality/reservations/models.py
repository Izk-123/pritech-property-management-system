# apps/hospitality/reservations/models.py
"""
Reservation models.

A Reservation covers one or more rooms over a date range. The rooms
are attached via ReservationRoom rows **at booking time** — not at
check-in — so that confirmed bookings block inventory for their
dates. Attaching only at check-in was the original design and it
allowed overbooking: two staff could confirm two reservations for
the same room and the same dates without either seeing a conflict.
"""
import builtins
import secrets
from datetime import timedelta

from django.db import connection, models, transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Reservation(TimeStampedModel):
    """A booking for one or more rooms over a date range."""

    class Status(models.TextChoices):
        PENDING = 'PEND', 'Pending'
        CONFIRMED = 'CONF', 'Confirmed'
        CHECKED_IN = 'CHIN', 'Checked In'
        CHECKED_OUT = 'CHOUT', 'Checked Out'
        CANCELLED = 'CANC', 'Cancelled'
        NO_SHOW = 'NOSH', 'No Show'

    class Source(models.TextChoices):
        WALK_IN = 'WALK', 'Walk-In'
        PHONE = 'PHONE', 'Phone'
        EMAIL = 'EMAIL', 'Email'
        WEBSITE = 'WEB', 'Website'
        AGENT = 'AGENT', 'Travel Agent'

    reservation_number = models.CharField(
        max_length=20, unique=True, editable=False,
    )
    primary_guest = models.ForeignKey(
        'people.Person', on_delete=models.PROTECT,
        related_name='reservations',
    )
    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='reservations',
    )
    status = models.CharField(
        max_length=5, choices=Status.choices, default=Status.PENDING,
    )
    source = models.CharField(max_length=6, choices=Source.choices)
    check_in = models.DateField()
    check_out = models.DateField()
    adults = models.PositiveIntegerField(default=1)
    children = models.PositiveIntegerField(default=0)
    special_requests = models.TextField(blank=True)
    rate_plan = models.ForeignKey(
        'rates.RatePlan', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reservations',
    )
    deposit_required = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    deposit_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    deposit_currency = models.CharField(max_length=3, default='MWK')
    guest_access_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Anonymous one-time guest portal token scoped to this reservation.',
    )
    guest_access_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the guest portal link expires.',
    )
    created_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['-check_in']
        indexes = [
            models.Index(
                fields=['property', 'status', 'check_in', 'check_out'],
            ),
            models.Index(fields=['reservation_number']),
            models.Index(fields=['primary_guest']),
            models.Index(fields=['check_in']),
            models.Index(fields=['status', 'check_in']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_out__gt=models.F('check_in')),
                name='reservation_checkout_after_checkin',
            ),
        ]

    def __str__(self):
        return f'{self.reservation_number} — {self.primary_guest.full_name}'

    def generate_guest_access_token(self, *, expires_in_days=14):
        """Create or refresh a reservation-scoped guest portal token."""
        self.guest_access_token = secrets.token_urlsafe(32)
        self.guest_access_expires_at = timezone.now() + timedelta(days=expires_in_days)
        return self.guest_access_token

    @property
    def guest_access_is_valid(self):
        return bool(
            self.guest_access_token and
            self.guest_access_expires_at and
            self.guest_access_expires_at > timezone.now() and
            self.status not in {
                self.Status.CANCELLED,
                self.Status.NO_SHOW,
                self.Status.CHECKED_OUT,
            }
        )

    def save(self, *args, **kwargs):
        """
        Assign a reservation number on first save.

        The old implementation used ``count() + 1`` on the day's
        reservations. Two concurrent saves hit the same count, both
        tried to write the same number, and the second raised an
        IntegrityError because ``reservation_number`` is unique.

        The fix is a Postgres transaction-scoped advisory lock. The
        lock key is derived from today's date and is therefore stable
        across processes — unlike Python's ``hash()``, which is
        seeded per process. Two workers saving concurrently take
        turns: the first acquires the lock, counts, writes, and
        commits; the second then acquires the lock and sees the
        committed row.

        ``pg_advisory_xact_lock`` releases automatically when the
        surrounding transaction ends, so there is nothing to clean up
        on failure.
        """
        if self.reservation_number:
            # Already has a number — just save. No lock needed.
            return super().save(*args, **kwargs)

        with transaction.atomic():
            today = timezone.now().strftime('%Y%m%d')

            # Derive a stable 32-bit integer key from the date.
            # int('20261007') = 20261007 fits comfortably within the
            # signed 32-bit range pg_advisory_xact_lock accepts.
            lock_key = int(today)

            with connection.cursor() as cur:
                cur.execute(
                    'SELECT pg_advisory_xact_lock(%s)', [lock_key],
                )

            count = Reservation.objects.filter(
                reservation_number__startswith=f'HTL-{today}'
            ).count()

            self.reservation_number = f'HTL-{today}-{count + 1:04d}'
            super().save(*args, **kwargs)

    # NOTE: the `property` FK field above shadows Python's builtin
    # `property` class inside this class body, so the `@property`
    # decorator would try to call the ForeignKey instance. Reach for
    # `builtins.property` explicitly.
    @builtins.property
    def nights(self):
        return (self.check_out - self.check_in).days

    @builtins.property
    def guest_portal_url(self):
        if not self.guest_access_token:
            return ''
        return reverse('reservations:guest_portal', kwargs={'token': self.guest_access_token})

    @staticmethod
    def find_conflicting_unit_ids(property, check_in, check_out,
                                   exclude_reservation=None):
        """
        Return unit IDs that are already booked during the requested
        range, using half-open intervals: ``[check_in, check_out)``.

        A booking that ends on Oct 5 and a booking that starts on
        Oct 5 do *not* conflict — Oct 5 is the turnover day.

        Considers CONFIRMED and CHECKED_IN reservations as blocking.
        CANCELLED, NO_SHOW, and CHECKED_OUT are ignored. PENDING is
        not considered because our flow never creates PENDING rows
        (ReservationCreateView sets CONFIRMED directly); if that
        changes, add PENDING to the status list here.

        Pass ``exclude_reservation`` when checking availability for an
        existing reservation — otherwise its own rooms count as
        conflicts.
        """
        qs = ReservationRoom.objects.filter(
            reservation__property=property,
            reservation__status__in=[
                Reservation.Status.CONFIRMED,
                Reservation.Status.CHECKED_IN,
            ],
            reservation__check_in__lt=check_out,
            reservation__check_out__gt=check_in,
        )
        if exclude_reservation:
            qs = qs.exclude(reservation=exclude_reservation)
        return qs.values_list('unit_id', flat=True)


class ReservationRoom(TimeStampedModel):
    """
    Links a reservation to one or more specific units.

    Created at booking time (not check-in). The row is updated at
    check-in to record the actual arrival timestamp; the unit is
    flipped to OCCUPIED at the same moment.

    ``unique_together = [('reservation', 'unit')]`` prevents the same
    unit being added twice to a reservation.
    """

    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name='rooms',
    )
    unit = models.ForeignKey(
        'properties.Unit', on_delete=models.PROTECT,
        related_name='reservation_rooms',
    )
    rate_per_night = models.DecimalField(max_digits=12, decimal_places=2)
    rate_currency = models.CharField(max_length=3, default='MWK')
    actual_check_in = models.DateTimeField(null=True, blank=True)
    actual_check_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('reservation', 'unit')]

    def __str__(self):
        return f'{self.reservation.reservation_number} — {self.unit.identifier}'