"""
Social account adapter for Pritech PMS.

Google returns a single `name` claim. This adapter splits it into
first_name / last_name and populates the extended User fields that
allauth doesn't know about.

It also sets a session flag when a brand-new Google user is created
without a tenant — the RequireTenantSetupMiddleware picks this up
and redirects to /signup/complete/.
"""
import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

logger = logging.getLogger(__name__)


class PritechSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Populates User from Google's profile claims.
    """

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)

        # Google gives us `given_name` and `family_name` for most
        # locales, and always a `name` (full display name). Prefer
        # the granular fields when present.
        given = (data.get('given_name') or '').strip()
        family = (data.get('family_name') or '').strip()
        full_name = (data.get('name') or '').strip()

        if given or family:
            user.first_name = given[:150]
            user.last_name = family[:150]
        elif full_name:
            parts = full_name.split(' ', 1)
            user.first_name = parts[0][:150]
            if len(parts) > 1:
                user.last_name = parts[1][:150]

        # Email is authoritative and pre-verified by Google.
        email = (data.get('email') or '').strip().lower()
        if email:
            user.email = email

        user.is_active = True

        logger.info(
            f'Populated Google user: {user.email} '
            f'({user.first_name} {user.last_name})'
        )
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)

        # If the user has no tenant yet (and isn't a platform admin),
        # mark their session so the middleware can redirect them to
        # /signup/complete/ after the OAuth handshake finishes.
        if (
            not user.is_platform_admin
            and not user.is_superuser
            and not user.tenant_memberships.exists()
        ):
            request.session['pending_tenant_setup'] = True
            logger.info(f'New Google user needs tenant setup: {user.email}')

        return user

    def is_auto_signup_allowed(self, request, sociallogin):
        return True

    def is_open_for_signup(self, request, sociallogin):
        return True