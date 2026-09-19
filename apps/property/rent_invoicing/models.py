from django.db import models
from django.db.models import Sum
from django.utils import timezone
from apps.core.models import TimeStampedModel


class RentInvoice(TimeStampedModel):
    """A monthly rent bill for a lease."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ISSUED = 'ISSUED', 'Issued'
        PARTIAL = 'PART', 'Partially Paid'
        PAID = 'PAID', 'Paid'
        OVERDUE = 'OVER', 'Overdue'
        VOID = 'VOID', 'Void'

    invoice_number = models.CharField(max_length=20, unique=True, editable=False)
    lease = models.ForeignKey(
        'leases.Lease', on_delete=models.PROTECT,
        related_name='invoices',
    )
    tenant = models.ForeignKey(
        'people.Person', on_delete=models.PROTECT,
        related_name='rent_invoices',
    )
    unit = models.ForeignKey(
        'properties.Unit', on_delete=models.PROTECT,
        related_name='rent_invoices',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()
    status = models.CharField(
        max_length=6, choices=Status.choices, default=Status.DRAFT,
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    late_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='MWK')

    class Meta:
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=['lease', 'status']),
            models.Index(fields=['due_date', 'status']),
            models.Index(fields=['tenant', 'status']),
        ]

    def __str__(self):
        return f'{self.invoice_number} — {self.tenant.full_name}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            today = timezone.now().strftime('%Y%m%d')
            last = RentInvoice.objects.filter(
                invoice_number__startswith=f'INV-{today}'
            ).count() + 1
            self.invoice_number = f'INV-{today}-{last:04d}'
        super().save(*args, **kwargs)

    @property
    def balance(self):
        return self.total_due - self.amount_paid

    @property
    def days_overdue(self):
        if self.status in [self.Status.PAID, self.Status.VOID]:
            return 0
        delta = (timezone.now().date() - self.due_date).days
        return max(0, delta)

    @property
    def aging_bucket(self):
        """Return the aging bucket for arrears reporting."""
        days = self.days_overdue
        if days == 0:
            return 'current'
        if days <= 30:
            return '0-30'
        if days <= 60:
            return '31-60'
        if days <= 90:
            return '61-90'
        return '90+'

    def recalculate_totals(self):
        """Recompute subtotal, total_due, and status from line items and payments."""
        self.subtotal = self.lines.aggregate(
            t=Sum('amount')
        )['t'] or 0
        self.total_due = self.subtotal + self.late_fee
        self.amount_paid = self.payments.aggregate(
            t=Sum('amount')
        )['t'] or 0

        if self.amount_paid >= self.total_due:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PARTIAL
        elif self.due_date < timezone.now().date():
            self.status = self.Status.OVERDUE

        self.save()


class RentInvoiceLine(TimeStampedModel):
    """An individual charge line on a rent invoice."""

    class LineType(models.TextChoices):
        RENT = 'RENT', 'Base Rent'
        WATER = 'WATER', 'Water'
        ELECTRICITY = 'ELEC', 'Electricity'
        GARBAGE = 'GARB', 'Garbage'
        SECURITY = 'SEC', 'Security'
        SERVICE = 'SERV', 'Service Charge'
        LATE_FEE = 'LATE', 'Late Fee'
        OTHER = 'OTHER', 'Other'

    invoice = models.ForeignKey(
        RentInvoice, on_delete=models.CASCADE, related_name='lines',
    )
    line_type = models.CharField(max_length=6, choices=LineType.choices)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Meter-based charges (water, electricity)
    meter_reading_previous = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    meter_reading_current = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    meter_rate = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.get_line_type_display()}: {self.amount}'


class RentPayment(TimeStampedModel):
    """A payment against a rent invoice."""

    class Method(models.TextChoices):
        CASH = 'CASH', 'Cash'
        AIRTEL_MONEY = 'AIRTL', 'Airtel Money'
        TNM_MPAMBA = 'TNM', 'TNM Mpamba'
        BANK_TRANSFER = 'BANK', 'Bank Transfer'
        CARD = 'CARD', 'Card'
        CHEQUE = 'CHQ', 'Cheque'

    invoice = models.ForeignKey(
        RentInvoice, on_delete=models.PROTECT, related_name='payments',
    )
    method = models.CharField(max_length=6, choices=Method.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    reference = models.CharField(max_length=100, blank=True)
    received_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_method_display()}: {self.amount}'