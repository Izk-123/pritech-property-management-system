"""
Helpers for building tenant-scoped group names and broadcasting.
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connection

logger = logging.getLogger(__name__)


def current_tenant_schema():
    """Return the schema_name of the active tenant, or None."""
    tenant = getattr(connection, 'tenant', None)
    return tenant.schema_name if tenant else None


def group_name(kind, schema=None):
    """
    Build a canonical group name.

    Examples:
        group_name('rooms')                → 'tenant_lakeview_rooms'
        group_name('user_42')              → 'tenant_lakeview_user_42'
        group_name('rooms', 'sunbird')     → 'tenant_sunbird_rooms'
    """
    schema = schema or current_tenant_schema()
    if not schema:
        raise ValueError('No active tenant schema; cannot build group name')
    return f'tenant_{schema}_{kind}'


def broadcast(group, message_type, data):
    """
    Fire-and-forget send to a WebSocket group.

    Safe to call from synchronous code (Django signals, view methods,
    Celery tasks). Uses async_to_sync under the hood.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning(f'No channel layer; dropping broadcast to {group}')
        return
    try:
        async_to_sync(channel_layer.group_send)(group, {
            'type': message_type,
            'data': data,
        })
    except Exception:
        logger.exception(f'Broadcast to {group} failed')


def broadcast_to_tenant(kind, message_type, data, schema=None):
    """Broadcast to a tenant-scoped group by kind."""
    try:
        group = group_name(kind, schema)
    except ValueError:
        return
    broadcast(group, message_type, data)