import builtins

from django.db import models
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
    created_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['-check_in']
        indexes = [
            models.Index(fields=['property', 'status', 'check_in', 'check_out']),
            models.Index(fields=['reservation_number']),
            models.Index(fields=['primary_guest']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_out__gt=models.F('check_in')),
                name='reservation_checkout_after_checkin',
            ),
        ]

    def __str__(self):
        return f'{self.reservation_number} — {self.primary_guest.full_name}'

    def save(self, *args, **kwargs):
        if not self.reservation_number:
            today = timezone.now().strftime('%Y%m%d')
            last = Reservation.objects.filter(
                reservation_number__startswith=f'HTL-{today}'
            ).count() + 1
            self.reservation_number = f'HTL-{today}-{last:04d}'
        super().save(*args, **kwargs)

    # NOTE: the `property` FK field above shadows Python's builtin `property`
    # class inside this class body, so the `@property` decorator would try to
    # call the ForeignKey instance. Reach for `builtins.property` explicitly.
    @builtins.property
    def nights(self):
        return (self.check_out - self.check_in).days

    @staticmethod
    def find_conflicting_unit_ids(property, check_in, check_out,
                                   exclude_reservation=None):
        """
        Return unit IDs that are already booked during the requested range.
        Uses half-open intervals: [check_in, check_out).
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
    """Links a reservation to one or more specific units."""

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