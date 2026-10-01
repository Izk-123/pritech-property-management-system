"""
Authentication and request middleware for Pritech PMS.

Four classes/functions:

  ClientIPMiddleware           — restores REMOTE_ADDR from Nginx's
                                 X-Real-IP so rate limiting, Axes,
                                 and audit logging see the real client
                                 IP behind a Unix socket.

  RequireTenantSetupMiddleware — redirects a Google-authenticated user
                                 with no tenant to /signup/complete/.

  ForceTwoFactorMiddleware     — Phase 9.2. Forces platform admins and
                                 superusers to enrol in MFA. Uses
                                 allauth.mfa state — django-otp is no
                                 longer present.

  ratelimited_view             — django-ratelimit's 429 response view.
                                 (Moved here from views.py, which was
                                 deleted with the two_factor migration.)
"""
import logging

from django.http import HttpResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Client IP restoration
# ─────────────────────────────────────────────────────────────────────

class ClientIPMiddleware:
    """
    Copy Nginx's X-Real-IP into request.META['REMOTE_ADDR'].

    Nginx proxies to Gunicorn over a Unix socket. In that setup the
    TCP peer Django sees has no IP — REMOTE_ADDR is empty. Any
    library that reads REMOTE_ADDR for rate limiting, lockout, or
    audit logging therefore fails or logs nothing useful. This
    middleware fixes the root cause for every consumer at once.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        real_ip = request.META.get('HTTP_X_REAL_IP')
        if real_ip:
            request.META['REMOTE_ADDR'] = real_ip
        return self.get_response(request)


# ─────────────────────────────────────────────────────────────────────
# Tenant setup guard — Phase 9.1
# ─────────────────────────────────────────────────────────────────────

_TENANT_SETUP_EXEMPT_PREFIXES = (
    '/signup/',
    '/accounts/',
    '/admin/',
    '/static/',
    '/media/',
    '/logout/',
    '/login/',
    '/i18n/',
    '/health/',
    '/offline/',
)


class RequireTenantSetupMiddleware:
    """
    If the user is authenticated but belongs to no tenant, send them
    to /signup/complete/ until they finish provisioning.

    Skips platform admins and superusers entirely — they manage
    tenants, they don't belong to them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_setup(request):
            return redirect('signup:complete')
        return self.get_response(request)

    def _needs_setup(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        if user.is_platform_admin or user.is_superuser:
            return False

        for prefix in _TENANT_SETUP_EXEMPT_PREFIXES:
            if request.path.startswith(prefix):
                return False

        return not user.tenant_memberships.exists()


# ─────────────────────────────────────────────────────────────────────
# MFA enforcement — Phase 9.2 (allauth.mfa)
# ─────────────────────────────────────────────────────────────────────

class ForceTwoFactorMiddleware:
    """
    Force platform admins and superusers to enrol in MFA.

    Runs after allauth's AccountMiddleware. If the user is
    authenticated as a platform admin but has no MFA authenticator
    enabled, redirect them to the TOTP activation page.

    Public schema only — tenant admins can enrol optionally, so this
    doesn't interrupt guest-facing tenant pages.

    Uses allauth.mfa's `Authenticator` model directly. Any row means
    the user has at least one MFA method set up (TOTP or recovery
    codes).
    """

    # Paths the user must be able to reach even without MFA set up.
    EXEMPT_PREFIXES = (
        '/accounts/2fa/',               # allauth MFA views
        '/accounts/logout/',
        '/accounts/password/',          # password change / reset
        '/accounts/confirm-email/',     # email verification
        '/accounts/email/',             # email management
        '/accounts/inactive/',
        '/accounts/reauthenticate/',
        '/admin/logout/',
        '/health/',
        '/static/',
        '/media/',
        '/i18n/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_mfa_setup(request):
            return redirect('mfa_activate_totp')
        return self.get_response(request)

    def _needs_mfa_setup(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        # Only force for platform admins and superusers
        if not (user.is_platform_admin or user.is_superuser):
            return False

        # Allow the MFA setup URLs themselves
        for prefix in self.EXEMPT_PREFIXES:
            if request.path.startswith(prefix):
                return False

        # Public schema only — tenant admins can enrol optionally
        tenant = getattr(request, 'tenant', None)
        if not tenant or tenant.schema_name != 'public':
            return False

        # Has any authenticator enabled?
        try:
            from allauth.mfa.models import Authenticator
            if Authenticator.objects.filter(user=user).exists():
                return False
        except Exception:
            # If the app isn't loaded yet (e.g. during a migration),
            # don't force a redirect that could loop.
            logger.exception('MFA check failed — allowing request')
            return False

        return True


# ─────────────────────────────────────────────────────────────────────
# Rate-limit view (moved from apps.shared.users.views)
# ─────────────────────────────────────────────────────────────────────

def ratelimited_view(request, exception=None):
    """Returned by django-ratelimit when a rate limit is exceeded."""
    return HttpResponse(
        'Too many requests. Please wait a minute and try again.',
        status=429,
        content_type='text/plain',
    )