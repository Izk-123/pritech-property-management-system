# apps/hospitality/guest_portal/tasks.py
"""
Send the guest portal link over WhatsApp.

Called explicitly from:
  • ReservationCreateView.form_valid — via transaction.on_commit,
    so a rolled-back booking never produces a stray message.
  • ResendPortalLinkView.post — staff-triggered resend.

Never called from a signal. Editing a reservation must not spam
the guest.
"""
import logging

from celery import shared_task

from .utils import build_portal_url

logger = logging.getLogger(__name__)


@shared_task
def send_guest_portal_link(reservation_id):
    """
    Queue the guest portal link over WhatsApp.

    Safe to call on a reservation that already has a valid token:
    the token is reused, not rotated. Rotation is the view's job,
    because only the view knows whether the staff member asked for
    it.
    """
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

    # Safety net. The create view relies on this because it doesn't
    # have a token yet when it queues the task; the resend view has
    # already generated one, so this branch is a no-op there.
    if not res.guest_access_token:
        res.generate_guest_access_token(expires_in_days=30)
        res.save(update_fields=[
            'guest_access_token',
            'guest_access_expires_at',
            'updated_at',
        ])

    guest = res.primary_guest
    phone = normalise_mw_phone(guest.phone_primary or '')
    if not phone:
        return 'no-phone'

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
            build_portal_url(res),
        ),
    )
    return f'queued:{log.pk}'