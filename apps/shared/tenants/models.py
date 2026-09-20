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

    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.schema_name})'


class Domain(DomainMixin):
    """Maps a hostname to a tenant."""

    class Meta:
        ordering = ['domain']

    def __str__(self):
        return self.domain