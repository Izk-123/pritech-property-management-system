from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.core.models import TimeStampedModel


class Lease(TimeStampedModel):
    """A rental contract between a tenant and a unit."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING = 'PEND', 'Pending Signature'
        ACTIVE = 'ACT', 'Active'
        EXPIRED = 'EXP', 'Expired'
        TERMINATED = 'TERM', 'Terminated'
        RENEWED = 'REN', 'Renewed'

    class Frequency(models.TextChoices):
        MONTHLY = 'MONTH', 'Monthly'
        QUARTERLY = 'QTR', 'Quarterly'
        ANNUALLY = 'YEAR', 'Annually'

    lease_number = models.CharField(max_length=20, unique=True, editable=False)
    tenant = models.ForeignKey(
        'people.Person', on_delete=models.PROTECT,
        related_name='leases',
    )
    unit = models.ForeignKey(
        'properties.Unit', on_delete=models.PROTECT,
        related_name='leases',
    )
    landlord = models.ForeignKey(
        'people.Person', on_delete=models.PROTECT,
        related_name='landlord_leases', null=True, blank=True,
    )
    status = models.CharField(
        max_length=5, choices=Status.choices, default=Status.DRAFT,
    )
    start_date = models.DateField()
    end_date = models.DateField()
    rent_free_until = models.DateField(
        null=True, blank=True,
        help_text='Rent-free period end date (common in commercial leases)',
    )
    rent_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    rent_currency = models.CharField(max_length=3, default='MWK')
    payment_frequency = models.CharField(
        max_length=5, choices=Frequency.choices, default=Frequency.MONTHLY,
    )
    payment_due_day = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(28)],
        help_text='Day of month rent is due (1–28)',
    )
    escalation_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Annual rent increase percentage',
    )
    deposit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    deposit_received = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    deposit_refunded = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    deposit_deductions = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    grace_period_days = models.PositiveIntegerField(default=5)
    late_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
    )
    late_fee_fixed = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    auto_renew = models.BooleanField(default=False)
    renewal_notice_days = models.PositiveIntegerField(default=60)
    document = models.ForeignKey(
        'documents.Document', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='leases',
    )
    created_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['unit', 'status']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['end_date', 'status']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F('start_date')),
                name='lease_end_after_start',
            ),
            models.CheckConstraint(
                condition=models.Q(payment_due_day__gte=1,
                                   payment_due_day__lte=28),
                name='lease_due_day_1_to_28',
            ),
        ]

    def __str__(self):
        return f'{self.lease_number} — {self.tenant.full_name}'

    def save(self, *args, **kwargs):
        if not self.lease_number:
            today = timezone.now().strftime('%Y%m%d')
            last = Lease.objects.filter(
                lease_number__startswith=f'LSE-{today}'
            ).count() + 1
            self.lease_number = f'LSE-{today}-{last:04d}'
        super().save(*args, **kwargs)

    @property
    def deposit_balance(self):
        return (
            self.deposit_received
            - self.deposit_refunded
            - self.deposit_deductions
        )

    @property
    def is_expiring_soon(self):
        """Lease ends within the renewal notice window."""
        if self.status != self.Status.ACTIVE:
            return False
        days_remaining = (self.end_date - timezone.now().date()).days
        return 0 <= days_remaining <= self.renewal_notice_days


class LeaseUnit(TimeStampedModel):
    """Junction: a lease can cover multiple units (apartment + parking)."""

    lease = models.ForeignKey(
        Lease, on_delete=models.CASCADE, related_name='lease_units',
    )
    unit = models.ForeignKey(
        'properties.Unit', on_delete=models.PROTECT,
        related_name='lease_units',
    )
    rent_share = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='If different from main rent',
    )

    class Meta:
        unique_together = [('lease', 'unit')]

    def __str__(self):
        return f'{self.lease.lease_number} → {self.unit.identifier}'