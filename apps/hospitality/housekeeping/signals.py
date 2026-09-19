from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import HousekeepingTask
from apps.core.properties.models import Unit


@receiver(post_save, sender=HousekeepingTask)
def on_housekeeping_status_change(sender, instance, **kwargs):
    """
    Housekeeping completion → mark unit AVAILABLE.
    Inspection → also mark AVAILABLE (for properties that inspect).
    """
    if instance.status == HousekeepingTask.Status.COMPLETED:
        unit = instance.unit
        if unit.status == Unit.Status.CLEANING:
            unit.status = Unit.Status.AVAILABLE
            unit.save(update_fields=['status', 'updated_at'])

    elif instance.status == HousekeepingTask.Status.INSPECTED:
        unit = instance.unit
        if unit.status in (Unit.Status.CLEANING, Unit.Status.AVAILABLE):
            unit.status = Unit.Status.AVAILABLE
            unit.save(update_fields=['status', 'updated_at'])