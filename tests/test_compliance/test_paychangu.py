import pytest
import hmac
import hashlib
from django.conf import settings
from apps.compliance.paychangu.services import PayChanguService


class TestPayChanguWebhook:
    def test_valid_signature(self):
        payload = b'{"tx_ref":"abc","status":"successful"}'
        secret = b'test-secret'
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(settings, 'PAYCHANGU_WEBHOOK_SECRET', 'test-secret')
            expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
            assert PayChanguService.verify_webhook_signature(
                payload.decode(), expected,
            )

    def test_invalid_signature(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(settings, 'PAYCHANGU_WEBHOOK_SECRET', 'test-secret')
            assert not PayChanguService.verify_webhook_signature(
                '{"tx_ref":"abc"}', 'wrong-signature',
            )