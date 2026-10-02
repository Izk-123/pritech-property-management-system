"""
Views that serve PDFs. Every view checks permissions before
generating. The tenant is resolved from the subdomain by
django-tenants, so the same view serves every tenant's PDFs
with their own branding automatically.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import StaffRequiredMixin
from apps.hospitality.folios.models import Folio, FolioPayment
from apps.property.leases.models import Lease
from apps.property.rent_invoicing.models import RentInvoice
from apps.property.sales.models import SaleAgreement

from .folio import render_folio_invoice
from .receipt import render_payment_receipt
from .lease import render_lease_agreement
from .rent_invoice import render_rent_invoice
from .sale_agreement import render_sale_agreement


def _pdf_response(pdf_bytes, filename, inline=True):
    """Build a Django response with the correct headers."""
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    disposition = 'inline' if inline else 'attachment'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    return response


class FolioInvoicePDFView(StaffRequiredMixin, View):
    """Serve a folio invoice as a PDF."""

    def get(self, request, pk):
        folio = get_object_or_404(
            Folio.objects
                .select_related('reservation__primary_guest',
                                'reservation__property')
                .prefetch_related('charges', 'payments'),
            pk=pk,
        )
        pdf = render_folio_invoice(folio)
        filename = f'folio-{folio.reservation.reservation_number}.pdf'
        inline = request.GET.get('download') != '1'
        return _pdf_response(pdf, filename, inline=inline)


class PaymentReceiptPDFView(StaffRequiredMixin, View):
    """Serve a payment receipt as a PDF."""

    def get(self, request, pk):
        payment = get_object_or_404(
            FolioPayment.objects.select_related(
                'folio__reservation__primary_guest',
                'folio__reservation__property',
                'received_by',
            ),
            pk=pk,
        )
        pdf = render_payment_receipt(payment)
        filename = f'receipt-{payment.pk:08d}.pdf'
        inline = request.GET.get('download') != '1'
        return _pdf_response(pdf, filename, inline=inline)


class LeaseAgreementPDFView(StaffRequiredMixin, View):
    """Serve a lease agreement as a PDF."""

    def get(self, request, pk):
        lease = get_object_or_404(
            Lease.objects.select_related(
                'tenant', 'landlord', 'unit', 'unit__property',
            ),
            pk=pk,
        )
        pdf = render_lease_agreement(lease)
        filename = f'lease-{lease.lease_number}.pdf'
        inline = request.GET.get('download') != '1'
        return _pdf_response(pdf, filename, inline=inline)


class RentInvoicePDFView(StaffRequiredMixin, View):
    """Serve a rent invoice as a PDF."""

    def get(self, request, pk):
        invoice = get_object_or_404(
            RentInvoice.objects
                .select_related('tenant', 'unit', 'unit__property', 'lease')
                .prefetch_related('lines', 'payments'),
            pk=pk,
        )
        pdf = render_rent_invoice(invoice)
        filename = f'invoice-{invoice.invoice_number}.pdf'
        inline = request.GET.get('download') != '1'
        return _pdf_response(pdf, filename, inline=inline)


class SaleAgreementPDFView(StaffRequiredMixin, View):
    """Serve a sale agreement as a PDF."""

    def get(self, request, pk):
        agreement = get_object_or_404(
            SaleAgreement.objects.select_related(
                'buyer', 'seller', 'listing__property', 'listing__unit',
            ).prefetch_related('installments', 'commissions'),
            pk=pk,
        )
        pdf = render_sale_agreement(agreement)
        filename = f'sale-{agreement.agreement_number}.pdf'
        inline = request.GET.get('download') != '1'
        return _pdf_response(pdf, filename, inline=inline)