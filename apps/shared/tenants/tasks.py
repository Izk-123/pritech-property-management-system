from celery import shared_task
from django.utils import timezone


@shared_task
def heartbeat():
    """Runs every 15 minutes. Confirms the Celery worker is alive."""
    return f'ok at {timezone.now().isoformat()}'