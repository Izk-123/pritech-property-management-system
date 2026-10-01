"""
Optional Veriphone lookup for phone validation.

Veriphone's free tier covers 1,000 lookups per month, which is plenty
for early-stage signups. Returns True if the number is a valid,
reachable mobile line. Never raises — always falls back to True on
network errors so signup is never blocked by a third-party outage.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def lookup(e164_number):
    api_key = getattr(settings, 'VERIPHONE_API_KEY', '')
    if not api_key:
        return True   # feature disabled — assume valid

    try:
        resp = requests.get(
            'https://api.veriphone.io/v2/verify',
            params={'phone': e164_number, 'key': api_key},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        # Veriphone returns status="success" and phone_valid=true
        # for a reachable mobile line.
        if data.get('status') != 'success':
            return True
        return bool(data.get('phone_valid'))
    except Exception as exc:
        logger.warning(f'Veriphone lookup failed for {e164_number}: {exc}')
        return True   # fail open — never block signup on API issues