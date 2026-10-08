"""
Send the guest portal link over WhatsApp after a booking is created.

Called explicitly from ReservationCreateView.form_valid — never from
a post_save signal, to avoid re-sending every time staff edit a
reservation.
"""
import logging

from celery import shared_task
from django.db import connection

logger = logging.getLogger(__name__)


@shared_task
def send_guest_portal_link(reservation_id):
    from apps.communications.models import NotificationLog
    from apps.communications.services import normalise_mw_phone
    from apps.communications.tasks import send_whatsapp_template_task
    from apps.communications.templates import body_components
    from apps.hospitality.reservations.models import Reservation

    try:
        res = Reservation.objects.select_related(
            'primary_guest', 'property',
        ).get(pk=reservation_id)
    except Reservation.DoesNotExist:
        return 'missing'

    # ── Generate a token if none exists ────────────────────────────
    # Reservation.guest_access_token is null=True, blank=True and is
    # NOT populated by the create flow. Without this, every link
    # would ship dead.
    if not res.guest_access_token:
        res.generate_guest_access_token(expires_in_days=30)
        res.save(update_fields=[
            'guest_access_token', 'guest_access_expires_at', 'updated_at',
        ])

    guest = res.primary_guest
    phone = normalise_mw_phone(guest.phone_primary)
    if not phone:
        return 'no-phone'

    # ── Build the portal URL ──────────────────────────────────────
    # schema_name comes from the active tenant, not from the Property
    # model — Property is a tenant-schema row and does not carry it.
    schema = connection.tenant.schema_name
    portal_url = (
        f'https://{schema}.pms.pritechmw.com'
        f'/stay/{res.guest_access_token}/'
    )

    log = NotificationLog.objects.create(
        person=guest,
        channel=NotificationLog.Channel.WHATSAPP,
        event='guest_portal_link',
        recipient=phone,
        body_preview=f'Portal link for {res.reservation_number}',
        reservation_id=res.pk,
    )

    send_whatsapp_template_task.delay(
        log_id=log.pk,
        template_name='guest_portal_link',
        components=body_components(
            guest.full_name,
            res.property.name,
            portal_url,
        ),
    )
    return f'queued:{log.pk}'