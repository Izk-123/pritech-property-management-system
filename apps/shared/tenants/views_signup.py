from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView
from apps.core.mixins import PublicSchemaOnlyMixin
from .forms import TenantSignupForm
from .services import provision_tenant


class TenantSignupView(PublicSchemaOnlyMixin, FormView):
    """Public signup for new tenants."""

    template_name = 'pages/signup.html'
    form_class = TenantSignupForm
    success_url = reverse_lazy('signup:signup_success')

    def form_valid(self, form):
        data = form.cleaned_data
        subdomain = data['subdomain']
        domain_name = f'{subdomain}.pms.pritechmw.com'

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


class SignupSuccessView(PublicSchemaOnlyMixin, TemplateView):
    template_name = 'pages/signup_success.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tenant_domain'] = self.request.session.pop('new_tenant_domain', None)
        ctx['tenant_name'] = self.request.session.pop('new_tenant_name', None)
        return ctx


class HealthCheckView(TemplateView):
    """Simple health check for uptime monitors."""

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