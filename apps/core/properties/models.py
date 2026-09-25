from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from apps.core.models import TimeStampedModel


class Amenity(models.Model):
    """A feature or service available at a property or unit."""

    class Category(models.TextChoices):
        ROOM = 'ROOM', 'Room Feature'
        PROPERTY = 'PROPERTY', 'Property Feature'
        SERVICE = 'SERVICE', 'Service'

    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True,
                            help_text='CSS icon class or Material Symbol name')
    category = models.CharField(max_length=10, choices=Category.choices)

    class Meta:
        verbose_name_plural = 'Amenities'
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class Property(TimeStampedModel):
    """A physical property: hotel, lodge, rental building, or standalone house."""

    class PropertyType(models.TextChoices):
        HOTEL = 'HOTEL', 'Hotel'
        LODGE = 'LODGE', 'Lodge'
        RENTAL_BUILDING = 'RENTAL', 'Rental Building'
        STANDALONE_HOUSE = 'HOUSE', 'Standalone House'
        MIXED_USE = 'MIXED', 'Mixed Use'

    class Region(models.TextChoices):
        NORTH = 'NORTH', 'Northern'
        CENTRAL = 'CENTRAL', 'Central'
        SOUTH = 'SOUTH', 'Southern'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        MAINTENANCE = 'MAINT', 'Under Maintenance'
        COMING_SOON = 'SOON', 'Coming Soon'

    name = models.CharField(max_length=255)
    property_type = models.CharField(max_length=10, choices=PropertyType.choices)
    address = models.TextField()
    district = models.CharField(max_length=100)
    region = models.CharField(max_length=10, choices=Region.choices)
    gps_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
    )
    gps_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
    )
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE,
    )

    class Meta:
        verbose_name_plural = 'Properties'
        ordering = ['name']
        indexes = [
            models.Index(fields=['property_type', 'status']),
            models.Index(fields=['district', 'region']),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_property_type_display()})'


class Unit(TimeStampedModel):
    """A bookable or rentable unit within a property."""

    class UnitType(models.TextChoices):
        ROOM = 'ROOM', 'Hotel Room'
        CHALET = 'CHALET', 'Lodge Chalet'
        APARTMENT = 'APT', 'Apartment'
        HOUSE = 'HOUSE', 'House'
        BED = 'BED', 'Bed (Dormitory)'

    class Status(models.TextChoices):
        AVAILABLE = 'AVAIL', 'Available'
        OCCUPIED = 'OCC', 'Occupied'
        CLEANING = 'CLEAN', 'Cleaning'
        MAINTENANCE = 'MAINT', 'Maintenance'
        BLOCKED = 'BLOCK', 'Blocked'
        SOLD = 'SOLD', 'Sold'

    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='units',
    )
    unit_type = models.CharField(max_length=10, choices=UnitType.choices)
    identifier = models.CharField(
        max_length=50, help_text='e.g., "Room 101", "Chalet A"',
    )
    floor = models.CharField(max_length=20, blank=True)
    capacity_adults = models.PositiveIntegerField(default=2)
    capacity_children = models.PositiveIntegerField(default=0)
    bed_count = models.PositiveIntegerField(default=1)
    amenities = models.ManyToManyField(Amenity, blank=True)
    base_rate_mwk = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    base_rate_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    status = models.CharField(
        max_length=6, choices=Status.choices, default=Status.AVAILABLE,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'Units'
        ordering = ['property', 'identifier']
        unique_together = [('property', 'identifier')]
        indexes = [
            models.Index(fields=['property', 'unit_type', 'status']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(capacity_adults__gte=1),
                name='unit_capacity_adults_gte_1',
            ),
            models.CheckConstraint(
                condition=models.Q(bed_count__gte=1),
                name='unit_bed_count_gte_1',
            ),
        ]

    def __str__(self):
        return f'{self.identifier} — {self.property.name}'


class StaffPropertyAssignment(models.Model):
    """
    Assigns a User to one or more properties within the current tenant.

    Lives in the TENANT schema (properties app is a TENANT_APP).
    References public.shared_users.User — cross-schema FK from tenant
    to public works because public is on the tenant's search_path.

    Satisfies AZ-02 (property-level scoping).
    """
    user = models.ForeignKey(
        'shared_users.User',
        on_delete=models.CASCADE,
        related_name='property_assignments',
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='staff_assignments',
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        'shared_users.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='property_assignments_made',
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _('staff property assignment')
        verbose_name_plural = _('staff property assignments')
        unique_together = [('user', 'property')]
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['property', 'is_active']),
        ]

    def __str__(self):
        return f'{self.user.email} → {self.property.name}'

from auditlog.registry import auditlog
auditlog.register(Property)
auditlog.register(Unit)