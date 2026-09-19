from django.db import models
from apps.core.models import TimeStampedModel
from django.utils import timezone

class HousekeepingTask(TimeStampedModel):
    """A cleaning or inspection task for a unit."""

    class TaskType(models.TextChoices):
        CHECKOUT_CLEAN = 'CO', 'Check-out Cleaning'
        STAYOVER_CLEAN = 'SO', 'Stayover Cleaning'
        DEEP_CLEAN = 'DEEP', 'Deep Cleaning'
        INSPECTION = 'INSP', 'Inspection'

    class Status(models.TextChoices):
        PENDING = 'PEND', 'Pending'
        IN_PROGRESS = 'PROG', 'In Progress'
        COMPLETED = 'COMP', 'Completed'
        INSPECTED = 'INSP', 'Inspected'
        SKIPPED = 'SKIP', 'Skipped'

    unit = models.ForeignKey(
        'properties.Unit', on_delete=models.CASCADE,
        related_name='housekeeping_tasks',
    )
    task_type = models.CharField(max_length=5, choices=TaskType.choices)
    status = models.CharField(
        max_length=5, choices=Status.choices, default=Status.PENDING,
    )
    assigned_to = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='housekeeping_tasks',
    )
    priority = models.PositiveIntegerField(
        default=3, help_text='1 = Highest, 5 = Lowest',
    )
    notes = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    inspected_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inspected_tasks',
    )

    class Meta:
        ordering = ['priority', 'created_at']
        indexes = [
            models.Index(fields=['status', 'assigned_to']),
            models.Index(fields=['unit', 'status']),
        ]

    def __str__(self):
        return f'{self.get_task_type_display()} — {self.unit.identifier}'

    def save(self, *args, **kwargs):
        # Auto-timestamp transitions
        if self.status == self.Status.IN_PROGRESS and not self.started_at:
            self.started_at = timezone.now()
        if self.status in (self.Status.COMPLETED, self.Status.INSPECTED) \
                and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)