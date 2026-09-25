"""
Auth event signal handlers.

These run automatically for every login, logout, and failed login.
No view code needs to change — this is the whole point of AZ-10.
"""
import logging

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AuthAuditLog, UserTenantMembership

logger = logging.getLogger(__name__)


def _client_ip(request):
    """Best-effort client IP from a request (handles X-Forwarded-For)."""
    if not request:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _user_agent(request):
    if not request:
        return ''
    return request.META.get('HTTP_USER_AGENT', '')[:1000]


def _tenant(request):
    """Return the current tenant object, or None."""
    return getattr(request, 'tenant', None)


# ── Login succeeded ─────────────────────────────────────────────────
@receiver(user_logged_in)
def on_login_success(sender, request, user, **kwargs):
    tenant = _tenant(request)
    ip = _client_ip(request)

    # Update last-login metadata on the user
    try:
        user.last_login_ip = ip
        if tenant and tenant.schema_name != 'public':
            user.last_tenant = tenant
        user.save(update_fields=['last_login_ip', 'last_tenant', 'updated_at'])
    except Exception:
        logger.exception('Failed to update last_login metadata')

    AuthAuditLog.objects.create(
        user=user,
        tenant=tenant if tenant and tenant.schema_name != 'public' else None,
        event_type=AuthAuditLog.EventType.LOGIN_SUCCESS,
        ip_address=ip,
        user_agent=_user_agent(request),
        details={
            'tenant_schema': tenant.schema_name if tenant else None,
            'session_key': getattr(request.session, 'session_key', None)
                if hasattr(request, 'session') else None,
        },
    )


# ── Logout ──────────────────────────────────────────────────────────
@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if not user:
        return
    tenant = _tenant(request)
    AuthAuditLog.objects.create(
        user=user,
        tenant=tenant if tenant and tenant.schema_name != 'public' else None,
        event_type=AuthAuditLog.EventType.LOGOUT,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        details={
            'tenant_schema': tenant.schema_name if tenant else None,
        },
    )


# ── Login failed ────────────────────────────────────────────────────
@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    tenant = _tenant(request)
    email = credentials.get('username') or credentials.get('email') or ''

    AuthAuditLog.objects.create(
        user=None,
        tenant=tenant if tenant and tenant.schema_name != 'public' else None,
        event_type=AuthAuditLog.EventType.LOGIN_FAILED,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        details={
            'attempted_email': str(email)[:255],
            'tenant_schema': tenant.schema_name if tenant else None,
        },
    )


# ── Membership changes ──────────────────────────────────────────────
@receiver(post_save, sender=UserTenantMembership)
def on_membership_change(sender, instance, created, **kwargs):
    """Log when a role is added or changed."""
    if not created:
        return
    AuthAuditLog.objects.create(
        user=instance.user,
        tenant=instance.tenant,
        event_type=AuthAuditLog.EventType.MEMBERSHIP_ADDED,
        details={
            'role': instance.role,
            'invited_by': instance.invited_by.email if instance.invited_by else None,
            'expires_at': instance.expires_at.isoformat() if instance.expires_at else None,
        },
    )