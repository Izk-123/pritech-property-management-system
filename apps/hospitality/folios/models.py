from django.db import models
from django.db.models import Sum
from apps.core.models import TimeStampedModel


class Folio(TimeStampedModel):
    """The running bill for a reservation."""

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        SETTLED = 'SETL', 'Settled'
        VOID = 'VOID', 'Void'

    reservation = models.OneToOneField(
        'reservations.Reservation', on_delete=models.PROTECT,
        related_name='folio',
    )
    status = models.CharField(
        max_length=4, choices=Status.choices, default=Status.OPEN,
    )
    currency = models.CharField(max_length=3, default='MWK')
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['status'])]

    def __str__(self):
        return f'Folio for {self.reservation.reservation_number}'

    @property
    def total_charges(self):
        return self.charges.aggregate(t=Sum('amount'))['t'] or 0

    @property
    def total_payments(self):
        return self.payments.aggregate(t=Sum('amount'))['t'] or 0

    @property
    def balance(self):
        return self.total_charges - self.total_payments


class FolioCharge(TimeStampedModel):
    """A single charge line on a folio."""

    class ChargeType(models.TextChoices):
        ROOM = 'ROOM', 'Room Charge'
        FNB = 'FNB', 'Food & Beverage'
        LAUNDRY = 'LAUN', 'Laundry'
        MINIBAR = 'MINI', 'Minibar'
        ACTIVITY = 'ACT', 'Activity/Package'
        MISC = 'MISC', 'Miscellaneous'
        DISCOUNT = 'DISC', 'Discount'

    folio = models.ForeignKey(
        Folio, on_delete=models.CASCADE, related_name='charges',
    )
    charge_type = models.CharField(max_length=5, choices=ChargeType.choices)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    posted_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['folio', 'charge_type'])]

    def __str__(self):
        return f'{self.get_charge_type_display()}: {self.amount}'


class FolioPayment(TimeStampedModel):
    """A payment against a folio."""

    class Method(models.TextChoices):
        CASH_MWK = 'CASH_MWK', 'Cash (MWK)'
        CASH_USD = 'CASH_USD', 'Cash (USD)'
        AIRTEL_MONEY = 'AIRTL', 'Airtel Money'
        TNM_MPAMBA = 'TNM', 'TNM Mpamba'
        CARD = 'CARD', 'Card'
        BANK_TRANSFER = 'BANK', 'Bank Transfer'

    folio = models.ForeignKey(
        Folio, on_delete=models.CASCADE, related_name='payments',
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    reference = models.CharField(max_length=100, blank=True)
    received_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.get_method_display()}: {self.amount}'