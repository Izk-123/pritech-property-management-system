from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count
from .models import TourismLevyRecord


@shared_task
def generate_monthly_levy_report():
    """
    Generate Tourism Levy remittance report for the previous month.
    Must be remitted by the 12th of the following month.
    """
    today = timezone.now().date()
    last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

    records = TourismLevyRecord.objects.filter(
        period_month=last_month,
        is_remitted=False,
    ).values('property__name').annotate(
        total_levy=Sum('levy_amount'),
        total_room_charges=Sum('room_charge_amount'),
        record_count=Count('id'),
    )

    # Return data for admin report view
    return {
        'period': str(last_month),
        'properties': list(records),
    }