"""
Celery tasks for the reservations module.

All tasks are tenant-aware. When running from the public schema
(e.g., Celery Beat), use `run_night_audit_for_all_tenants`. When
running from inside a tenant schema, use `run_night_audit_for_property`.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Tenant-aware orchestration
# ─────────────────────────────────────────────────────────────────────

@shared_task
def run_night_audit_for_all_tenants():
    """
    Iterate over every active tenant and run the night audit for
    each of their active properties.

    Called by Celery Beat at 2 AM daily.
    """
    from django_tenants.utils import schema_context
    from apps.shared.tenants.models import Tenant

    tenants = Tenant.objects.filter(is_active=True).exclude(
        schema_name='public',
    )

    results = []
    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                from apps.core.properties.models import Property
                properties = Property.objects.filter(status='ACTIVE')

                for prop in properties:
                    try:
                        result = run_night_audit_for_property(prop.id)
                        results.append({
                            'tenant': tenant.schema_name,
                            'property': prop.name,
                            'result': result,
                        })
                    except Exception as e:
                        logger.exception(
                            f'Night audit failed for {tenant.schema_name} / {prop.name}: {e}'
                        )
                        results.append({
                            'tenant': tenant.schema_name,
                            'property': prop.name,
                            'error': str(e),
                        })
        except Exception as e:
            logger.exception(f'Night audit skipped tenant {tenant.schema_name}: {e}')
            results.append({
                'tenant': tenant.schema_name,
                'error': str(e),
            })

    return results


# ─────────────────────────────────────────────────────────────────────
# Per-property work (runs inside tenant schema)
# ─────────────────────────────────────────────────────────────────────

@shared_task
def run_night_audit_for_property(property_id):
    """
    Post one night's room charge to every in-house folio for a single
    property, apply Tourism Levy, and flag overdue confirmations as
    no-shows.

    Must be called from within a tenant schema context.
    """
    from apps.core.properties.models import Property
    from apps.hospitality.reservations.models import Reservation
    from apps.hospitality.folios.models import FolioCharge
    from apps.compliance.tourism_levy.services import apply_tourism_levy

    property = Property.objects.get(id=property_id)
    today = timezone.now().date()

    in_house = Reservation.objects.filter(
        property=property,
        status=Reservation.Status.CHECKED_IN,
    ).select_related('folio').prefetch_related('rooms__unit')

    posted = 0
    for reservation in in_house:
        folio = getattr(reservation, 'folio', None)
        if not folio or folio.status != 'OPEN':
            continue

        for rr in reservation.rooms.all():
            FolioCharge.objects.create(
                folio=folio,
                charge_type=FolioCharge.ChargeType.ROOM,
                description=f'Room charge — {rr.unit.identifier}',
                amount=rr.rate_per_night,
                currency=rr.rate_currency,
            )
            posted += 1

        # Apply Tourism Levy (1% of room charges)
        try:
            apply_tourism_levy(folio)
        except Exception as e:
            logger.exception(f'Levy application failed for folio {folio.pk}: {e}')

    # Flag overdue confirmations as no-shows
    no_shows = Reservation.objects.filter(
        property=property,
        status=Reservation.Status.CONFIRMED,
        check_in__lt=today,
    )
    no_show_count = no_shows.count()
    no_shows.update(status=Reservation.Status.NO_SHOW)

    return (
        f'{property.name}: {posted} room charges posted, '
        f'{no_show_count} no-shows flagged'
    )


# ─────────────────────────────────────────────────────────────────────
# Backwards compatibility
# ─────────────────────────────────────────────────────────────────────

@shared_task
def run_night_audit(property_id):
    """
    Legacy entry point. Kept for compatibility with existing scheduled
    tasks and manual calls. Delegates to `run_night_audit_for_property`.
    """
    return run_night_audit_for_property(property_id)