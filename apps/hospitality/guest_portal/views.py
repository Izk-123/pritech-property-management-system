"""
The single guest-facing view.

Shows a summary of the reservation and a WhatsApp deep link to the
front desk. Nothing else. No forms, no POST endpoints, no JavaScript.
"""
from django.views.generic import TemplateView

from apps.communications.services import normalise_mw_phone

from .mixins import GuestPortalMixin


class GuestLandingView(GuestPortalMixin, TemplateView):
    template_name = 'pages/guest/landing.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        reservation = self.request.guest_reservation
        prop = self.request.guest_property
        guest = self.request.guest

        ctx['reservation'] = reservation
        ctx['room'] = reservation.rooms.first()

        # Property phone → E.164 for the wa.me link
        ctx['whatsapp_number'] = normalise_mw_phone(prop.phone or '')

        # Pre-filled message — built here, not in the template, so we
        # can URL-encode once and never worry about it again.
        if ctx['whatsapp_number']:
            from urllib.parse import quote
            ctx['whatsapp_message'] = quote(
                f'Hi, this is {guest.full_name}, '
                f'about reservation {reservation.reservation_number}.'
            )

        return ctx