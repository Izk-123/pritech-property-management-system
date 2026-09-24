"""
ASGI URL patterns for WebSocket connections.

These are mounted in config/asgi.py — NOT in Django's urls.py.
"""
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/notifications/$',
            consumers.NotificationConsumer.as_asgi()),
    re_path(r'^ws/rooms/$',
            consumers.RoomStatusConsumer.as_asgi()),
    re_path(r'^ws/front-desk/$',
            consumers.FrontDeskConsumer.as_asgi()),
    re_path(r'^ws/property/$',
            consumers.PropertyBoardConsumer.as_asgi()),
]