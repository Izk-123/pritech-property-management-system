import pytest
from unittest.mock import patch
from decimal import Decimal
from apps.compliance.forex.models import ForexRate
from apps.compliance.forex.services import convert_to_mwk


@pytest.mark.django_db
class TestForex:
    def test_convert_usd_to_mwk(self):
        ForexRate.objects.create(
            base_currency='MWK', quote_currency='USD',
            rate=Decimal('1750.000000'),
            effective_from='2025-01-01T00:00:00Z',
        )
        amount, rate = convert_to_mwk(100, 'USD')
        assert amount == Decimal('175000.00')
        assert rate == Decimal('1750.000000')

    def test_convert_mwk_returns_same(self):
        amount, rate = convert_to_mwk(50000, 'MWK')
        assert amount == 50000
        assert rate == 1

    def test_no_rate_raises(self, db):
        with pytest.raises(ValueError):
            convert_to_mwk(100, 'EUR')