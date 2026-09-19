from django.db import models
from apps.core.models import TimeStampedModel


class MaintenanceRequest(TimeStampedModel):
    """A maintenance issue logged against a unit."""

    class Category(models.TextChoices):
        PLUMBING = 'PLUMB', 'Plumbing'
        ELECTRICAL = 'ELEC', 'Electrical'
        STRUCTURAL = 'STRUC', 'Structural'
        APPLIANCE = 'APPL', 'Appliance'
        PEST = 'PEST', 'Pest Control'
        GENERAL = 'GEN', 'General'

    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MED', 'Medium'
        HIGH = 'HIGH', 'High'
        EMERGENCY = 'EMERG', 'Emergency'

    class Status(models.TextChoices):
        SUBMITTED = 'SUBM', 'Submitted'
        ACKNOWLEDGED = 'ACK', 'Acknowledged'
        IN_PROGRESS = 'PROG', 'In Progress'
        COMPLETED = 'COMP', 'Completed'
        VERIFIED = 'VER', 'Verified'
        CANCELLED = 'CANC', 'Cancelled'

    unit = models.ForeignKey(
        'properties.Unit', on_delete=models.CASCADE,
        related_name='maintenance_requests',
    )
    submitted_by = models.ForeignKey(
        'people.Person', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='maintenance_requests',
    )
    category = models.CharField(max_length=5, choices=Category.choices)
    priority = models.CharField(
        max_length=5, choices=Priority.choices, default=Priority.MEDIUM,
    )
    status = models.CharField(
        max_length=4, choices=Status.choices, default=Status.SUBMITTED,
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    assigned_to = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_maintenance',
    )
    assigned_to_name = models.CharField(
        max_length=255, blank=True,
        help_text='External contractor name (if not a platform user)',
    )
    parts_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    labour_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    total_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['unit', 'status']),
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['assigned_to', 'status']),
        ]

    def __str__(self):
        return f'{self.get_category_display()} — {self.unit.identifier}'

    def save(self, *args, **kwargs):
        self.total_cost = self.parts_cost + self.labour_cost

        if self.status == self.Status.ACKNOWLEDGED and not self.acknowledged_at:
            self.acknowledged_at = timezone.now()
        elif self.status == self.Status.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status == self.Status.VERIFIED and not self.verified_at:
            self.verified_at = timezone.now()

        super().save(*args, **kwargs)