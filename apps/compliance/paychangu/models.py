"""
PayChangu transaction ledger.

Every call to the PayChangu API — initiated from a view or received
as a webhook — leaves a row here. The ledger is the reconciliation
source of truth: if the PayChangu dashboard and our data disagree,
this table wins.

Design notes
------------
* ``charge_id`` is unique — PayChangu issues one per transaction and
  it never changes. Idempotency on webhook processing keys off this.

* ``content_type`` / ``object_id`` are **nullable**. A transaction
  can exist before it is linked to a FolioPayment or RentPayment
  (the webhook may arrive while the calling view is still
  committing its row), or it may never be linked at all (a payment
  that the tenant never recorded in the app). Requiring these
  would cause every webhook to fail ``IntegrityError`` — that was
  the original bug this file fixes.

* ``verification_data`` stores the raw JSON from PayChangu's verify
  endpoint. It's kept for audit purposes and to allow re-verification
  if a dispute arises.
"""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TimeStampedModel


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

    # ─── Identity ───────────────────────────────────────────────
    charge_id = models.CharField(
        max_length=100, unique=True, db_index=True,
        help_text='PayChangu-assigned transaction ID. Unique per transaction.',
    )
    ref_id = models.CharField(
        max_length=100, blank=True,
        help_text='Our own reference (usually an invoice or folio number).',
    )

    # ─── Money ──────────────────────────────────────────────────
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')

    method = models.CharField(
        max_length=6, choices=Method.choices, blank=True,
    )
    status = models.CharField(
        max_length=4, choices=Status.choices, default=Status.INITIATED,
    )

    # ─── Payer details (from PayChangu's webhook payload) ───────
    payer_mobile = models.CharField(max_length=20, blank=True)
    payer_name = models.CharField(max_length=255, blank=True)
    payer_email = models.EmailField(blank=True)

    # ─── Link to the business transaction ───────────────────────
    #
    # Nullable for two reasons:
    #
    #  1. Timing. The webhook can arrive before the view that
    #     initiated the payment has finished committing its
    #     FolioPayment / RentPayment row. Linking happens as a
    #     best-effort step in the webhook handler.
    #
    #  2. Some transactions are never linked. A tenant might pay a
    #     deposit that isn't yet attached to any invoice, or make a
    #     payment the front desk simply forgets to record. The
    #     ledger keeps the raw transaction so it can be reconciled
    #     manually later.
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # ─── Verification trail ─────────────────────────────────────
    verification_data = models.JSONField(
        default=dict, blank=True,
        help_text='Raw response from PayChangu verify_transaction.',
    )
    webhook_received_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['charge_id']),
            models.Index(fields=['status', 'created_at']),
            # Reconciliation queries: "find unlinked successful
            # transactions from this week" filters on these two.
            models.Index(fields=['content_type', 'object_id']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.charge_id} — {self.get_status_display()}'

    @property
    def is_linked(self):
        """True when this transaction is attached to a business object."""
        return self.content_type_id is not None and self.object_id is not None