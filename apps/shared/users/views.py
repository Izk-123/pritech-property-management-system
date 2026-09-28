from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit

from .models import AuthAuditLog


class SchemaAwareLoginView(LoginView):
    """
    Login view with tenant awareness, membership check, and rate limiting.

    Satisfies AU-03 (tenant-specific access), AU-12 (tenant from subdomain),
    AU-15 (rate limiting).
    """
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    @method_decorator(
        ratelimit(key='ip', rate='5/m', method='POST', block=True),
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        tenant = getattr(self.request, 'tenant', None)

        # Public schema — no membership check needed
        if not tenant or tenant.schema_name == 'public':
            return response

        # Platform admins bypass membership
        if user.is_platform_admin or user.is_superuser:
            return response

        # Tenant schema — require an active membership
        if not user.has_membership(tenant):
            AuthAuditLog.objects.create(
                user=user,
                tenant=tenant,
                event_type=AuthAuditLog.EventType.PERMISSION_DENIED,
                details={
                    'reason': 'no_membership_for_tenant',
                    'tenant_schema': tenant.schema_name,
                },
            )
            logout(self.request)
            messages.error(
                self.request,
                f'Your account does not have access to {tenant.name}. '
                f'Contact your administrator.',
            )
            return redirect('login')

        return response

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to

        tenant = getattr(self.request, 'tenant', None)

        if not tenant or tenant.schema_name == 'public':
            return reverse('public_home')

        try:
            return reverse('reservations:front_desk')
        except NoReverseMatch:
            return reverse('home')


def ratelimited_view(request, exception=None):
    """Returned by django-ratelimit when a rate limit is exceeded."""
    return HttpResponse(
        'Too many requests. Please wait a minute and try again.',
        status=429,
        content_type='text/plain',
    )