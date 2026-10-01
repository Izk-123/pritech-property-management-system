"""
Adapters for allauth.

Two adapters:

  PritechAccountAdapter       — email/password login flow. Enforces
                                tenant membership (moved here from
                                the old SchemaAwareLoginView).

  PritechSocialAccountAdapter — Google sign-in. Splits the `name`
                                claim and routes fresh users to
                                /signup/complete/.

Why the account adapter does the tenant check
---------------------------------------------
allauth's login view owns the login flow end-to-end (that's how it
can chain MFA without us reimplementing the whole wizard). If we
subclass the view just to add a membership check, we'd lose that.
Instead we override ``login()`` on the adapter — a hook called right
before ``django.contrib.auth.login()`` — and raise
``ImmediateHttpResponse`` to abort the login cleanly.
"""
import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


class PritechAccountAdapter(DefaultAccountAdapter):
    """
    Email/password login adapter.

    Enforces the same tenant-membership rule the old
    SchemaAwareLoginView enforced: a user cannot log into a tenant
    subdomain unless they have an active UserTenantMembership there
    (or are a platform admin / superuser).
    """

    def login(self, request, user):
        tenant = getattr(request, 'tenant', None)

        # Public schema — no membership check
        if not tenant or tenant.schema_name == 'public':
            return super().login(request, user)

        # Platform staff bypass
        if user.is_platform_admin or user.is_superuser:
            return super().login(request, user)

        # Tenant schema — require an active membership
        if not user.has_membership(tenant):
            from apps.shared.users.models import AuthAuditLog
            AuthAuditLog.objects.create(
                user=user,
                tenant=tenant,
                event_type=AuthAuditLog.EventType.PERMISSION_DENIED,
                details={
                    'reason': 'no_membership_for_tenant',
                    'tenant_schema': tenant.schema_name,
                },
            )
            messages.error(
                request,
                f'Your account does not have access to {tenant.name}. '
                f'Contact your administrator.',
            )
            # Abort the login. allauth catches this and returns the
            # response — the user stays anonymous.
            raise ImmediateHttpResponse(redirect('account_login'))

        return super().login(request, user)


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