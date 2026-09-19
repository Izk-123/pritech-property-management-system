from datetime import timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import ListView, TemplateView
from django.db.models import Count, Q, Sum
from apps.core.properties.models import Unit
from apps.property.leases.models import Lease
from apps.property.rent_invoicing.models import RentInvoice
from apps.property.sales.models import SaleListing


class AvailabilityDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'pages/property/availability_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.now().date()

        # Units by status
        ctx['units_by_status'] = (
            Unit.objects
            .values('status')
            .annotate(count=Count('id'))
            .order_by('status')
        )

        # Expiring leases (next 90 days)
        ctx['expiring_leases'] = (
            Lease.objects
            .filter(
                status=Lease.Status.ACTIVE,
                end_date__lte=today + timedelta(days=90),
                end_date__gte=today,
            )
            .select_related('tenant', 'unit', 'unit__property')
            .order_by('end_date')
        )

        # Arrears
        ctx['arrears'] = (
            RentInvoice.objects
            .filter(status__in=[
                RentInvoice.Status.ISSUED,
                RentInvoice.Status.PARTIAL,
                RentInvoice.Status.OVERDUE,
            ])
            .select_related('tenant', 'unit')
            .order_by('due_date')
        )

        # Sales pipeline
        ctx['sale_pipeline'] = (
            SaleListing.objects
            .filter(status__in=[
                SaleListing.Status.LISTED,
                SaleListing.Status.UNDER_OFFER,
                SaleListing.Status.AGREEMENT,
            ])
            .select_related('property', 'unit', 'agent')
        )

        return ctx


class LeaseListView(LoginRequiredMixin, ListView):
    model = Lease
    template_name = 'pages/property/lease_list.html'
    context_object_name = 'leases'
    paginate_by = 25

    def get_queryset(self):
        qs = Lease.objects.select_related(
            'tenant', 'unit', 'unit__property'
        ).order_by('-start_date')

        status = self.request.GET.get('status', '')
        if status in Lease.Status.values:
            qs = qs.filter(status=status)

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(lease_number__icontains=search) |
                Q(tenant__full_name__icontains=search) |
                Q(unit__identifier__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = Lease.Status.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class RentInvoiceListView(LoginRequiredMixin, ListView):
    model = RentInvoice
    template_name = 'pages/property/rent_invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 25

    def get_queryset(self):
        qs = RentInvoice.objects.select_related(
            'tenant', 'unit', 'lease'
        ).order_by('-due_date')

        status = self.request.GET.get('status', '')
        if status in RentInvoice.Status.values:
            qs = qs.filter(status=status)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = RentInvoice.Status.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        return ctx