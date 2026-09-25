from django.contrib import messages
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse

from .models import AuthAuditLog


class SchemaAwareLoginView(LoginView):
    """
    Login view that:
      1. Honours ?next= when safe.
      2. On the public schema  → redirects to public_home.
      3. On a tenant schema    → verifies the user has an active
         membership (or is a platform admin), then redirects to
         the front desk.

    Satisfies AU-03 (global auth, tenant-specific access) and AU-12
    (tenant resolved from subdomain).
    """
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        """
        Run Django's normal login, then check tenant membership.
        """
        response = super().form_valid(form)
        user = self.request.user
        tenant = getattr(self.request, 'tenant', None)

        # Public schema — nothing to check
        if not tenant or tenant.schema_name == 'public':
            return response

        # Platform admins bypass membership check
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
            # Log them back out and show a clear message
            from django.contrib.auth import logout
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