"""
Communications models.

NotificationTemplate  — per-tenant, per-event, per-channel template
NotificationLog       — audit trail of every outbound message
InboundMessage        — inbound WhatsApp messages from guests
"""
from django.db import models

from apps.core.models import TimeStampedModel


class NotificationTemplate(TimeStampedModel):
    """Per-tenant message template for a specific event and channel."""

    class Event(models.TextChoices):
        BOOKING_CONFIRMED = 'booking_confirmed', 'Booking Confirmed'
        CHECK_IN_REMINDER = 'check_in_reminder', 'Check-in Reminder'
        CHECKOUT_THANKS = 'checkout_thanks', 'Check-out Thank You'
        PAYMENT_RECEIPT = 'payment_receipt', 'Payment Receipt'
        LEASE_RENEWAL = 'lease_renewal', 'Lease Renewal Reminder'
        RENT_DUE = 'rent_due', 'Rent Due Reminder'
        RENT_OVERDUE = 'rent_overdue', 'Rent Overdue Notice'
        MAINTENANCE_UPDATE = 'maintenance_update', 'Maintenance Update'
        WELCOME = 'welcome', 'Welcome Message'

    class Channel(models.TextChoices):
        WHATSAPP = 'WA', 'WhatsApp'
        EMAIL = 'EM', 'Email'
        SMS = 'SMS', 'SMS'

    event = models.CharField(max_length=30, choices=Event.choices)
    channel = models.CharField(max_length=3, choices=Channel.choices)
    language = models.CharField(max_length=5, default='en')

    name = models.CharField(
        max_length=100,
        help_text=(
            'WhatsApp template name (approved in Meta Business Manager) '
            'or email subject.'
        ),
    )
    body = models.TextField(
        help_text=(
            'Message body with {placeholders}. '
            'Available: {guest_name}, {property_name}, {reservation_number}, '
            '{check_in}, {check_out}, {amount}, {currency}, {balance}.'
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Notification Template'
        verbose_name_plural = 'Notification Templates'
        unique_together = [('event', 'channel', 'language')]
        ordering = ['event', 'channel']

    def __str__(self):
        return f'{self.get_event_display()} ({self.get_channel_display()})'

    def render(self, context):
        """Return the body with placeholders filled in."""
        try:
            return self.body.format(**context)
        except (KeyError, IndexError):
            return self.body


class NotificationLog(TimeStampedModel):
    """Audit trail of every outbound message."""

    class Channel(models.TextChoices):
        WHATSAPP = 'WA', 'WhatsApp'
        EMAIL = 'EM', 'Email'
        SMS = 'SMS', 'SMS'

    class Status(models.TextChoices):
        PENDING = 'PEND', 'Pending'
        SENT = 'SENT', 'Sent'
        DELIVERED = 'DELIV', 'Delivered'
        READ = 'READ', 'Read'
        FAILED = 'FAIL', 'Failed'

    person = models.ForeignKey(
        'people.Person', on_delete=models.CASCADE,
        related_name='notifications',
    )
    channel = models.CharField(max_length=3, choices=Channel.choices)
    event = models.CharField(max_length=30)
    recipient = models.CharField(
        max_length=255,
        help_text='E.164 phone number or email address',
    )
    subject = models.CharField(max_length=255, blank=True)
    body_preview = models.TextField(blank=True)
    status = models.CharField(
        max_length=5, choices=Status.choices, default=Status.PENDING,
    )
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Optional links to business objects
    reservation_id = models.PositiveIntegerField(null=True, blank=True)
    folio_id = models.PositiveIntegerField(null=True, blank=True)
    lease_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = 'Notification Log'
        verbose_name_plural = 'Notification Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['person', 'status']),
            models.Index(fields=['channel', 'status']),
            models.Index(fields=['provider_message_id']),
            models.Index(fields=['event', 'created_at']),
        ]

    def __str__(self):
        return f'{self.get_channel_display()} → {self.recipient} ({self.get_status_display()})'


class InboundMessage(TimeStampedModel):
    """An inbound WhatsApp message from a guest."""

    person = models.ForeignKey(
        'people.Person', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inbound_messages',
    )
    from_number = models.CharField(max_length=20, db_index=True)
    body = models.TextField()
    provider_message_id = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    replied = models.BooleanField(default=False)
    replied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['from_number', 'created_at']),
            models.Index(fields=['is_read']),
        ]

    def __str__(self):
        return f'From {self.from_number}: {self.body[:50]}'