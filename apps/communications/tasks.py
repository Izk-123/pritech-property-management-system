"""
Celery tasks for outbound messages.

Every message is asynchronous so a slow WhatsApp API call never
blocks a user's HTTP request. Tasks are idempotent and retry with
exponential backoff.
"""
import logging

from celery import shared_task
from django.utils import timezone

from .models import NotificationLog
from .services import WhatsAppClient, send_email, normalise_mw_phone
from .templates import body_components

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Low-level senders
# ─────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=180)
def send_whatsapp_template_task(
    self,
    log_id: int,
    template_name: str,
    language: str = 'en',
    components: list = None,
):
    """Send a WhatsApp template and update the NotificationLog."""
    try:
        log = NotificationLog.objects.get(pk=log_id)
    except NotificationLog.DoesNotExist:
        return 'log-missing'

    client = WhatsAppClient()
    message_id, error = client.send_template(
        to=log.recipient,
        template_name=template_name,
        language=language,
        components=components,
    )

    if message_id:
        log.status = NotificationLog.Status.SENT
        log.provider_message_id = message_id
        log.sent_at = timezone.now()
        log.error_message = ''
        log.save(update_fields=[
            'status', 'provider_message_id', 'sent_at',
            'error_message', 'updated_at',
        ])
        return message_id

    log.status = NotificationLog.Status.FAILED
    log.error_message = error or 'unknown'
    log.save(update_fields=['status', 'error_message', 'updated_at'])

    raise self.retry(exc=Exception(error or 'WhatsApp send failed'))


@shared_task(bind=True, max_retries=3, default_retry_delay=180)
def send_email_task(
    self,
    log_id: int,
    subject: str,
    text_body: str,
    html_body: str = '',
    from_email: str = '',
):
    """Send an email and update the NotificationLog."""
    try:
        log = NotificationLog.objects.get(pk=log_id)
    except NotificationLog.DoesNotExist:
        return 'log-missing'

    ok, error = send_email(
        to=log.recipient,
        subject=subject,
        text_body=text_body,
        html_body=html_body or None,
        from_email=from_email or None,
    )

    if ok:
        log.status = NotificationLog.Status.SENT
        log.sent_at = timezone.now()
        log.error_message = ''
        log.save(update_fields=['status', 'sent_at', 'error_message', 'updated_at'])
        return 'sent'

    log.status = NotificationLog.Status.FAILED
    log.error_message = error or 'unknown'
    log.save(update_fields=['status', 'error_message', 'updated_at'])
    raise self.retry(exc=Exception(error or 'Email send failed'))


# ─────────────────────────────────────────────────────────────────────
# High-level tasks (called by signals)
# ─────────────────────────────────────────────────────────────────────

@shared_task
def send_payment_receipt(payment_id: int):
    """
    Send a WhatsApp receipt for a FolioPayment.

    Triggered by the FolioPayment post_save signal.
    """
    from apps.hospitality.folios.models import FolioPayment

    try:
        payment = FolioPayment.objects.select_related(
            'folio__reservation__primary_guest',
            'folio__reservation__property',
        ).get(pk=payment_id)
    except FolioPayment.DoesNotExist:
        return 'payment-missing'

    reservation = payment.folio.reservation
    guest = reservation.primary_guest

    phone = normalise_mw_phone(guest.phone_primary)
    if not phone:
        return 'no-phone'

    log = NotificationLog.objects.create(
        person=guest,
        channel=NotificationLog.Channel.WHATSAPP,
        event='payment_receipt',
        recipient=phone,
        body_preview=(
            f'Receipt: {payment.currency} {payment.amount} '
            f'for {reservation.reservation_number}'
        ),
        reservation_id=reservation.pk,
        folio_id=payment.folio_id,
    )

    components = body_components(
        guest.full_name,
        f'{payment.currency} {payment.amount}',
        reservation.reservation_number,
        f'{payment.folio.currency} {payment.folio.balance}',
    )

    send_whatsapp_template_task.delay(
        log_id=log.pk,
        template_name='payment_receipt',
        components=components,
    )
    return f'queued:{log.pk}'


@shared_task
def send_booking_confirmation(reservation_id: int):
    """
    Send a WhatsApp confirmation when a reservation is created.

    Call this explicitly from the reservation creation view or
    service. Do NOT trigger it from post_save unconditionally —
    you'll spam guests whenever a staff member edits their stay.
    """
    from apps.hospitality.reservations.models import Reservation

    try:
        reservation = Reservation.objects.select_related(
            'primary_guest', 'property',
        ).get(pk=reservation_id)
    except Reservation.DoesNotExist:
        return 'reservation-missing'

    guest = reservation.primary_guest
    phone = normalise_mw_phone(guest.phone_primary)
    if not phone:
        return 'no-phone'

    log = NotificationLog.objects.create(
        person=guest,
        channel=NotificationLog.Channel.WHATSAPP,
        event='booking_confirmed',
        recipient=phone,
        body_preview=(
            f'Booking {reservation.reservation_number} — '
            f'{reservation.check_in} to {reservation.check_out}'
        ),
        reservation_id=reservation.pk,
    )

    components = body_components(
        guest.full_name,
        reservation.property.name,
        reservation.reservation_number,
        reservation.check_in.strftime('%d %b %Y'),
        reservation.check_out.strftime('%d %b %Y'),
    )

    send_whatsapp_template_task.delay(
        log_id=log.pk,
        template_name='booking_confirmation',
        components=components,
    )
    return f'queued:{log.pk}'


@shared_task
def send_checkin_reminder(reservation_id: int):
    """Send a reminder 24 hours before check-in."""
    from apps.hospitality.reservations.models import Reservation

    try:
        reservation = Reservation.objects.select_related(
            'primary_guest', 'property',
        ).get(pk=reservation_id)
    except Reservation.DoesNotExist:
        return 'reservation-missing'

    guest = reservation.primary_guest
    phone = normalise_mw_phone(guest.phone_primary)
    if not phone:
        return 'no-phone'

    log = NotificationLog.objects.create(
        person=guest,
        channel=NotificationLog.Channel.WHATSAPP,
        event='check_in_reminder',
        recipient=phone,
        body_preview=f'Reminder for {reservation.reservation_number}',
        reservation_id=reservation.pk,
    )

    components = body_components(
        guest.full_name,
        reservation.property.name,
        reservation.check_in.strftime('%d %b %Y'),
    )
    send_whatsapp_template_task.delay(
        log_id=log.pk,
        template_name='check_in_reminder',
        components=components,
    )
    return f'queued:{log.pk}'


@shared_task
def send_rent_due_reminder(invoice_id: int):
    """Send a WhatsApp reminder for an upcoming rent invoice."""
    from apps.property.rent_invoicing.models import RentInvoice

    try:
        invoice = RentInvoice.objects.select_related(
            'tenant', 'unit',
        ).get(pk=invoice_id)
    except RentInvoice.DoesNotExist:
        return 'invoice-missing'

    tenant = invoice.tenant
    phone = normalise_mw_phone(tenant.phone_primary)
    if not phone:
        return 'no-phone'

    log = NotificationLog.objects.create(
        person=tenant,
        channel=NotificationLog.Channel.WHATSAPP,
        event='rent_due',
        recipient=phone,
        body_preview=f'Rent due: {invoice.currency} {invoice.balance}',
    )

    components = body_components(
        tenant.full_name,
        invoice.unit.identifier,
        f'{invoice.currency} {invoice.balance}',
        invoice.due_date.strftime('%d %b %Y'),
    )
    send_whatsapp_template_task.delay(
        log_id=log.pk,
        template_name='rent_due',
        components=components,
    )
    return f'queued:{log.pk}'


# ─────────────────────────────────────────────────────────────────────
# Periodic tasks
# ─────────────────────────────────────────────────────────────────────

@shared_task
def scan_checkin_reminders():
    """
    Runs daily. Finds reservations checking in tomorrow and queues
    reminders.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.hospitality.reservations.models import Reservation

    tomorrow = (timezone.now().date() + timedelta(days=1))
    qs = Reservation.objects.filter(
        status=Reservation.Status.CONFIRMED,
        check_in=tomorrow,
    )
    count = 0
    for res in qs:
        send_checkin_reminder.delay(res.pk)
        count += 1
    return f'queued {count} check-in reminders'


@shared_task
def scan_rent_due_reminders(days_before: int = 3):
    """Runs daily. Queues rent reminders for invoices due in N days."""
    from datetime import timedelta
    from django.utils import timezone
    from apps.property.rent_invoicing.models import RentInvoice

    target = timezone.now().date() + timedelta(days=days_before)
    qs = RentInvoice.objects.filter(
        status__in=[
            RentInvoice.Status.ISSUED,
            RentInvoice.Status.PARTIAL,
        ],
        due_date=target,
    )
    count = 0
    for inv in qs:
        send_rent_due_reminder.delay(inv.pk)
        count += 1
    return f'queued {count} rent reminders'