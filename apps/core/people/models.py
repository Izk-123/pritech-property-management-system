from django.db import models
from apps.core.models import TimeStampedModel


class Person(TimeStampedModel):
    """A unified identity: guest, tenant, buyer, landlord, or staff."""

    class IDType(models.TextChoices):
        NATIONAL_ID = 'NATID', 'Malawi National ID'
        PASSPORT = 'PASS', 'Passport'
        DRIVER_LICENSE = 'DL', "Driver's License"

    class Language(models.TextChoices):
        ENGLISH = 'en', 'English'
        CHICHEWA = 'ny', 'Chichewa'

    full_name = models.CharField(max_length=255)
    id_type = models.CharField(max_length=10, choices=IDType.choices, blank=True)
    id_number = models.CharField(max_length=50, blank=True, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, default='Malawian')
    phone_primary = models.CharField(max_length=20, db_index=True)
    phone_secondary = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True, db_index=True)
    address = models.TextField(blank=True)
    district = models.CharField(max_length=100, blank=True)
    preferred_language = models.CharField(
        max_length=2, choices=Language.choices, default=Language.ENGLISH,
    )
    is_blacklisted = models.BooleanField(default=False)
    blacklist_reason = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'People'
        ordering = ['full_name']
        indexes = [
            models.Index(fields=['phone_primary']),
            models.Index(fields=['id_number']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return self.full_name


class PersonPropertyRole(TimeStampedModel):
    """Links a Person to a Property with a specific role."""

    class Role(models.TextChoices):
        GUEST = 'GUEST', 'Guest'
        TENANT = 'TENANT', 'Tenant'
        BUYER = 'BUYER', 'Buyer'
        LANDLORD = 'LANDLORD', 'Landlord'
        OWNER = 'OWNER', 'Property Owner'
        STAFF = 'STAFF', 'Staff Member'

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name='property_roles',
    )
    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='person_roles',
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['person', 'role']
        indexes = [
            models.Index(fields=['person', 'role']),
            models.Index(fields=['property', 'role']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F('start_date')) |
                          models.Q(end_date__isnull=True),
                name='person_role_end_after_start',
            ),
        ]

    def __str__(self):
        return f'{self.person.full_name} → {self.property.name} ({self.get_role_display()})'
    
from auditlog.registry import auditlog
auditlog.register(Person)
auditlog.register(PersonPropertyRole)