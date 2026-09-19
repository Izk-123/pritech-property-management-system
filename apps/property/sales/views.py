from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, FormView,
)
from django.views import View
from django.db.models import Q
from .models import SaleListing, SaleOffer, SaleAgreement
from .forms import SaleListingForm, SaleOfferForm, SaleAgreementForm
from .services import accept_offer, create_sale_agreement, complete_sale, SaleError


class ListingListView(LoginRequiredMixin, ListView):
    model = SaleListing
    template_name = 'pages/property/sales_listing_list.html'
    context_object_name = 'listings'
    paginate_by = 25

    def get_queryset(self):
        qs = SaleListing.objects.select_related(
            'property', 'unit', 'agent'
        ).order_by('-listing_date')

        status = self.request.GET.get('status', '')
        if status in SaleListing.Status.values:
            qs = qs.filter(status=status)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = SaleListing.Status.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        return ctx


class ListingDetailView(LoginRequiredMixin, DetailView):
    model = SaleListing
    template_name = 'pages/property/sales_listing_detail.html'
    context_object_name = 'listing'

    def get_queryset(self):
        return SaleListing.objects.select_related(
            'property', 'unit', 'agent'
        ).prefetch_related('offers__buyer')


class ListingCreateView(LoginRequiredMixin, CreateView):
    model = SaleListing
    form_class = SaleListingForm
    template_name = 'pages/property/sales_listing_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Listing created.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('property:sales:listing_detail',
                            kwargs={'pk': self.object.pk})


class OfferCreateView(LoginRequiredMixin, CreateView):
    model = SaleOffer
    form_class = SaleOfferForm
    template_name = 'pages/property/sales_offer_form.html'

    def get_listing(self):
        return get_object_or_404(SaleListing, pk=self.kwargs['listing_pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['listing'] = self.get_listing()
        return ctx

    def form_valid(self, form):
        form.instance.listing = self.get_listing()
        messages.success(self.request, 'Offer recorded.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('property:sales:listing_detail',
                            kwargs={'pk': self.get_listing().pk})


class OfferAcceptView(LoginRequiredMixin, View):
    def post(self, request, pk):
        offer = get_object_or_404(SaleOffer, pk=pk)
        try:
            accept_offer(offer, user=request.user)
            messages.success(
                request,
                f'Offer accepted. Listing moved to Under Offer.',
            )
        except SaleError as e:
            messages.error(request, str(e))
        return redirect('property:sales:listing_detail',
                        pk=offer.listing.pk)


class AgreementCreateView(LoginRequiredMixin, FormView):
    template_name = 'pages/property/sales_agreement_form.html'
    form_class = SaleAgreementForm

    def get_offer(self):
        return get_object_or_404(SaleOffer, pk=self.kwargs['offer_pk'])

    def get_initial(self):
        initial = super().get_initial()
        offer = self.get_offer()
        initial['buyer'] = offer.buyer
        initial['sale_price'] = offer.offer_amount
        initial['currency'] = offer.currency
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['offer'] = self.get_offer()
        return ctx

    def form_valid(self, form):
        offer = self.get_offer()
        try:
            agreement = create_sale_agreement(
                offer=offer,
                deposit_amount=form.cleaned_data['deposit_amount'],
                payment_type=form.cleaned_data['payment_type'],
                completion_date=form.cleaned_data['completion_date'],
                installment_count=form.cleaned_data.get('installment_count') or 1,
                user=self.request.user,
            )
            messages.success(
                self.request,
                f'Sale agreement {agreement.agreement_number} created.',
            )
            return redirect('property:sales:agreement_detail', pk=agreement.pk)
        except SaleError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class AgreementDetailView(LoginRequiredMixin, DetailView):
    model = SaleAgreement
    template_name = 'pages/property/sales_agreement_detail.html'
    context_object_name = 'agreement'

    def get_queryset(self):
        return SaleAgreement.objects.select_related(
            'listing', 'listing__property', 'buyer', 'seller'
        ).prefetch_related('installments', 'commissions__agent')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_paid'] = sum(
            i.amount_paid for i in self.object.installments.all()
        ) + self.object.deposit_paid
        return ctx


class AgreementCompleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        agreement = get_object_or_404(SaleAgreement, pk=pk)
        try:
            complete_sale(agreement, user=request.user)
            messages.success(request, 'Sale marked as completed.')
        except SaleError as e:
            messages.error(request, str(e))
        return redirect('property:sales:agreement_detail', pk=pk)