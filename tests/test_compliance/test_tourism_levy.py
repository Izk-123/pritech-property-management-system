import pytest
from decimal import Decimal
from datetime import date
from apps.compliance.tourism_levy.models import TourismLevyConfig, TourismLevyRecord
from apps.compliance.tourism_levy.services import apply_tourism_levy
from apps.hospitality.folios.models import Folio, FolioCharge
from tests.factories.properties import PropertyFactory
from tests.factories.people import PersonFactory
from apps.hospitality.reservations.models import Reservation


@pytest.fixture
def folio_with_room_charge(db):
    prop = PropertyFactory()
    TourismLevyConfig.objects.create(
        property=prop, levy_percent=Decimal('1.00'),
        effective_from=date.today(),
    )
    guest = PersonFactory()
    res = Reservation.objects.create(
        primary_guest=guest, property=prop,
        status='CHIN', source='WALK',
        check_in=date.today(), check_out=date.today(),
    )
    folio = Folio.objects.create(reservation=res, currency='MWK')
    FolioCharge.objects.create(
        folio=folio, charge_type='ROOM',
        description='Room charge', amount=Decimal('100000'),
    )
    return folio


@pytest.mark.django_db
class TestTourismLevy:
    def test_levy_is_1_percent(self, folio_with_room_charge):
        record = apply_tourism_levy(folio_with_room_charge)
        assert record is not None
        assert record.levy_amount == Decimal('1000.00')
        assert record.levy_rate == Decimal('1.00')

    def test_levy_added_to_folio(self, folio_with_room_charge):
        apply_tourism_levy(folio_with_room_charge)
        levy_charges = folio_with_room_charge.charges.filter(
            charge_type='LEVY',
        )
        assert levy_charges.count() == 1
        assert levy_charges.first().amount == Decimal('1000.00')

    def test_no_levy_without_room_charge(self, db):
        prop = PropertyFactory()
        TourismLevyConfig.objects.create(
            property=prop, levy_percent=Decimal('1.00'),
            effective_from=date.today(),
        )
        guest = PersonFactory()
        res = Reservation.objects.create(
            primary_guest=guest, property=prop,
            status='CHIN', source='WALK',
            check_in=date.today(), check_out=date.today(),
        )
        folio = Folio.objects.create(reservation=res, currency='MWK')
        result = apply_tourism_levy(folio)
        assert result is None