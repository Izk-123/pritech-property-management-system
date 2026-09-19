from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Reservation
from apps.core.properties.models import Unit
from apps.hospitality.housekeeping.models import HousekeepingTask


@receiver(post_save, sender=Reservation)
def on_reservation_status_change(sender, instance, **kwargs):
    """
    Handle side effects of reservation status transitions.

    CHECKED_OUT → mark unit as CLEANING + create housekeeping task
    NO_SHOW → release the unit (no housekeeping needed)
    """
    if instance.status == Reservation.Status.CHECKED_OUT:
        for rr in instance.rooms.all():
            unit = rr.unit
            # Only transition if the unit is currently OCCUPIED
            if unit.status == Unit.Status.OCCUPIED:
                unit.status = Unit.Status.CLEANING
                unit.save(update_fields=['status', 'updated_at'])
                HousekeepingTask.objects.create(
                    unit=unit,
                    task_type=HousekeepingTask.TaskType.CHECKOUT_CLEAN,
                    priority=1,
                )
            rr.actual_check_out = timezone.now()
            rr.save(update_fields=['actual_check_out', 'updated_at'])

    elif instance.status == Reservation.Status.NO_SHOW:
        for rr in instance.rooms.all():
            unit = rr.unit
            if unit.status == Unit.Status.OCCUPIED:
                unit.status = Unit.Status.AVAILABLE
                unit.save(update_fields=['status', 'updated_at'])