"""
Consumer method decorators.

Use `@tenant_orm` on any consumer method that touches the ORM to
ensure the PostgreSQL search_path is set to the correct tenant
schema before the query runs.
"""
from functools import wraps

from channels.db import database_sync_to_async
from django.db import connection


def tenant_orm(func):
    """Ensure ORM calls in a consumer method run in the tenant schema."""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        tenant = self.scope.get('tenant')
        if tenant:
            await _set_schema(tenant.schema_name)
        return await func(self, *args, **kwargs)
    return wrapper


@database_sync_to_async
def _set_schema(schema_name):
    connection.set_schema(schema_name)