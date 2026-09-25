# apps/shared/tenants/middleware.py
from django.utils import translation


class TenantLanguageMiddleware:
    """Set the language from the tenant's preference if no user preference exists."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, 'tenant', None)
        if tenant and not request.session.get('_language'):
            default_lang = getattr(tenant, 'default_language', 'en')
            translation.activate(default_lang)
            request.LANGUAGE_CODE = default_lang
        return self.get_response(request)