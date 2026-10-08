# apps/hospitality/guest_portal/utils.py
"""
Helpers shared between the guest portal views and tasks.
"""
from django.db import connection


def build_portal_url(reservation, request=None):
    """
    Build the full guest portal URL for a reservation.

    When `request` is provided, use its scheme and host so local dev
    works (lvh.me, localhost, custom ports). Otherwise fall back to
    the canonical production subdomain derived from the active
    tenant's schema_name — which is what the WhatsApp template must
    contain, since the guest's phone has no idea what lvh.me is.
    """
    if not reservation.guest_access_token:
        return ''

    path = f'/stay/{reservation.guest_access_token}/'

    if request is not None:
        return request.build_absolute_uri(path)

    schema = connection.tenant.schema_name
    return f'https://{schema}.pms.pritechmw.com{path}'