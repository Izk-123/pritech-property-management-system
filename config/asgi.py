"""
ASGI entrypoint.

Django must be fully initialised before importing any app modules
that touch the ORM. That is why the app imports come after
django_asgi_app.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django_asgi_app = get_asgi_application()

# Imports below this line require Django apps to be loaded.
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from apps.realtime.middleware import TenantWSAuthMiddlewareStack  # noqa: E402
from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        TenantWSAuthMiddlewareStack(
            URLRouter(websocket_urlpatterns),
        ),
    ),
})