from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, FormView,
)
from django.db.models import Q
from .models import RentInvoice, RentInvoiceLine, RentPayment
from .forms import RentInvoiceLineForm, RentPaymentForm, InvoiceGenerationForm
from .services import generate_invoice_for_lease, record_payment, apply_late_fee
from apps.property.leases.models import Lease
from django.views import View

class InvoiceListView(LoginRequiredMixin, ListView):
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

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(invoice_number__icontains=search) |
                Q(tenant__full_name__icontains=search) |
                Q(unit__identifier__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = RentInvoice.Status.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = RentInvoice
    template_name = 'pages/property/rent_invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        return RentInvoice.objects.select_related(
            'tenant', 'unit', 'lease'
        ).prefetch_related('lines', 'payments')


class InvoiceGenerateForLeaseView(LoginRequiredMixin, FormView):
    template_name = 'pages/property/rent_invoice_generate.html'
    form_class = InvoiceGenerationForm

    def get_lease(self):
        return get_object_or_404(Lease, pk=self.kwargs['lease_pk'])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['lease'] = self.get_lease()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['lease'] = self.get_lease()
        return ctx

    def form_valid(self, form):
        lease = self.get_lease()
        invoice = generate_invoice_for_lease(
            lease,
            period_start=form.cleaned_data['period_start'],
            period_end=form.cleaned_data['period_end'],
            due_date=form.cleaned_data['due_date'],
        )
        if invoice:
            messages.success(
                self.request,
                f'Invoice {invoice.invoice_number} generated.',
            )
            return redirect('property:invoices:detail', pk=invoice.pk)
        else:
            messages.warning(
                self.request,
                'An invoice already exists for this period.',
            )
            return redirect('property:leases:detail', pk=lease.pk)


class InvoiceLineAddView(LoginRequiredMixin, CreateView):
    model = RentInvoiceLine
    form_class = RentInvoiceLineForm
    template_name = 'pages/property/rent_invoice_line_form.html'

    def get_invoice(self):
        return get_object_or_404(RentInvoice, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['invoice'] = self.get_invoice()
        return ctx

    def form_valid(self, form):
        form.instance.invoice = self.get_invoice()
        response = super().form_valid(form)
        invoice = self.get_invoice()
        invoice.recalculate_totals()
        messages.success(self.request, 'Line added.')
        return response

    def get_success_url(self):
        return reverse_lazy('property:invoices:detail',
                            kwargs={'pk': self.get_invoice().pk})


class InvoicePaymentView(LoginRequiredMixin, CreateView):
    model = RentPayment
    form_class = RentPaymentForm
    template_name = 'pages/property/rent_payment_form.html'

    def get_invoice(self):
        return get_object_or_404(RentInvoice, pk=self.kwargs['pk'])

    def get_initial(self):
        initial = super().get_initial()
        invoice = self.get_invoice()
        if invoice.balance > 0:
            initial['amount'] = invoice.balance
            initial['currency'] = invoice.currency
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['invoice'] = self.get_invoice()
        return ctx

    def form_valid(self, form):
        invoice = self.get_invoice()
        payment = form.save(commit=False)
        payment.invoice = invoice
        payment.received_by = self.request.user
        payment.save()
        invoice.recalculate_totals()
        messages.success(self.request, 'Payment recorded.')
        return redirect('property:invoices:detail', pk=invoice.pk)


class InvoiceApplyLateFeeView(LoginRequiredMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(RentInvoice, pk=pk)
        before = invoice.late_fee
        apply_late_fee(invoice)
        invoice.refresh_from_db()
        if invoice.late_fee > before:
            messages.success(request, 'Late fee applied.')
        else:
            messages.info(request, 'No late fee applied (grace period or already applied).')
        return redirect('property:invoices:detail', pk=pk)