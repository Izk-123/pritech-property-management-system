import pytest
from channels.testing import WebsocketCommunicator
from config.asgi import application


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestNotificationConsumer:
    async def test_rejects_unauthenticated(self, tenant_a):
        communicator = WebsocketCommunicator(
            application,
            '/ws/notifications/',
            headers=[(b'host', tenant_a.domains.first().domain.encode())],
        )
        connected, _ = await communicator.connect()
        assert not connected

    async def test_authenticated_user_connects(self, tenant_a, user_a):
        communicator = WebsocketCommunicator(
            application,
            '/ws/notifications/',
            headers=[(b'host', tenant_a.domains.first().domain.encode())],
        )
        # Inject user into scope — real code uses AuthMiddlewareStack
        communicator.scope['user'] = user_a

        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()