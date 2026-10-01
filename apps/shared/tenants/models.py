"""
Tenant and Domain models — live in the PUBLIC schema.

Tenant is the client organisation. django-tenants creates a
PostgreSQL schema per Tenant. Domain maps a hostname to a Tenant.

Phase 9.1 adds a ``modules`` JSONField so each tenant can declare
which business modules they use (Hospitality, Property Sales,
Property Rentals). This drives conditional navigation and — later —
feature gating in the UI.
"""
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Tenant(TenantMixin):
    """
    Represents a client organization (hotel group, lodge, property manager).
    Each tenant gets its own PostgreSQL schema.
    """
    name = models.CharField(max_length=255)
    schema_name = models.CharField(max_length=63, unique=True)

    class Plan(models.TextChoices):
        STARTER = 'STARTER', 'Starter'
        PROFESSIONAL = 'PRO', 'Professional'
        ENTERPRISE = 'ENT', 'Enterprise'

    class Module(models.TextChoices):
        """
        Which business modules this tenant uses.

        Selected at signup, changeable by the platform admin later.
        Not every tenant runs all three — a hotel doesn't need
        lease management, a landlord doesn't need housekeeping.
        """
        HOSPITALITY     = 'HOSPITALITY',     'Hospitality (Hotel / Lodge)'
        PROPERTY_SALES  = 'PROPERTY_SALES',  'Property Sales'
        PROPERTY_RENTALS = 'PROPERTY_RENTALS', 'Property Rentals'

    plan = models.CharField(
        max_length=10, choices=Plan.choices, default=Plan.STARTER,
    )
    is_active = models.BooleanField(default=True)
    paid_until = models.DateField(null=True, blank=True)
    on_trial = models.BooleanField(default=True)
    contact_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    default_language = models.CharField(
        max_length=5,
        choices=[('en', 'English'), ('ny', 'Chichewa')],
        default='en',
        help_text='Default UI language for this tenant',
    )

    # ─── Phase 9.1 — enabled business modules ─────────────────────
    modules = models.JSONField(
        default=list,
        blank=True,
        help_text='Enabled modules for this tenant',
    )

    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.schema_name})'

    # ─── Module helpers ──────────────────────────────────────────
    @property
    def has_hospitality(self):
        return self.Module.HOSPITALITY in (self.modules or [])

    @property
    def has_sales(self):
        return self.Module.PROPERTY_SALES in (self.modules or [])

    @property
    def has_rentals(self):
        return self.Module.PROPERTY_RENTALS in (self.modules or [])

    @property
    def has_property_module(self):
        """Either sales or rentals — used to gate the Property nav."""
        return self.has_sales or self.has_rentals


class Domain(DomainMixin):
    """Maps a hostname to a tenant."""

    class Meta:
        ordering = ['domain']

    def __str__(self):
        return self.domain