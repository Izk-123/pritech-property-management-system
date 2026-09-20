from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.conf import settings

from apps.core.mixins import PlatformAdminRequiredMixin, PublicSchemaOnlyMixin
from .models import Tenant, Domain
from .forms import TenantForm
from .services import provision_tenant, deprovision_tenant, reactivate_tenant


class TenantListView(PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, ListView):
    """List all tenants — platform admin only."""

    model = Tenant
    template_name = 'pages/platform/tenant_list.html'
    context_object_name = 'tenants'
    paginate_by = 25

    def get_queryset(self):
        qs = Tenant.objects.exclude(schema_name='public').order_by('-created_at')

        status = self.request.GET.get('status', '')
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'suspended':
            qs = qs.filter(is_active=False)

        plan = self.request.GET.get('plan', '')
        if plan in Tenant.Plan.values:
            qs = qs.filter(plan=plan)

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(schema_name__icontains=search) |
                Q(contact_email__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['plans'] = Tenant.Plan.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['current_plan'] = self.request.GET.get('plan', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['total_active'] = Tenant.objects.filter(
            is_active=True,
        ).exclude(schema_name='public').count()
        ctx['total_suspended'] = Tenant.objects.filter(
            is_active=False,
        ).exclude(schema_name='public').count()
        return ctx


class TenantDetailView(PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, DetailView):
    """View a single tenant's details."""

    model = Tenant
    template_name = 'pages/platform/tenant_detail.html'
    context_object_name = 'tenant'

    def get_queryset(self):
        return Tenant.objects.exclude(schema_name='public').prefetch_related('domains')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['domains'] = self.object.domains.all()

        # Try to load tenant-specific stats
        from django_tenants.utils import schema_context
        try:
            with schema_context(self.object.schema_name):
                from apps.core.properties.models import Property, Unit
                from apps.core.people.models import Person
                from apps.hospitality.reservations.models import Reservation
                from apps.property.leases.models import Lease

                ctx['stats'] = {
                    'properties': Property.objects.count(),
                    'units': Unit.objects.count(),
                    'people': Person.objects.count(),
                    'reservations': Reservation.objects.count(),
                    'active_leases': Lease.objects.filter(status='ACT').count(),
                }
        except Exception as e:
            ctx['stats_error'] = str(e)

        return ctx


class TenantCreateView(PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, CreateView):
    """Create a new tenant."""

    model = Tenant
    form_class = TenantForm
    template_name = 'pages/platform/tenant_form.html'

    def form_valid(self, form):
        data = form.cleaned_data
        domain_name = f'{data["subdomain"]}.{settings.TENANT_BASE_DOMAIN}'

        try:
            tenant = provision_tenant(
                name=data['name'],
                schema_name=data['subdomain'],
                domain_name=domain_name,
                plan=data['plan'],
                contact_name=data.get('contact_name', ''),
                contact_email=data.get('contact_email', ''),
                contact_phone=data.get('contact_phone', ''),
            )
            messages.success(
                self.request,
                f'Tenant "{tenant.name}" provisioned at https://{domain_name}',
            )
            return redirect('platform:tenant_detail', pk=tenant.pk)
        except Exception as e:
            messages.error(self.request, f'Provisioning failed: {e}')
            return self.form_invalid(form)


class TenantUpdateView(PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, UpdateView):
    """Edit a tenant's metadata."""

    model = Tenant
    form_class = TenantForm
    template_name = 'pages/platform/tenant_form.html'

    def get_queryset(self):
        return Tenant.objects.exclude(schema_name='public')

    def form_valid(self, form):
        messages.success(self.request, 'Tenant updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('platform:tenant_detail', kwargs={'pk': self.object.pk})


class TenantSuspendView(PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, View):
    """Suspend a tenant (deactivate, keep schema)."""

    def post(self, request, pk):
        tenant = get_object_or_404(
            Tenant.objects.exclude(schema_name='public'), pk=pk,
        )
        deprovision_tenant(tenant, drop_schema=False)
        messages.warning(request, f'Tenant "{tenant.name}" suspended.')
        return redirect('platform:tenant_detail', pk=pk)


class TenantReactivateView(PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, View):
    """Reactivate a suspended tenant."""

    def post(self, request, pk):
        tenant = get_object_or_404(
            Tenant.objects.exclude(schema_name='public'), pk=pk,
        )
        reactivate_tenant(tenant)
        messages.success(request, f'Tenant "{tenant.name}" reactivated.')
        return redirect('platform:tenant_detail', pk=pk)


class TenantDeleteView(PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, View):
    """
    Permanently delete a tenant — DESTRUCTIVE, drops the schema.
    Requires typed confirmation.
    """

    def post(self, request, pk):
        tenant = get_object_or_404(
            Tenant.objects.exclude(schema_name='public'), pk=pk,
        )

        confirmation = request.POST.get('confirm_name', '').strip()
        if confirmation != tenant.name:
            messages.error(
                request,
                'Confirmation name did not match. Tenant was not deleted.',
            )
            return redirect('platform:tenant_detail', pk=pk)

        name = tenant.name
        try:
            deprovision_tenant(tenant, drop_schema=True)
            messages.warning(request, f'Tenant "{name}" permanently deleted.')
            return redirect('platform:tenant_list')
        except Exception as e:
            messages.error(request, f'Deletion failed: {e}')
            return redirect('platform:tenant_detail', pk=pk)