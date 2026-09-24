import pytest
from unittest.mock import patch
from apps.communications.tasks import send_payment_receipt_whatsapp


@pytest.mark.django_db
class TestWhatsAppReceipt:
    def test_queues_when_phone_valid(self, folio_payment):
        with patch('apps.communications.tasks.send_whatsapp_template.delay') as mock:
            result = send_payment_receipt_whatsapp(folio_payment.pk)
            assert result.startswith('queued:')
            mock.assert_called_once()

    def test_skips_when_no_phone(self, folio_payment):
        folio_payment.folio.reservation.primary_guest.phone_primary = ''
        folio_payment.folio.reservation.primary_guest.save()
        result = send_payment_receipt_whatsapp(folio_payment.pk)
        assert result == 'no-phone'

    @pytest.mark.parametrize('raw,expected', [
        ('0991234567', '265991234567'),
        ('+265991234567', '265991234567'),
        ('265991234567', '265991234567'),
        ('991234567', '265991234567'),
        ('garbage', None),
    ])
    def test_phone_normalisation(self, raw, expected):
        from apps.communications.tasks import _normalise_mw_phone
        assert _normalise_mw_phone(raw) == expected