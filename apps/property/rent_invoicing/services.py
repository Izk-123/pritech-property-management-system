from django.db import transaction
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from .models import RentInvoice, RentInvoiceLine, RentPayment
from apps.property.leases.models import Lease


@transaction.atomic
def generate_invoice_for_lease(lease, period_start, period_end, due_date):
    """Create a rent invoice for one billing period."""
    # Skip if a non-void invoice already exists for this period
    existing = lease.invoices.filter(
        period_start=period_start,
    ).exclude(status=RentInvoice.Status.VOID).exists()

    if existing:
        return None

    invoice = RentInvoice.objects.create(
        lease=lease,
        tenant=lease.tenant,
        unit=lease.unit,
        period_start=period_start,
        period_end=period_end,
        due_date=due_date,
        currency=lease.rent_currency,
    )

    # Base rent line
    RentInvoiceLine.objects.create(
        invoice=invoice,
        line_type=RentInvoiceLine.LineType.RENT,
        description=f'Monthly rent — {lease.unit.identifier}',
        amount=lease.rent_amount,
    )

    invoice.recalculate_totals()
    invoice.status = RentInvoice.Status.ISSUED
    invoice.save(update_fields=['status', 'updated_at'])

    return invoice


@transaction.atomic
def apply_late_fee(invoice):
    """Apply a late fee if the invoice is past its grace period."""
    if invoice.status in (RentInvoice.Status.PAID, RentInvoice.Status.VOID):
        return

    lease = invoice.lease
    grace_end = invoice.due_date + timedelta(days=lease.grace_period_days)
    if timezone.now().date() <= grace_end:
        return

    # Don't double-apply
    existing = invoice.lines.filter(
        line_type=RentInvoiceLine.LineType.LATE_FEE,
    ).exists()
    if existing:
        return

    if lease.late_fee_fixed > 0:
        fee = lease.late_fee_fixed
    elif lease.late_fee_percent > 0:
        fee = invoice.subtotal * (lease.late_fee_percent / 100)
    else:
        return

    RentInvoiceLine.objects.create(
        invoice=invoice,
        line_type=RentInvoiceLine.LineType.LATE_FEE,
        description=f'Late fee ({lease.grace_period_days}-day grace exceeded)',
        amount=fee,
    )

    invoice.late_fee = fee
    invoice.recalculate_totals()


@transaction.atomic
def record_payment(invoice, amount, method, reference='', user=None):
    """Record a payment against an invoice and recalculate status."""
    payment = RentPayment.objects.create(
        invoice=invoice,
        method=method,
        amount=amount,
        currency=invoice.currency,
        reference=reference,
        received_by=user,
    )
    invoice.recalculate_totals()
    return payment