"""
Authentication and request middleware for Pritech PMS.

Three classes:

  ClientIPMiddleware           — restores REMOTE_ADDR from Nginx's
                                 X-Real-IP so rate limiting, Axes,
                                 and audit logging see the real client
                                 IP behind a Unix socket.

  RequireTenantSetupMiddleware — redirects a Google-authenticated user
                                 with no tenant to /signup/complete/.

  ForceTwoFactorMiddleware     — forces platform admins and superusers
                                 to enrol in 2FA (Phase 8).
"""
import logging

from django.shortcuts import redirect

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Client IP restoration
# ─────────────────────────────────────────────────────────────────────

class ClientIPMiddleware:
    """
    Copy Nginx's X-Real-IP into request.META['REMOTE_ADDR'].

    Why this exists
    ---------------
    Nginx proxies to Gunicorn over a Unix socket. In that setup the
    TCP peer Django sees has no IP — REMOTE_ADDR is empty. Any
    library that reads REMOTE_ADDR for rate limiting, lockout, or
    audit logging therefore fails or logs nothing useful. This
    middleware fixes the root cause for every consumer at once.

    Preference order
    ----------------
    * X-Real-IP         — set by Nginx to $remote_addr, unspoofable
    * (leave as-is)     — in local dev without a proxy, REMOTE_ADDR
                          already holds the loopback address

    Placement
    ---------
    Immediately after TenantMainMiddleware so everything downstream
    sees the corrected value.
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

# Paths that must stay reachable even when a user has no tenant yet.
# Signup itself, allauth's OAuth callback, static assets, health.
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

    Typical flow for a fresh Google sign-in:

      1. allauth creates the User, signs them in.
      2. Our social adapter sets session['pending_tenant_setup'] = True.
      3. This middleware sees an authenticated user with no
         UserTenantMembership rows and redirects to the completion
         form.
      4. After the form creates a Tenant + membership, the flag is
         cleared and normal navigation resumes.

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

        # Platform staff never need tenant setup
        if user.is_platform_admin or user.is_superuser:
            return False

        # Whitelisted paths always pass through (signup, allauth, etc.)
        for prefix in _TENANT_SETUP_EXEMPT_PREFIXES:
            if request.path.startswith(prefix):
                return False

        # Any active membership means they're already set up
        return not user.tenant_memberships.exists()


# ─────────────────────────────────────────────────────────────────────
# 2FA enforcement — Phase 8
# ─────────────────────────────────────────────────────────────────────

class ForceTwoFactorMiddleware:
    """
    Force platform admins and superusers to enrol in 2FA.

    Runs after OTPMiddleware. If the user is authenticated as a
    platform admin but has no confirmed OTP device, redirect them
    to the 2FA setup page.

    Public schema only — tenant admins can enrol optionally, so
    this doesn't interrupt guest-facing tenant pages.
    """

    EXEMPT_URLS = {
        '/account/two_factor/setup/',
        '/account/two_factor/backup/tokens/',
        '/account/logout/',
        '/admin/logout/',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_2fa_setup(request):
            return redirect('two_factor:setup')
        return self.get_response(request)

    def _needs_2fa_setup(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        # Only force for platform admins and superusers
        if not (user.is_platform_admin or user.is_superuser):
            return False

        # Allow the setup URLs themselves
        if request.path in self.EXEMPT_URLS:
            return False

        # Public schema only — tenant admins can enrol optionally
        tenant = getattr(request, 'tenant', None)
        if not tenant or tenant.schema_name != 'public':
            return False

        # Has a confirmed TOTP or static device?
        try:
            from django_otp import devices_for_user
            for device in devices_for_user(user, confirmed=True):
                return False
        except Exception:
            pass

        return True