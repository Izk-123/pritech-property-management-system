import hashlib
import hmac
import logging
import requests
from django.conf import settings
from django.utils import timezone
from .models import EISTerminal, EISInvoiceLog

logger = logging.getLogger(__name__)


class EISClient:
    """Client for the MRA Electronic Invoicing System API."""

    BASE_URL = getattr(
        settings, 'EIS_API_BASE_URL',
        'https://dev-eis-api.mra.mw/api/v1',
    )

    def __init__(self, terminal: EISTerminal):
        self.terminal = terminal
        self.headers = {
            'Authorization': (
                f'Bearer {terminal.config_data.get("access_token", "")}'
            ),
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def submit_invoice(self, invoice_data: dict):
        """
        Submit an invoice to MRA EIS.
        Returns (success: bool, response_data: dict).
        """
        try:
            response = requests.post(
                f'{self.BASE_URL}/sale/transaction',
                headers=self.headers,
                json=invoice_data,
                timeout=20,
            )
            if response.status_code == 200:
                data = response.json()
                # Check for shouldDownloadLatestConfig flag
                if data.get('data', {}).get('shouldDownloadLatestConfig'):
                    self.sync_configuration()
                return True, data
            return False, {
                'error': response.text,
                'status_code': response.status_code,
            }
        except requests.RequestException as e:
            logger.error(f'EIS submission failed: {e}')
            return False, {'error': str(e), 'offline': True}

    def sync_configuration(self):
        """
        Fetch latest configuration from MRA.
        Called daily and when shouldDownloadLatestConfig is true.
        """
        try:
            response = requests.get(
                f'{self.BASE_URL}/configuration/getLatestConfig',
                headers=self.headers,
                timeout=15,
            )
            if response.status_code == 200:
                data = response.json()
                self.terminal.config_data = data.get('data', {})
                self.terminal.last_config_sync = timezone.now()
                self.terminal.save(
                    update_fields=['config_data', 'last_config_sync', 'updated_at'],
                )
                logger.info(f'Config synced for {self.terminal.terminal_code}')
                return True
            return False
        except requests.RequestException as e:
            logger.error(f'EIS config sync failed: {e}')
            return False

    def generate_offline_hmac(self, invoice_number, line_count, transaction_date):
        """
        Generate HMAC for offline invoice QR code.
        Uses terminal-specific key provided by MRA during onboarding.
        """
        data = f'{invoice_number}{line_count}{transaction_date}'
        signature = hmac.new(
            self.terminal.offline_signing_key.encode(),
            data.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def ping(self):
        """Check if MRA EIS API is reachable."""
        try:
            response = requests.get(
                f'{self.BASE_URL}/utilities/ping',
                headers=self.headers,
                timeout=10,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False