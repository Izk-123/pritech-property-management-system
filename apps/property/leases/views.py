from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, FormView,
)
from django.views import View
from django.db.models import Q, Sum
from .models import Lease
from .forms import LeaseForm, LeaseRenewalForm, LeaseTerminationForm
from .services import activate_lease, terminate_lease, renew_lease, LeaseError


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


class LeaseDetailView(LoginRequiredMixin, DetailView):
    model = Lease
    template_name = 'pages/property/lease_detail.html'
    context_object_name = 'lease'

    def get_queryset(self):
        return Lease.objects.select_related(
            'tenant', 'unit', 'unit__property', 'landlord', 'document'
        ).prefetch_related('invoices__lines', 'invoices__payments')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_invoiced'] = self.object.invoices.exclude(
            status='VOID'
        ).aggregate(t=Sum('total_due'))['t'] or 0
        ctx['total_paid'] = self.object.invoices.aggregate(
            t=Sum('amount_paid')
        )['t'] or 0
        ctx['outstanding'] = ctx['total_invoiced'] - ctx['total_paid']
        return ctx


class LeaseCreateView(LoginRequiredMixin, CreateView):
    model = Lease
    form_class = LeaseForm
    template_name = 'pages/property/lease_form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.status = Lease.Status.DRAFT
        messages.success(self.request, 'Lease created as draft.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('property:lease_detail', kwargs={'pk': self.object.pk})


class LeaseUpdateView(LoginRequiredMixin, UpdateView):
    model = Lease
    form_class = LeaseForm
    template_name = 'pages/property/lease_form.html'

    def get_queryset(self):
        return Lease.objects.filter(
            status__in=[Lease.Status.DRAFT, Lease.Status.PENDING]
        )

    def form_valid(self, form):
        messages.success(self.request, 'Lease updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('property:lease_detail', kwargs={'pk': self.object.pk})


class LeaseActivateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        lease = get_object_or_404(Lease, pk=pk)
        try:
            activate_lease(lease, user=request.user)
            messages.success(
                request,
                f'Lease {lease.lease_number} activated. '
                f'Unit {lease.unit.identifier} marked as occupied.',
            )
        except LeaseError as e:
            messages.error(request, str(e))
        return redirect('property:lease_detail', pk=pk)


class LeaseTerminateView(LoginRequiredMixin, FormView):
    template_name = 'pages/property/lease_terminate.html'
    form_class = LeaseTerminationForm

    def get_lease(self):
        return get_object_or_404(Lease, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['lease'] = self.get_lease()
        return ctx

    def form_valid(self, form):
        lease = self.get_lease()
        try:
            terminate_lease(
                lease,
                reason=form.cleaned_data['reason'],
                user=self.request.user,
            )
            messages.success(request := self.request, f'Lease {lease.lease_number} terminated.')
            return redirect('property:lease_detail', pk=lease.pk)
        except LeaseError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class LeaseRenewView(LoginRequiredMixin, FormView):
    template_name = 'pages/property/lease_renew.html'
    form_class = LeaseRenewalForm

    def get_lease(self):
        return get_object_or_404(Lease, pk=self.kwargs['pk'])

    def get_initial(self):
        initial = super().get_initial()
        lease = self.get_lease()
        initial['new_rent_amount'] = lease.rent_amount
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['lease'] = self.get_lease()
        return ctx

    def form_valid(self, form):
        lease = self.get_lease()
        try:
            new_lease = renew_lease(
                lease,
                new_end_date=form.cleaned_data['new_end_date'],
                new_rent_amount=form.cleaned_data['new_rent_amount'],
                user=self.request.user,
            )
            messages.success(
                self.request,
                f'Lease renewed. New lease: {new_lease.lease_number}.',
            )
            return redirect('property:lease_detail', pk=new_lease.pk)
        except LeaseError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)