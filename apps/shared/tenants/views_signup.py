"""
Public signup views.

Two paths:

  * ``TenantSignupView``         — email + password self-service signup.
                                   Creates the User AND the Tenant in
                                   one go.

  * ``SignupCompleteView``       — Phase 9.1: second step for Google
                                   sign-ups. The user is already
                                   authenticated; this view collects
                                   only the tenant details.

  * ``SignupSuccessView``        — thank-you page with the new URL.
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from apps.core.mixins import PublicSchemaOnlyMixin
from .forms import TenantSignupForm, TenantSignupCompleteForm
from .models import Tenant
from .services import provision_tenant


class TenantSignupView(PublicSchemaOnlyMixin, FormView):
    """Public signup for new tenants (email + password path)."""

    template_name = 'pages/signup.html'
    form_class = TenantSignupForm
    success_url = reverse_lazy('signup:signup_success')

    def form_valid(self, form):
        data = form.cleaned_data
        subdomain = data['subdomain']
        domain_name = f'{subdomain}.{settings.TENANT_BASE_DOMAIN}'

        try:
            tenant = provision_tenant(
                name=data['organization_name'],
                schema_name=subdomain,
                domain_name=domain_name,
                plan=data['plan'],
                admin_email=data['contact_email'].lower(),
                admin_password=data['admin_password'],
                contact_name=data['contact_name'],
                contact_email=data['contact_email'],
                contact_phone=data.get('contact_phone', ''),
            )

            # Store the domain in the session so the success page can link to it
            self.request.session['new_tenant_domain'] = domain_name
            self.request.session['new_tenant_name'] = tenant.name

            return super().form_valid(form)
        except Exception as e:
            form.add_error(None, f'Signup failed: {e}')
            return self.form_invalid(form)


class SignupCompleteView(PublicSchemaOnlyMixin, LoginRequiredMixin, FormView):
    """
    Second step for Google sign-ups (Phase 9.1).

    The user is already authenticated via Google. This form collects
    the tenant details Google cannot supply:
      • Organization name
      • Subdomain
      • Modules to enable
      • Contact phone
      • Plan

    On success:
      1. Provision a new Tenant (without creating a new admin user —
         the authenticated user IS the admin).
      2. Create a UserTenantMembership granting them TENANT_ADMIN role.
      3. Clear the session flag so RequireTenantSetupMiddleware stops
         redirecting them.
      4. Hand off to SignupSuccessView with the new URL.
    """

    template_name = 'pages/signup_complete.html'
    form_class = TenantSignupCompleteForm

    def dispatch(self, request, *args, **kwargs):
        # If the user already has a tenant, skip this step
        if request.user.is_authenticated and request.user.tenant_memberships.exists():
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            'organization_name': '',
            'subdomain': '',
            'plan': Tenant.Plan.STARTER,
            'modules': [Tenant.Module.HOSPITALITY],
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['google_user'] = self.request.user
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        subdomain = data['subdomain']
        domain_name = f'{subdomain}.{settings.TENANT_BASE_DOMAIN}'

        try:
            tenant = provision_tenant(
                name=data['organization_name'],
                schema_name=subdomain,
                domain_name=domain_name,
                plan=data['plan'],
                # No admin_email / admin_password: the Google user is
                # already authenticated. We just grant them membership.
                admin_email=None,
                admin_password=None,
                contact_name=self.request.user.full_name,
                contact_email=self.request.user.email,
                contact_phone=data.get('contact_phone', ''),
                modules=data['modules'],
            )

            # Make the Google user a tenant admin
            from apps.shared.users.models import UserTenantMembership
            UserTenantMembership.objects.create(
                user=self.request.user,
                tenant=tenant,
                role=UserTenantMembership.Role.TENANT_ADMIN,
            )

            # Clear the pending flag set by the social adapter
            self.request.session.pop('pending_tenant_setup', None)

            # Hand off to the success page with context
            self.request.session['new_tenant_domain'] = domain_name
            self.request.session['new_tenant_name'] = tenant.name

            return redirect('signup:signup_success')

        except Exception as e:
            form.add_error(None, f'Setup failed: {e}')
            return self.form_invalid(form)


class SignupSuccessView(PublicSchemaOnlyMixin, TemplateView):
    """Thank-you page. Reads the domain/name off the session."""

    template_name = 'pages/signup_success.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tenant_domain'] = self.request.session.pop('new_tenant_domain', None)
        ctx['tenant_name'] = self.request.session.pop('new_tenant_name', None)
        return ctx


class HealthCheckView(TemplateView):
    """Simple HTML health check for uptime monitors.

    Note: the JSON endpoint at /health/ is the primary monitor
    (see apps/shared/tenants/views_health.py). This view is only
    kept for backwards compatibility with older monitors.
    """

    template_name = 'pages/health.html'

    def get_context_data(self, **kwargs):
        from django.db import connection
        ctx = super().get_context_data(**kwargs)
        ctx['db_ok'] = True
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
        except Exception:
            ctx['db_ok'] = False
        return ctx