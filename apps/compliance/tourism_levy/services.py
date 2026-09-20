from django.db.models import Sum
from django.utils import timezone
from .models import TourismLevyConfig, TourismLevyRecord
from apps.hospitality.folios.models import Folio, FolioCharge


def apply_tourism_levy(folio: Folio):
    """
    Apply Tourism Levy to a folio's room charges.
    Called during night audit for each in-house reservation.
    """
    try:
        config = folio.reservation.property.levy_config
    except TourismLevyConfig.DoesNotExist:
        return None

    if not config.is_active:
        return None

    room_charges = folio.charges.filter(
        charge_type=FolioCharge.ChargeType.ROOM,
    ).aggregate(t=Sum('amount'))['t'] or 0

    if room_charges == 0:
        return None

    levy_amount = (room_charges * config.levy_percent) / 100

    # Add levy as a folio charge
    FolioCharge.objects.create(
        folio=folio,
        charge_type=FolioCharge.ChargeType.TOURISM_LEVY,
        description=f'Tourism Levy ({config.levy_percent}%)',
        amount=levy_amount,
        currency=folio.currency,
    )

    # Record for monthly remittance
    record = TourismLevyRecord.objects.create(
        folio=folio,
        property=folio.reservation.property,
        room_charge_amount=room_charges,
        levy_rate=config.levy_percent,
        levy_amount=levy_amount,
        period_month=timezone.now().date().replace(day=1),
    )

    return record