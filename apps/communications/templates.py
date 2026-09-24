"""
Small helper for building WhatsApp template component payloads.
"""
from typing import List


def body_components(*values) -> List[dict]:
    """
    Build a WhatsApp template body component.

    Meta's template API requires body parameters as a list of
    {'type': 'text', 'text': '...'} dicts, in the same order as the
    {{1}}, {{2}}, ... placeholders in the approved template.

    Example:
        body_components('John Doe', '50000', 'MWK')
        →
        [{'type': 'body', 'parameters': [
            {'type': 'text', 'text': 'John Doe'},
            {'type': 'text', 'text': '50000'},
            {'type': 'text', 'text': 'MWK'},
        ]}]
    """
    return [{
        'type': 'body',
        'parameters': [
            {'type': 'text', 'text': str(v)} for v in values
        ],
    }]