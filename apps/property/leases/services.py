from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Lease, LeaseUnit
from apps.core.properties.models import Unit


class LeaseError(ValidationError):
    pass


@transaction.atomic
def activate_lease(lease, user=None):
    """Transition a lease from DRAFT/PENDING to ACTIVE and mark the unit occupied."""
    if lease.status not in (Lease.Status.DRAFT, Lease.Status.PENDING):
        raise LeaseError(
            f'Cannot activate a lease with status {lease.get_status_display()}.'
        )

    # Verify no other active lease exists for the same unit
    existing = Lease.objects.filter(
        unit=lease.unit,
        status=Lease.Status.ACTIVE,
    ).exclude(pk=lease.pk).exists()

    if existing:
        raise LeaseError(
            f'Unit {lease.unit.identifier} already has an active lease.'
        )

    lease.status = Lease.Status.ACTIVE
    lease.save(update_fields=['status', 'updated_at'])

    lease.unit.status = Unit.Status.OCCUPIED
    lease.unit.save(update_fields=['status', 'updated_at'])

    return lease


@transaction.atomic
def terminate_lease(lease, reason='', user=None):
    """Terminate an active lease and release the unit."""
    if lease.status != Lease.Status.ACTIVE:
        raise LeaseError('Only active leases can be terminated.')

    lease.status = Lease.Status.TERMINATED
    lease.save(update_fields=['status', 'updated_at'])

    lease.unit.status = Unit.Status.AVAILABLE
    lease.unit.save(update_fields=['status', 'updated_at'])

    return lease


@transaction.atomic
def renew_lease(old_lease, new_end_date, new_rent_amount=None, user=None):
    """
    Renew a lease: create a new lease, mark the old one RENEWED.
    Preserves the rental history chain.
    """
    if old_lease.status not in (Lease.Status.ACTIVE, Lease.Status.EXPIRED):
        raise LeaseError('Only active or expired leases can be renewed.')

    new_start = old_lease.end_date
    new_rent = new_rent_amount or old_lease.rent_amount

    # Apply escalation if configured and no explicit new amount
    if new_rent_amount is None and old_lease.escalation_percent > 0:
        new_rent = old_lease.rent_amount * (
            1 + old_lease.escalation_percent / 100
        )

    new_lease = Lease.objects.create(
        tenant=old_lease.tenant,
        unit=old_lease.unit,
        landlord=old_lease.landlord,
        status=Lease.Status.ACTIVE,
        start_date=new_start,
        end_date=new_end_date,
        rent_amount=new_rent,
        rent_currency=old_lease.rent_currency,
        payment_frequency=old_lease.payment_frequency,
        payment_due_day=old_lease.payment_due_day,
        escalation_percent=old_lease.escalation_percent,
        grace_period_days=old_lease.grace_period_days,
        late_fee_percent=old_lease.late_fee_percent,
        late_fee_fixed=old_lease.late_fee_fixed,
        created_by=user,
    )

    old_lease.status = Lease.Status.RENEWED
    old_lease.save(update_fields=['status', 'updated_at'])

    return new_lease