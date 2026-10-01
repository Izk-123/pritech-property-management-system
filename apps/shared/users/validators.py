"""
Malawi phone number validators and normalisers.

Supported input formats (all resolve to E.164 like +265991234567):
    0991234567
    0881234567
    0981234567
    +265991234567
    +265 99 123 4567
    265991234567

Supported carrier prefixes:
    088  → TNM
    098  → Airtel
    099  → Airtel

Landlines (01...) are rejected — we only accept mobile numbers
because SMS/WhatsApp verification requires a mobile line.
"""
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


# Mobile prefix (3 digits after country code): 88, 98, 99
_MOBILE_RE = re.compile(r'^\+265(88|98|99)\d{7}$')

# Loose input shapes we accept and normalise
_ALLOWED_PREFIXES = ('088', '098', '099')


def normalise_mw_phone(raw):
    """
    Return E.164 (+265XXXXXXXXX) for a Malawi mobile number, or None
    if the input cannot be normalised.
    """
    if not raw:
        return None

    digits = re.sub(r'\D', '', str(raw))

    if not digits:
        return None

    # Already has country code
    if digits.startswith('265') and len(digits) == 12:
        e164 = f'+{digits}'
        return e164 if _MOBILE_RE.match(e164) else None

    # Local format with leading zero: 0991234567 → 265991234567
    if len(digits) == 10 and digits.startswith('0'):
        if digits[:3] not in _ALLOWED_PREFIXES:
            return None
        e164 = f'+265{digits[1:]}'
        return e164 if _MOBILE_RE.match(e164) else None

    # Bare 9-digit form: 991234567 → 265991234567
    if len(digits) == 9:
        e164 = f'+265{digits}'
        return e164 if _MOBILE_RE.match(e164) else None

    return None


def validate_mw_phone(value):
    """Django validator for a single phone field."""
    if not value:
        return  # allow blank — field-level required= handles that

    normalised = normalise_mw_phone(value)
    if not normalised:
        raise ValidationError(
            _(
                'Enter a valid Malawi mobile number '
                '(e.g. 0991 234 567 or +265 99 123 4567).'
            ),
            code='invalid_mw_phone',
        )


def is_mobile_prefix(value):
    """True if the value starts with a known Malawi mobile prefix."""
    if not value:
        return False
    digits = re.sub(r'\D', '', str(value))
    if digits.startswith('265'):
        digits = digits[3:]
    elif digits.startswith('0'):
        digits = digits[1:]
    return digits[:2] in ('88', '98', '99')