"""
User model — lives in the PUBLIC schema.

Design notes
------------
* One user can belong to many tenants (see UserTenantMembership).
* The email field is the login identifier; username is kept for
  Django admin compatibility but is not used for auth.
* Every field added after the initial migration is nullable or has
  a default so `migrate_schemas --shared` can run on existing data
  without prompting.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Global user identity, tenant-agnostic."""

    class Gender(models.TextChoices):
        MALE = 'M', _('Male')
        FEMALE = 'F', _('Female')

    class PreferredLanguage(models.TextChoices):
        ENGLISH = 'en', _('English')
        CHICHEWA = 'ny', _('Chichewa')

    # ── Identity ─────────────────────────────────────────────────
    # Override AbstractUser.first_name to relax max_length to 150
    # for consistency with last_name.
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    middle_name = models.CharField(
        _('middle name'), max_length=150, blank=True,
        help_text=_('Optional — common in Malawi naming conventions'),
    )
    last_name = models.CharField(_('last name'), max_length=150, blank=True)

    email = models.EmailField(_('email address'), unique=True)

    date_of_birth = models.DateField(
        _('date of birth'), null=True, blank=True,
    )
    gender = models.CharField(
        _('gender'), max_length=1, choices=Gender.choices, blank=True,
    )
    national_id = models.CharField(
        _('national ID'), max_length=50, blank=True,
        help_text=_('Malawi National ID or passport number'),
    )
    avatar = models.ImageField(
        upload_to='avatars/%Y/%m/', null=True, blank=True,
    )

    # ── Contact ──────────────────────────────────────────────────
    phone = models.CharField(_('primary phone'), max_length=20, blank=True)
    alternate_phone = models.CharField(
        _('alternate phone'), max_length=20, blank=True,
    )

    # ── Address ──────────────────────────────────────────────────
    address_line1 = models.CharField(
        _('address line 1'), max_length=255, blank=True,
    )
    address_line2 = models.CharField(
        _('address line 2'), max_length=255, blank=True,
    )
    city = models.CharField(_('city / town'), max_length=100, blank=True)
    district = models.CharField(
        _('district'), max_length=100, blank=True,
        help_text=_('e.g. Lilongwe, Blantyre, Mzuzu'),
    )
    country = models.CharField(
        _('country'), max_length=100, default='Malawi',
    )

    # ── Preferences ──────────────────────────────────────────────
    preferred_language = models.CharField(
        _('preferred language'),
        max_length=5,
        choices=PreferredLanguage.choices,
        default=PreferredLanguage.ENGLISH,
    )
    timezone = models.CharField(
        _('timezone'), max_length=50, default='Africa/Blantyre',
    )

    # ── Platform role ────────────────────────────────────────────
    is_platform_admin = models.BooleanField(
        _('platform admin'),
        default=False,
        help_text=_('Can manage all tenants. Bypasses tenant membership checks.'),
    )

    # ── Cross-tenant metadata ────────────────────────────────────
    last_tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='last_users',
        help_text=_('Tenant the user last accessed — used for post-login redirect'),
    )
    last_login_ip = models.GenericIPAddressField(
        null=True, blank=True,
    )

    # ── Timestamps ───────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_platform_admin', 'is_active']),
        ]

    def __str__(self):
        return self.email

    # ── Convenience properties ───────────────────────────────────
    @property
    def full_name(self):
        """Return the best-available display name."""
        parts = [self.first_name, self.middle_name, self.last_name]
        composed = ' '.join(p for p in parts if p).strip()
        return composed or self.email

    @property
    def short_name(self):
        """First name only, for compact UI (greeting, avatar)."""
        return self.first_name or self.email.split('@')[0]

    def get_full_name(self):
        """Override Django's built-in — we want middle_name included."""
        return self.full_name

    def get_short_name(self):
        return self.short_name

    # ── Tenant helpers ───────────────────────────────────────────
    def tenants(self):
        """Return the tenants this user has an active membership in."""
        from django_tenants.utils import get_tenant_model
        TenantModel = get_tenant_model()
        return TenantModel.objects.filter(
            user_memberships__user=self,
            user_memberships__is_active=True,
        )

    def has_membership(self, tenant):
        """Does this user have an active membership in `tenant`?"""
        if self.is_platform_admin or self.is_superuser:
            return True
        return self.tenant_memberships.filter(
            tenant=tenant, is_active=True,
        ).exists()

    def role_in(self, tenant):
        """Return the role string in `tenant`, or None."""
        membership = self.tenant_memberships.filter(
            tenant=tenant, is_active=True,
        ).first()
        return membership.role if membership else None
    
# ─────────────────────────────────────────────────────────────────────
# Multi-tenant RBAC
# ─────────────────────────────────────────────────────────────────────

class UserTenantMembership(models.Model):
    """
    Links a User to a Tenant with a specific role.

    Satisfies AZ-01 (RBAC), AU-03 (tenant-specific access).
    A user can be a Manager in Tenant A and Read-Only in Tenant B.
    """

    class Role(models.TextChoices):
        TENANT_ADMIN   = 'TADMIN', _('Tenant Administrator')
        MANAGER        = 'MGR',    _('Manager')
        FRONT_DESK     = 'FD',     _('Front Desk')
        HOUSEKEEPER    = 'HK',     _('Housekeeper')
        ACCOUNTANT     = 'ACC',    _('Accountant')
        MAINTENANCE    = 'MNT',    _('Maintenance')
        PROPERTY_AGENT = 'AGT',    _('Property Agent')
        READ_ONLY      = 'RO',     _('Read Only')

    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='tenant_memberships',
    )
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='user_memberships',
    )
    role = models.CharField(max_length=6, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    joined_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text=_('For temporary access. Leave blank for permanent.'),
    )
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invited_memberships',
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('user tenant membership')
        verbose_name_plural = _('user tenant memberships')
        # One active role per user per tenant (change the role, don't add another row)
        unique_together = [('user', 'tenant')]
        indexes = [
            models.Index(fields=['user', 'tenant', 'is_active']),
            models.Index(fields=['tenant', 'role', 'is_active']),
        ]

    def __str__(self):
        return f'{self.user.email} → {self.tenant.name} ({self.get_role_display()})'

    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.expires_at


# ─────────────────────────────────────────────────────────────────────
# Auth audit log — AZ-10
# ─────────────────────────────────────────────────────────────────────

class AuthAuditLog(models.Model):
    """
    Audit trail of every authentication and authorization event.

    Written by signal handlers in apps/shared/users/signals.py.
    Read-only in admin. Never deleted by application code.
    """

    class EventType(models.TextChoices):
        LOGIN_SUCCESS       = 'LOGIN_OK',   _('Login Success')
        LOGIN_FAILED        = 'LOGIN_FAIL', _('Login Failed')
        LOGOUT              = 'LOGOUT',     _('Logout')
        PASSWORD_RESET      = 'PWD_RESET',  _('Password Reset Requested')
        PASSWORD_CHANGED    = 'PWD_CHG',    _('Password Changed')
        MFA_ENABLED         = 'MFA_ON',     _('MFA Enabled')
        MFA_DISABLED        = 'MFA_OFF',    _('MFA Disabled')
        TOKEN_REFRESH       = 'TOKEN_REF',  _('Token Refreshed')
        PERMISSION_DENIED   = 'PERM_DENY',  _('Permission Denied')
        ROLE_CHANGED        = 'ROLE_CHG',   _('Role Changed')
        MEMBERSHIP_ADDED    = 'MEMB_ADD',   _('Membership Added')
        MEMBERSHIP_REMOVED  = 'MEMB_DEL',   _('Membership Removed')

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='auth_logs',
    )
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='auth_logs',
    )
    event_type = models.CharField(max_length=10, choices=EventType.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('auth audit log')
        verbose_name_plural = _('auth audit logs')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'event_type', 'created_at']),
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['event_type', 'created_at']),
        ]

    def __str__(self):
        who = self.user.email if self.user else '(anonymous)'
        return f'{who} · {self.get_event_type_display()} · {self.created_at:%Y-%m-%d %H:%M}'