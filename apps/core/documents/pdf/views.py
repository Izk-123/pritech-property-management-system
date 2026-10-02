"""Views that serve PDFs."""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.mixins import StaffRequiredMixin
from apps.hospitality.folios.models import Folio, FolioPayment
from apps.property.leases.models import Lease

from .folio import render_folio_invoice
from .receipt import render_payment_receipt
from .lease import render_lease_agreement
from .rent_invoice import render_rent_invoice
from .sale_agreement import render_sale_agreement


def _pdf_response(pdf_bytes, filename, inline=True):
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    disposition = 'inline' if inline else 'attachment'
    response['Content-Disposition'] = (
        f'{disposition}; filename="{filename}"'
    )
    response['Cache-Control'] = 'private, no-store'
    return response


class FolioInvoicePDFView(StaffRequiredMixin, View):
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