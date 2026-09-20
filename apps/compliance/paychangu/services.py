import hashlib
import hmac
import logging
from django.conf import settings
from django.utils import timezone
from .models import PayChanguTransaction

logger = logging.getLogger(__name__)


class PayChanguService:
    """Wrapper around the PayChangu API using the official Python SDK."""

    def __init__(self):
        from paychangu import PayChanguClient
        self.client = PayChanguClient(
            secret_key=settings.PAYCHANGU_SECRET_KEY,
        )

    def initiate_payment(self, amount, currency, email, first_name,
                         last_name, tx_ref, callback_url, return_url,
                         title='Payment', description=''):
        """
        Initiate a payment via PayChangu Standard Checkout.
        Returns (success: bool, checkout_url: str, tx_ref: str).
        """
        from paychangu.models.payment import Payment

        payment = Payment(
            amount=amount,
            currency=currency,
            email=email,
            first_name=first_name,
            last_name=last_name,
            callback_url=callback_url,
            return_url=return_url,
            tx_ref=tx_ref,
            customization={
                'title': title,
                'description': description,
            },
        )
        try:
            response = self.client.initiate_transaction(payment)
            data = response.get('data', {})
            return (
                True,
                data.get('checkout_url', ''),
                data.get('tx_ref', tx_ref),
            )
        except Exception as e:
            logger.error(f'PayChangu initiation failed: {e}')
            return False, '', tx_ref

    def verify_transaction(self, tx_ref):
        """Verify a transaction by reference."""
        try:
            response = self.client.verify_transaction(tx_ref)
            return True, response
        except Exception as e:
            logger.error(f'PayChangu verification failed: {e}')
            return False, {'error': str(e)}

    @staticmethod
    def verify_webhook_signature(payload, received_signature):
        """
        Verify webhook is from PayChangu.
        Uses SHA-256 HMAC of the payload with the web secret key.
        """
        secret = settings.PAYCHANGU_WEBHOOK_SECRET.encode()
        expected = hmac.new(
            secret,
            payload.encode() if isinstance(payload, str) else payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, received_signature)