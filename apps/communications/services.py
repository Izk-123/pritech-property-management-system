"""
Delivery services: WhatsApp Cloud API and email.
"""
import logging
from typing import Optional, Tuple

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# WhatsApp Cloud API
# ─────────────────────────────────────────────────────────────────────

class WhatsAppClient:
    """
    Client for Meta's WhatsApp Cloud API.

    Reads credentials from Django settings:
        WHATSAPP_PHONE_NUMBER_ID
        WHATSAPP_ACCESS_TOKEN
        WHATSAPP_API_VERSION

    All phone numbers must be E.164 without the leading '+'.
    """

    def __init__(self):
        self.phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
        self.token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
        self.version = getattr(settings, 'WHATSAPP_API_VERSION', 'v21.0')
        self.base_url = f'https://graph.facebook.com/{self.version}'

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

    def is_configured(self) -> bool:
        return bool(self.phone_id and self.token)

    def send_template(
        self,
        to: str,
        template_name: str,
        language: str = 'en',
        components: Optional[list] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Send an approved template message.

        Returns:
            (message_id, error) — one of these is None.
        """
        if not self.is_configured():
            return None, 'WhatsApp not configured'

        url = f'{self.base_url}/{self.phone_id}/messages'
        payload = {
            'messaging_product': 'whatsapp',
            'to': to,
            'type': 'template',
            'template': {
                'name': template_name,
                'language': {'code': language},
            },
        }
        if components:
            payload['template']['components'] = components

        try:
            resp = requests.post(
                url, headers=self._headers(), json=payload, timeout=20,
            )
        except requests.RequestException as exc:
            return None, f'Network error: {exc}'

        if resp.status_code >= 400:
            logger.error(
                f'WhatsApp send failed ({resp.status_code}): {resp.text}'
            )
            return None, resp.text

        data = resp.json()
        message_id = data.get('messages', [{}])[0].get('id')
        return message_id, None

    def send_text(
        self, to: str, body: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Send a free-form text. Only valid inside the 24-hour
        customer service window.
        """
        if not self.is_configured():
            return None, 'WhatsApp not configured'

        url = f'{self.base_url}/{self.phone_id}/messages'
        payload = {
            'messaging_product': 'whatsapp',
            'to': to,
            'type': 'text',
            'text': {'body': body, 'preview_url': False},
        }
        try:
            resp = requests.post(
                url, headers=self._headers(), json=payload, timeout=20,
            )
        except requests.RequestException as exc:
            return None, f'Network error: {exc}'

        if resp.status_code >= 400:
            return None, resp.text

        return resp.json().get('messages', [{}])[0].get('id'), None


# ─────────────────────────────────────────────────────────────────────
# Email
# ─────────────────────────────────────────────────────────────────────

def send_email(
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    from_email: Optional[str] = None,
    reply_to: Optional[list] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Send an email via the configured backend (Anymail → Mailgun/SES).

    Returns (success, error).
    """
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[to],
            reply_to=reply_to or [],
        )
        if html_body:
            msg.attach_alternative(html_body, 'text/html')
        msg.send(fail_silently=False)
        return True, None
    except Exception as exc:
        logger.exception(f'Email send failed to {to}')
        return False, str(exc)


# ─────────────────────────────────────────────────────────────────────
# Phone normalisation (Malawi)
# ─────────────────────────────────────────────────────────────────────

def normalise_mw_phone(raw: str) -> Optional[str]:
    """
    Convert a Malawian phone number to E.164 without the + sign.

    Accepts:
        0991234567     → 265991234567
        +265 99 123 4567 → 265991234567
        265991234567   → 265991234567
    """
    if not raw:
        return None
    digits = ''.join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return None
    if digits.startswith('265') and len(digits) == 12:
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return '265' + digits[1:]
    if len(digits) == 9:
        return '265' + digits
    return None