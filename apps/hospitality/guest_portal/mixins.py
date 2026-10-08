"""
Token resolution for the guest landing page.

Resolves the token in the URL to a Reservation, checks expiry, and
attaches the reservation, property, and guest to the request.

Raises 404 on any failure so an invalid token is indistinguishable
from a non-existent one.
"""
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.hospitality.reservations.models import Reservation


class GuestPortalMixin:
    def dispatch(self, request, *args, **kwargs):
        token = kwargs.get('token')
        if not token:
            raise Http404

        reservation = get_object_or_404(
            Reservation.objects
                .select_related('primary_guest', 'property')
                .prefetch_related('rooms__unit'),
            guest_access_token=token,
        )
        if not reservation.guest_access_is_valid:
            raise Http404

        request.guest_reservation = reservation
        request.guest_property = reservation.property
        request.guest = reservation.primary_guest

        return super().dispatch(request, *args, **kwargs)