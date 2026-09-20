from celery import shared_task
from .services import fetch_and_cache_rates


@shared_task
def fetch_forex_rates():
    """Fetch and cache USD/MWK and EUR/MWK rates. Runs every 6 hours."""
    fetch_and_cache_rates()
    return 'Forex rates updated'