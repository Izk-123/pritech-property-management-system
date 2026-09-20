from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .services import generate_rbm_return
from apps.core.properties.models import Property


@shared_task
def generate_monthly_rbm_returns():
    """
    Generate RBM foreign currency returns for the previous month.
    Must be submitted by the 10th of the following month.
    """
    today = timezone.now().date()
    last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

    properties = Property.objects.filter(status='ACTIVE')
    total_returns = 0

    for prop in properties:
        returns = generate_rbm_return(prop.id, last_month)
        total_returns += len(returns)

    return f'Generated {total_returns} RBM returns for {last_month}'