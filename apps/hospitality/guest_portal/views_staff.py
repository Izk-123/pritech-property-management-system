# apps/hospitality/guest_portal/views_staff.py
"""
Staff-facing views for the guest portal.

Not mounted under /stay/ — that namespace is guest-only. These live
under /staff/guest-portal/ and require authentication + staff status.
"""
from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View

from apps.communications.models import NotificationLog
from apps.communications.services import normalise_mw_phone
from apps.core.mixins import TenantStaffRequiredMixin
from apps.hospitality.reservations.models import Reservation

from .tasks import send_guest_portal_link


class ResendPortalLinkView(TenantStaffRequiredMixin, View):
    """
    Resend the guest portal link over WhatsApp.

    Two actions, distinguished by the `action` value on the submit
    button:

      resend  — reuse the current token if valid, extend its expiry
                by 30 days, resend. Use when the guest lost the
                message.

      rotate  — generate a brand-new token regardless of the current
                one's validity, extend its expiry by 30 days, resend.
                Use when the guest reports the link leaked.

    Rate-limited to one send per 2 minutes per reservation. Tracked
    via NotificationLog — the same table the task writes to — so no
    additional state is required.
    """

    RATE_LIMIT_SECONDS = 120

    def post(self, request, pk):
        reservation = get_object_or_404(
            Reservation.objects.select_related('primary_guest'),
            pk=pk,
        )
        action = request.POST.get('action', 'resend')

        # ── Guard: phone number on file ────────────────────────────
        #
        # The task itself also checks this and returns 'no-phone',
        # but checking here means the staff member gets immediate
        # feedback instead of a silent no-op.
        phone = normalise_mw_phone(
            reservation.primary_guest.phone_primary or '',
        )
        if not phone:
            messages.error(
                request,
                'Guest has no phone number on file. '
                'Add one before resending the link.',
            )
            return redirect('reservations:detail', pk=pk)

        # ── Guard: recent send ─────────────────────────────────────
        cutoff = timezone.now() - timedelta(
            seconds=self.RATE_LIMIT_SECONDS,
        )
        if NotificationLog.objects.filter(
            reservation_id=reservation.pk,
            event='guest_portal_link',
            created_at__gte=cutoff,
        ).exists():
            minutes = self.RATE_LIMIT_SECONDS // 60
            messages.warning(
                request,
                f'A portal link was already sent in the last '
                f'{minutes} minute{"s" if minutes != 1 else ""}. '
                f'Wait a moment before resending.',
            )
            return redirect('reservations:detail', pk=pk)

        # ── Ensure the token is valid ──────────────────────────────
        #
        # Four cases collapse into two branches:
        #
        #   no token / token expired / rotate requested
        #       → generate a fresh token and reset expiry to +30d
        #
        #   token valid, plain resend
        #       → reuse the token, push expiry out to +30d
        #
        # Extending on reuse matters: a link sent 29 days ago and
        # about to expire shouldn't be resent with a 24-hour window
        # the guest won't see.
        rotate = (action == 'rotate')
        needs_new_token = (
            not reservation.guest_access_token
            or not reservation.guest_access_is_valid
            or rotate
        )

        if needs_new_token:
            reservation.generate_guest_access_token(expires_in_days=30)
            reservation.save(update_fields=[
                'guest_access_token',
                'guest_access_expires_at',
                'updated_at',
            ])
        else:
            reservation.guest_access_expires_at = (
                timezone.now() + timedelta(days=30)
            )
            reservation.save(update_fields=[
                'guest_access_expires_at',
                'updated_at',
            ])

        # ── Queue the WhatsApp send ────────────────────────────────
        #
        # The task creates the NotificationLog row the rate limiter
        # above reads on its next invocation, so no extra bookkeeping
        # is needed here.
        try:
            send_guest_portal_link.delay(reservation.pk)
        except Exception:
            messages.error(
                request,
                'Could not queue the WhatsApp send — the broker may '
                'be down. Try again in a moment.',
            )
            return redirect('reservations:detail', pk=pk)

        if rotate:
            messages.success(
                request,
                f'New link generated and sent to {phone}. '
                f'Any previously shared links no longer work.',
            )
        else:
            messages.success(
                request,
                f'Portal link sent to {phone}.',
            )
        return redirect('reservations:detail', pk=pk)