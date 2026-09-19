from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Reservation
from apps.hospitality.folios.models import FolioCharge
from apps.core.properties.models import Property


@shared_task
def run_night_audit(property_id):
    """
    Post one night's room charge to every in-house folio,
    then flag overdue confirmations as no-shows.
    """
    property = Property.objects.get(id=property_id)
    today = timezone.now().date()

    # Post room charges
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

    # Flag no-shows
    no_shows = Reservation.objects.filter(
        property=property,
        status=Reservation.Status.CONFIRMED,
        check_in__lt=today,
    )
    no_show_count = no_shows.count()
    no_shows.update(status=Reservation.Status.NO_SHOW)

    return (
        f'Night audit for {property.name}: '
        f'{posted} room charges posted, '
        f'{no_show_count} no-shows flagged.'
    )