"""
Real-time WebSocket consumers.

Every consumer is tenant-scoped: the group name embeds the tenant
schema so a message broadcast to Lakeview's room board never
reaches Sunbird's browsers.

Authentication is enforced through Channels' AuthMiddlewareStack
(see config/asgi.py). Anonymous users are rejected.
"""
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.db import connection

from .utils import group_name

logger = logging.getLogger(__name__)


class BaseTenantConsumer(AsyncWebsocketConsumer):
    """Shared plumbing for tenant-scoped consumers."""

    async def _setup(self):
        """
        Resolve the tenant, verify authentication, and join the
        consumer's group. Returns True on success, False on failure
        (in which case the connection has already been closed).
        """
        self.tenant = self.scope.get('tenant')
        if not self.tenant:
            await self.close(code=4001)
            return False

        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4003)
            return False

        self.schema = self.tenant.schema_name
        self.group = self.group_name()

        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        return True

    def group_name(self):
        """Override in subclasses to define the group."""
        raise NotImplementedError

    async def _teardown(self):
        if hasattr(self, 'group'):
            await self.channel_layer.group_discard(
                self.group, self.channel_name,
            )

    @database_sync_to_async
    def _set_schema(self):
        connection.set_schema(self.schema)

    async def receive(self, text_data=None, bytes_data=None):
        """
        Handle client-to-server messages.

        Only `ping` is supported by default. Subclasses can override
        to handle application-specific messages.
        """
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if payload.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))


class NotificationConsumer(BaseTenantConsumer):
    """
    Per-user notification stream.

    URL: ws://host/ws/notifications/

    Each user joins a personal group. Booking confirmations, payment
    receipts, and system alerts are sent to this group only.
    """

    def group_name(self):
        return group_name(f'user_{self.user.id}', self.schema)

    async def connect(self):
        await self._setup()

    async def disconnect(self, close_code):
        await self._teardown()

    async def notify(self, event):
        """Receive a group_send and forward to the client."""
        await self.send(text_data=json.dumps(event['data']))


class RoomStatusConsumer(BaseTenantConsumer):
    """
    Live room-status board for housekeeping and front desk.

    URL: ws://host/ws/rooms/

    Broadcasts whenever a housekeeping task or unit status changes.
    """

    def group_name(self):
        return group_name('rooms', self.schema)

    async def connect(self):
        await self._setup()

    async def disconnect(self, close_code):
        await self._teardown()

    async def room_update(self, event):
        await self.send(text_data=json.dumps(event['data']))


class FrontDeskConsumer(BaseTenantConsumer):
    """
    Live front-desk stream: arrivals, departures, in-house count,
    payment notifications.

    URL: ws://host/ws/front-desk/
    """

    def group_name(self):
        return group_name('frontdesk', self.schema)

    async def connect(self):
        await self._setup()

    async def disconnect(self, close_code):
        await self._teardown()

    async def frontdesk_update(self, event):
        await self.send(text_data=json.dumps(event['data']))


class PropertyBoardConsumer(BaseTenantConsumer):
    """
    Live property-management stream for lease and invoice changes.

    URL: ws://host/ws/property/
    """

    def group_name(self):
        return group_name('property', self.schema)

    async def connect(self):
        await self._setup()

    async def disconnect(self, close_code):
        await self._teardown()

    async def property_update(self, event):
        await self.send(text_data=json.dumps(event['data']))