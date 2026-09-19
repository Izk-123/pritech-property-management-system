from celery import shared_task
from django.utils import timezone
from datetime import date, timedelta
from apps.property.leases.models import Lease
from .services import generate_invoice_for_lease, apply_late_fee
from .models import RentInvoice


@shared_task
def generate_monthly_rent_invoices():
    """
    Runs on the 1st of each month.
    Creates rent invoices for all active leases.
    """
    today = timezone.now().date()
    period_start = today.replace(day=1)
    # End of month: first day of next month minus one day
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    period_end = next_month - timedelta(days=1)

    active_leases = Lease.objects.filter(
        status=Lease.Status.ACTIVE,
        start_date__lte=period_start,
        end_date__gte=period_start,
    ).exclude(
        rent_free_until__gte=period_start,
    ).select_related('tenant', 'unit')

    created = 0
    for lease in active_leases:
        due_date = period_start.replace(day=lease.payment_due_day)
        invoice = generate_invoice_for_lease(
            lease, period_start, period_end, due_date,
        )
        if invoice:
            created += 1

    return f'Generated {created} rent invoices for {period_start}'


@shared_task
def apply_overdue_late_fees():
    """
    Runs daily. Applies late fees to overdue invoices past their grace period.
    """
    today = timezone.now().date()
    overdue = RentInvoice.objects.filter(
        status__in=[RentInvoice.Status.ISSUED, RentInvoice.Status.PARTIAL],
        due_date__lt=today,
    ).select_related('lease')

    applied = 0
    for invoice in overdue:
        before = invoice.late_fee
        apply_late_fee(invoice)
        invoice.refresh_from_db()
        if invoice.late_fee > before:
            applied += 1

    return f'Applied {applied} late fees'


@shared_task
def flag_overdue_invoices():
    """Runs daily. Marks issued/partial invoices as OVERDUE if past due date."""
    today = timezone.now().date()
    updated = RentInvoice.objects.filter(
        status__in=[RentInvoice.Status.ISSUED, RentInvoice.Status.PARTIAL],
        due_date__lt=today,
    ).update(status=RentInvoice.Status.OVERDUE)
    return f'Flagged {updated} invoices as overdue'