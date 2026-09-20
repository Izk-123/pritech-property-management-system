import os
from django.core.files.storage import FileSystemStorage


class TenantFileStorage(FileSystemStorage):
    """
    Prepends the current tenant's schema name to every stored file path:
        media/<schema_name>/<original_path>
    On the public schema, files go to media/public/.
    """

    def get_available_name(self, name, max_length=None):
        try:
            from django.db import connection
            tenant = getattr(connection, 'tenant', None)
            schema = tenant.schema_name if tenant else 'public'
        except Exception:
            schema = 'public'
        name = os.path.join(schema, name)
        return super().get_available_name(name, max_length)

    def _save(self, name, content):
        try:
            from django.db import connection
            tenant = getattr(connection, 'tenant', None)
            schema = tenant.schema_name if tenant else 'public'
        except Exception:
            schema = 'public'
        name = os.path.join(schema, name)
        return super()._save(name, content)