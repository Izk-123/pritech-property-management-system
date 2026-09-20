from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count
from .models import RBMReturn
from apps.hospitality.folios.models import FolioPayment


def generate_rbm_return(property_id, return_month):
    """Generate RBM return for a property and month."""
    # Get all foreign currency payments for the month
    next_month = (return_month.replace(day=1) + timedelta(days=32)).replace(day=1)

    fcy_payments = FolioPayment.objects.filter(
        folio__reservation__property_id=property_id,
        method__in=['CASH_USD', 'CARD'],
        currency__in=['USD', 'EUR'],
        created_at__gte=return_month,
        created_at__lt=next_month,
    ).values('currency').annotate(
        total=Sum('amount'),
        count=Count('id'),
    )

    returns = []
    for row in fcy_payments:
        rbm_return, created = RBMReturn.objects.get_or_create(
            property_id=property_id,
            return_month=return_month,
            currency=row['currency'],
            defaults={
                'total_receipts': row['total'],
                'net_foreign_currency': row['total'],
                'transaction_count': row['count'],
            },
        )
        returns.append(rbm_return)

    return returns