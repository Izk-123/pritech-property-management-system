"""
Tenant-aware WebSocket middleware.

django-tenants' TenantMainMiddleware only handles HTTP requests.
WebSocket connections bypass it entirely, so we must resolve the
tenant from the hostname ourselves and set the PostgreSQL schema
before any ORM query runs inside a consumer.

Without this middleware, every ORM call in a consumer hits the
public schema and raises "relation does not exist" errors.
"""
import logging

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.auth import AuthMiddlewareStack
from django.db import connection
from django_tenants.utils import get_tenant_domain_model, get_public_schema_name

logger = logging.getLogger(__name__)


@database_sync_to_async
def _resolve_tenant(hostname):
    """
    Resolve a Tenant from a hostname.

    Falls back to the public tenant if no domain matches. Returns
    None only if even the public tenant is missing — which means
    the database hasn't been seeded yet.
    """
    DomainModel = get_tenant_domain_model()

    # Exact match first
    try:
        return DomainModel.objects.select_related('tenant').get(
            domain=hostname,
        ).tenant
    except DomainModel.DoesNotExist:
        pass

    # Fall back to the public tenant
    try:
        return DomainModel.objects.select_related('tenant').get(
            tenant__schema_name=get_public_schema_name(),
            is_primary=True,
        ).tenant
    except DomainModel.DoesNotExist:
        logger.error(f'No tenant found for hostname "{hostname}"')
        return None


class TenantWSMiddleware(BaseMiddleware):
    """
    Resolves the tenant from the WebSocket hostname and attaches it
    to scope['tenant']. Also caches the tenant schema in
    scope['tenant_schema'] for fast access in consumers.
    """

    async def __call__(self, scope, receive, send):
        # Extract the hostname header. ASGI gives headers as a list
        # of (name, value) byte tuples.
        headers = dict(scope.get('headers', []))
        host = headers.get(b'host', b'').decode('utf-8', errors='ignore')
        hostname = host.split(':')[0].strip().lower()

        if not hostname:
            scope['tenant'] = None
            scope['tenant_schema'] = None
            return await super().__call__(scope, receive, send)

        tenant = await _resolve_tenant(hostname)

        scope['tenant'] = tenant
        scope['tenant_schema'] = tenant.schema_name if tenant else None

        if tenant:
            await self._set_schema(tenant.schema_name)

        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def _set_schema(self, schema_name):
        connection.set_schema(schema_name)


def TenantWSAuthMiddlewareStack(inner):
    """
    Compose tenant resolution with Django's auth stack.

    Order matters: tenant first, then auth. The auth middleware
    loads the session, which may query tenant-scoped tables
    (e.g. audit log entries from previous requests).
    """
    return TenantWSMiddleware(AuthMiddlewareStack(inner))