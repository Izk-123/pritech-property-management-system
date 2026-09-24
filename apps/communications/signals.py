"""
Signals that trigger guest notifications.

These are deliberately minimal — most notifications are dispatched
explicitly from services or views so we control the timing.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='reservations.Reservation')
def reservation_created(sender, instance, created, **kwargs):
    """Queue a WhatsApp confirmation when a reservation is first created."""
    if not created:
        return
    if instance.status != 'CONF':
        return

    try:
        from .tasks import send_booking_confirmation
        send_booking_confirmation.delay(instance.pk)
    except Exception:
        logger.exception('Could not queue booking confirmation')