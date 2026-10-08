# apps/hospitality/guest_portal/urls_staff.py
"""
Staff-side guest portal URLs.

Mounted at /staff/guest-portal/ in config/urls.py. Distinguished
from the guest-facing /stay/ namespace, which is anonymous and
token-scoped.
"""
from django.urls import path

from . import views_staff

app_name = 'guest_portal_staff'

urlpatterns = [
    path(
        'reservations/<int:pk>/resend-link/',
        views_staff.ResendPortalLinkView.as_view(),
        name='resend_link',
    ),
]