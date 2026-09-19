from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView
from .models import Folio, FolioCharge, FolioPayment
from .forms import FolioChargeForm, FolioPaymentForm


class FolioChargeCreateView(LoginRequiredMixin, CreateView):
    model = FolioCharge
    form_class = FolioChargeForm
    template_name = 'pages/hospitality/folio_charge_form.html'

    def get_folio(self):
        return get_object_or_404(Folio, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['folio'] = self.get_folio()
        return ctx

    def form_valid(self, form):
        form.instance.folio = self.get_folio()
        form.instance.posted_by = self.request.user
        messages.success(self.request, 'Charge posted.')
        return super().form_valid(form)

    def get_success_url(self):
        return f'/reservations/{self.get_folio().reservation_id}/'


class FolioPaymentCreateView(LoginRequiredMixin, CreateView):
    model = FolioPayment
    form_class = FolioPaymentForm
    template_name = 'pages/hospitality/folio_payment_form.html'

    def get_folio(self):
        return get_object_or_404(Folio, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['folio'] = self.get_folio()
        return ctx

    def get_initial(self):
        initial = super().get_initial()
        folio = self.get_folio()
        if folio.balance > 0:
            initial['amount'] = folio.balance
            initial['currency'] = folio.currency
        return initial

    def form_valid(self, form):
        form.instance.folio = self.get_folio()
        form.instance.received_by = self.request.user
        messages.success(self.request, 'Payment recorded.')
        return super().form_valid(form)

    def get_success_url(self):
        return f'/reservations/{self.get_folio().reservation_id}/'