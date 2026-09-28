#apps/shared/tenants/views_health.py
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def health_check(request):
    """
    Comprehensive health check for uptime monitors.
    Returns 200 when all systems are go, 503 otherwise.
    """
    checks = {}
    status_code = 200

    # Database
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {type(e).__name__}'
        status_code = 503

    # Cache / Redis
    try:
        cache.set('__health_check', 'ok', 10)
        if cache.get('__health_check') == 'ok':
            checks['cache'] = 'ok'
        else:
            checks['cache'] = 'read mismatch'
            status_code = 503
    except Exception as e:
        checks['cache'] = f'error: {type(e).__name__}'
        status_code = 503

    # Celery broker
    try:
        from config.celery import app
        conn = app.connection()
        conn.ensure_connection(max_retries=1, timeout=2)
        checks['celery_broker'] = 'ok'
        conn.release()
    except Exception as e:
        checks['celery_broker'] = f'error: {type(e).__name__}'
        status_code = 503

    # Public tenant
    try:
        from django_tenants.utils import get_public_schema_name, get_tenant_model
        TenantModel = get_tenant_model()
        public = TenantModel.objects.get(schema_name=get_public_schema_name())
        checks['public_tenant'] = public.name
    except Exception as e:
        checks['public_tenant'] = f'error: {type(e).__name__}'
        status_code = 503

    return JsonResponse({
        'status': 'ok' if status_code == 200 else 'degraded',
        'checks': checks,
    }, status=status_code)