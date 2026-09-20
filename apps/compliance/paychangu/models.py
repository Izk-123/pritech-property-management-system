from django.db import models
from apps.core.models import TimeStampedModel
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class PayChanguTransaction(TimeStampedModel):
    """Record of every PayChangu transaction for reconciliation."""

    class Status(models.TextChoices):
        INITIATED = 'INIT', 'Initiated'
        PENDING = 'PEND', 'Pending'
        SUCCESSFUL = 'SUCC', 'Successful'
        FAILED = 'FAIL', 'Failed'
        REFUNDED = 'REF', 'Refunded'

    class Method(models.TextChoices):
        AIRTEL_MONEY = 'AIRTL', 'Airtel Money'
        TNM_MPAMBA = 'TNM', 'TNM Mpamba'
        CARD = 'CARD', 'Card'
        BANK_TRANSFER = 'BANK', 'Bank Transfer'

    charge_id = models.CharField(max_length=100, unique=True, db_index=True)
    ref_id = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    method = models.CharField(
        max_length=6, choices=Method.choices, blank=True,
    )
    status = models.CharField(
        max_length=4, choices=Status.choices, default=Status.INITIATED,
    )
    # Payer details
    payer_mobile = models.CharField(max_length=20, blank=True)
    payer_name = models.CharField(max_length=255, blank=True)
    payer_email = models.EmailField(blank=True)
    # Link to the business transaction (FolioPayment or RentPayment)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    # Verification
    verification_data = models.JSONField(default=dict, blank=True)
    webhook_received_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['charge_id']),
            models.Index(fields=['status', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.charge_id} — {self.get_status_display()}'