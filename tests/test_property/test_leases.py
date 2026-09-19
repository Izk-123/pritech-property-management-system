import pytest
from datetime import date, timedelta
from decimal import Decimal
from apps.property.leases.models import Lease
from apps.property.leases.services import (
    activate_lease, terminate_lease, renew_lease, LeaseError,
)
from tests.factories.properties import PropertyFactory, UnitFactory
from tests.factories.people import PersonFactory


@pytest.fixture
def lease(db):
    prop = PropertyFactory()
    unit = UnitFactory(property=prop)
    tenant = PersonFactory()
    return Lease.objects.create(
        tenant=tenant, unit=unit,
        status='DRAFT',
        start_date=date.today(),
        end_date=date.today() + timedelta(days=365),
        rent_amount=Decimal('500000'),
    )


@pytest.mark.django_db
class TestLeaseLifecycle:
    def test_activate_lease_marks_unit_occupied(self, lease):
        activate_lease(lease)
        lease.refresh_from_db()
        lease.unit.refresh_from_db()
        assert lease.status == 'ACT'
        assert lease.unit.status == 'OCC'

    def test_activate_lease_rejects_double_booking(self, lease):
        activate_lease(lease)
        other = Lease.objects.create(
            tenant=PersonFactory(), unit=lease.unit,
            status='DRAFT',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            rent_amount=Decimal('500000'),
        )
        with pytest.raises(LeaseError):
            activate_lease(other)

    def test_terminate_lease_releases_unit(self, lease):
        activate_lease(lease)
        terminate_lease(lease, reason='Tenant relocated')
        lease.refresh_from_db()
        lease.unit.refresh_from_db()
        assert lease.status == 'TERM'
        assert lease.unit.status == 'AVAIL'


@pytest.mark.django_db
class TestLeaseRenewal:
    def test_renew_creates_new_lease_and_marks_old_renewed(self, lease):
        activate_lease(lease)
        new = renew_lease(lease, new_end_date=lease.end_date + timedelta(days=365))
        lease.refresh_from_db()
        assert lease.status == 'REN'
        assert new.status == 'ACT'
        assert new.start_date == lease.end_date
        assert new.rent_amount > lease.rent_amount  # escalation applied