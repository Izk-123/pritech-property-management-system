import pytest
from apps.core.documents.pdf.receipt import render_payment_receipt
from apps.core.documents.pdf.folio import render_folio_invoice
from apps.core.documents.pdf.lease import render_lease_agreement


@pytest.mark.django_db(transaction=True)
class TestFolioPDF:
    def test_folio_pdf_renders(self, folio):
        pdf = render_folio_invoice(folio)
        assert pdf[:4] == b'%PDF'
        assert len(pdf) > 2000


@pytest.mark.django_db(transaction=True)
class TestReceiptPDF:
    def test_receipt_pdf_renders(self, folio_payment):
        pdf = render_payment_receipt(folio_payment)
        assert pdf[:4] == b'%PDF'


@pytest.mark.django_db(transaction=True)
class TestLeasePDF:
    def test_lease_pdf_renders(self, lease):
        pdf = render_lease_agreement(lease)
        assert pdf[:4] == b'%PDF'
        assert len(pdf) > 5000