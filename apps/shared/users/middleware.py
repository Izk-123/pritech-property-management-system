from django.shortcuts import redirect
from django.urls import reverse


class ForceTwoFactorMiddleware:
    """
    Force platform admins and superusers to enroll in 2FA.

    Runs after OTPMiddleware. If the user is authenticated as a
    platform admin but has no confirmed OTP device, redirect them
    to the 2FA setup page.
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

        # Public schema only — tenant admins can enroll optionally
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