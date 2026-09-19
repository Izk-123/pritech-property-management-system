import pytest
from datetime import date, timedelta
from decimal import Decimal
from apps.property.rent_invoicing.models import RentInvoice, RentInvoiceLine, RentPayment
from apps.property.rent_invoicing.services import (
    generate_invoice_for_lease, record_payment, apply_late_fee,
)
from apps.property.leases.models import Lease
from apps.property.leases.services import activate_lease
from tests.factories.properties import PropertyFactory, UnitFactory
from tests.factories.people import PersonFactory


@pytest.fixture
def active_lease(db):
    prop = PropertyFactory()
    unit = UnitFactory(property=prop)
    lease = Lease.objects.create(
        tenant=PersonFactory(), unit=unit,
        status='ACT',
        start_date=date.today(),
        end_date=date.today() + timedelta(days=365),
        rent_amount=Decimal('500000'),
        grace_period_days=5,
        late_fee_percent=Decimal('10'),
    )
    unit.status = 'OCC'
    unit.save()
    return lease


@pytest.mark.django_db
class TestInvoiceGeneration:
    def test_generate_creates_invoice_with_rent_line(self, active_lease):
        invoice = generate_invoice_for_lease(
            active_lease,
            period_start=date.today().replace(day=1),
            period_end=date.today().replace(day=28),
            due_date=date.today().replace(day=1),
        )
        assert invoice is not None
        assert invoice.lines.count() == 1
        assert invoice.lines.first().amount == Decimal('500000')
        assert invoice.total_due == Decimal('500000')

    def test_generate_skips_existing_period(self, active_lease):
        period_start = date.today().replace(day=1)
        generate_invoice_for_lease(active_lease, period_start, period_start, period_start)
        second = generate_invoice_for_lease(active_lease, period_start, period_start, period_start)
        assert second is None


@pytest.mark.django_db
class TestPaymentReconciliation:
    def test_full_payment_marks_invoice_paid(self, active_lease):
        invoice = generate_invoice_for_lease(
            active_lease,
            period_start=date.today().replace(day=1),
            period_end=date.today().replace(day=28),
            due_date=date.today(),
        )
        record_payment(invoice, Decimal('500000'), 'AIRTEL_MONEY')
        invoice.refresh_from_db()
        assert invoice.status == 'PAID'
        assert invoice.balance == 0

    def test_partial_payment_marks_invoice_partial(self, active_lease):
        invoice = generate_invoice_for_lease(
            active_lease,
            period_start=date.today().replace(day=1),
            period_end=date.today().replace(day=28),
            due_date=date.today(),
        )
        record_payment(invoice, Decimal('200000'), 'CASH')
        invoice.refresh_from_db()
        assert invoice.status == 'PART'
        assert invoice.balance == Decimal('300000')