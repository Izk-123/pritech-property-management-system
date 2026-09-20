import logging
from django.utils import timezone
from .models import ForexRate

logger = logging.getLogger(__name__)


def fetch_and_cache_rates():
    """Fetch USD/MWK and EUR/MWK rates and cache them."""
    from pyxrate import converter

    client = converter.CurrencyConverter()

    for currency in ['USD', 'EUR']:
        try:
            rate = client.get_exchange_rate(currency, 'MWK')
            if rate:
                # Close previous rate
                ForexRate.objects.filter(
                    quote_currency=currency,
                    effective_to__isnull=True,
                ).update(effective_to=timezone.now())

                ForexRate.objects.create(
                    base_currency='MWK',
                    quote_currency=currency,
                    rate=rate,
                    source=ForexRate.Source.PYX_RATE,
                    effective_from=timezone.now(),
                )
                logger.info(f'Cached {currency}/MWK rate: {rate}')
        except Exception as e:
            logger.error(f'Failed to fetch {currency}/MWK rate: {e}')


def convert_to_mwk(amount, from_currency):
    """Convert an amount to MWK using the cached rate."""
    if from_currency == 'MWK':
        return amount, 1

    rate_obj = ForexRate.get_current_rate(from_currency)
    if not rate_obj:
        raise ValueError(f'No cached rate for {from_currency}/MWK')

    return amount * rate_obj.rate, rate_obj.rate