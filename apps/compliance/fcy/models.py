from django.db import models
from apps.core.models import TimeStampedModel


class FCYBankAccount(TimeStampedModel):
    """Foreign currency denominated bank account per property."""

    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='fcy_accounts',
    )
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    currency = models.CharField(max_length=3)  # USD, EUR
    branch = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    authorized_at = models.DateField(
        help_text='Date RBM authorization received',
    )

    class Meta:
        verbose_name_plural = 'FCY Bank Accounts'

    def __str__(self):
        return f'{self.bank_name} — {self.currency} {self.account_number}'


class RBMReturn(TimeStampedModel):
    """Monthly RBM return of foreign currency transactions."""

    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='rbm_returns',
    )
    return_month = models.DateField(help_text='Month of return')
    currency = models.CharField(max_length=3)
    total_receipts = models.DecimalField(max_digits=14, decimal_places=2)
    total_refunds = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
    )
    net_foreign_currency = models.DecimalField(max_digits=14, decimal_places=2)
    transaction_count = models.PositiveIntegerField(default=0)
    submitted_to_rbm = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('property', 'return_month', 'currency')]

    def __str__(self):
        return f'{self.property.name} — {self.return_month} ({self.currency})'