from django.db import models
from apps.core.models import TimeStampedModel
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class EISTerminal(TimeStampedModel):
    """An MRA EIS terminal registered for a property or branch."""

    class Status(models.TextChoices):
        PENDING = 'PEND', 'Pending Activation'
        ACTIVE = 'ACT', 'Active'
        SUSPENDED = 'SUSP', 'Suspended'
        OFFLINE = 'OFF', 'Offline Mode'

    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='eis_terminals',
    )
    terminal_code = models.CharField(max_length=50, unique=True)
    terminal_activation_code = models.CharField(
        max_length=100, blank=True,
        help_text='TAC provided by MRA via email/SMS',
    )
    tin = models.CharField(
        max_length=20, help_text='Taxpayer Identification Number',
    )
    trading_name = models.CharField(max_length=255)
    default_tax_office = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=5, choices=Status.choices, default=Status.PENDING,
    )
    # Configuration synced from MRA via getLatestConfig
    config_data = models.JSONField(default=dict, blank=True)
    last_config_sync = models.DateTimeField(null=True, blank=True)
    # Offline signing key for QR codes when offline
    offline_signing_key = models.CharField(
        max_length=255, blank=True,
        help_text='Terminal-specific key for offline HMAC QR generation',
    )
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['property', 'terminal_code']

    def __str__(self):
        return f'{self.terminal_code} ({self.property.name})'


class EISInvoiceLog(TimeStampedModel):
    """Audit log of every invoice submitted to MRA EIS."""

    class SubmissionStatus(models.TextChoices):
        PENDING = 'PEND', 'Pending Submission'
        SUBMITTED = 'SUBM', 'Submitted to MRA'
        VALIDATED = 'VAL', 'Validated (MRA Invoice No Received)'
        OFFLINE_QUEUED = 'OFFQ', 'Queued Offline'
        FAILED = 'FAIL', 'Submission Failed'
        DUPLICATE = 'DUP', 'Duplicate Invoice Number'

    # Generic link to any invoice (folio, rent invoice, sale installment)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE,
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    terminal = models.ForeignKey(
        EISTerminal, on_delete=models.PROTECT,
        related_name='invoice_logs',
    )
    invoice_number = models.CharField(max_length=50, db_index=True)
    mra_invoice_number = models.CharField(max_length=50, blank=True)
    mra_validation_url = models.URLField(blank=True)
    mra_qr_signature = models.TextField(
        blank=True, help_text='Signature converted to QR code',
    )
    mra_response_data = models.JSONField(default=dict, blank=True)
    submission_status = models.CharField(
        max_length=4, choices=SubmissionStatus.choices,
        default=SubmissionStatus.PENDING,
    )
    offline_hmac_signature = models.TextField(blank=True)
    offline_generated_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['submission_status']),
            models.Index(fields=['content_type', 'object_id']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.invoice_number} → {self.get_submission_status_display()}'


class EISProductMapping(TimeStampedModel):
    """Maps internal products/services to MRA-standardized category codes."""

    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='eis_products',
    )
    internal_code = models.CharField(max_length=50)
    mra_product_code = models.CharField(max_length=50, blank=True)
    mra_category_code = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=255)
    is_approved = models.BooleanField(default=False)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('property', 'internal_code')]

    def __str__(self):
        return f'{self.internal_code} → {self.mra_product_code}'