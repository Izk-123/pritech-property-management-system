import pytest
from datetime import date, timedelta
from decimal import Decimal
from apps.hospitality.reservations.models import Reservation, ReservationRoom
from apps.hospitality.reservations.services import (
    check_in_reservation, check_out_reservation, available_units,
    CheckInError,
)
from apps.hospitality.folios.models import Folio, FolioPayment
from tests.factories.properties import PropertyFactory, UnitFactory
from tests.factories.people import PersonFactory


@pytest.fixture
def reservation(db):
    prop = PropertyFactory()
    guest = PersonFactory()
    return Reservation.objects.create(
        primary_guest=guest,
        property=prop,
        status='CONF',
        source='PHONE',
        check_in=date.today(),
        check_out=date.today() + timedelta(days=2),
        adults=2,
    )


@pytest.mark.django_db
class TestDateOverlap:
    def test_no_conflict_when_dates_are_adjacent(self, reservation):
        """A booking ending on day X and another starting on day X do not conflict."""
        unit = UnitFactory(property=reservation.property)
        ReservationRoom.objects.create(
            reservation=reservation, unit=unit,
            rate_per_night=Decimal('50000'),
        )

        # Second reservation: starts exactly when the first ends
        other = Reservation.objects.create(
            primary_guest=PersonFactory(),
            property=reservation.property,
            status='CONF', source='PHONE',
            check_in=reservation.check_out,
            check_out=reservation.check_out + timedelta(days=2),
        )
        conflicts = Reservation.find_conflicting_unit_ids(
            property=reservation.property,
            check_in=other.check_in,
            check_out=other.check_out,
        )
        assert unit.id not in conflicts

    def test_conflict_when_dates_overlap(self, reservation):
        unit = UnitFactory(property=reservation.property)
        ReservationRoom.objects.create(
            reservation=reservation, unit=unit,
            rate_per_night=Decimal('50000'),
        )
        conflicts = Reservation.find_conflicting_unit_ids(
            property=reservation.property,
            check_in=reservation.check_in + timedelta(days=1),
            check_out=reservation.check_out + timedelta(days=1),
        )
        assert unit.id in conflicts


@pytest.mark.django_db
class TestCheckIn:
    def test_check_in_creates_folio_and_marks_unit_occupied(self, reservation):
        unit = UnitFactory(property=reservation.property)
        check_in_reservation(
            reservation=reservation,
            unit_assignments=[{'unit': unit, 'rate': Decimal('50000')}],
        )
        reservation.refresh_from_db()
        unit.refresh_from_db()
        assert reservation.status == 'CHIN'
        assert unit.status == 'OCC'
        assert Folio.objects.filter(reservation=reservation).exists()

    def test_check_in_rejects_unavailable_unit(self, reservation):
        unit = UnitFactory(property=reservation.property, status='MAINT')
        with pytest.raises(CheckInError):
            check_in_reservation(
                reservation=reservation,
                unit_assignments=[{'unit': unit, 'rate': Decimal('50000')}],
            )


@pytest.mark.django_db
class TestCheckOut:
    def test_check_out_requires_settled_folio(self, reservation):
        unit = UnitFactory(property=reservation.property)
        check_in_reservation(
            reservation=reservation,
            unit_assignments=[{'unit': unit, 'rate': Decimal('50000')}],
        )
        folio = reservation.folio
        from apps.hospitality.folios.models import FolioCharge
        FolioCharge.objects.create(
            folio=folio, charge_type='ROOM',
            description='Room', amount=Decimal('50000'),
        )
        with pytest.raises(CheckInError):
            check_out_reservation(reservation)

    def test_check_out_triggers_housekeeping(self, reservation):
        unit = UnitFactory(property=reservation.property)
        check_in_reservation(
            reservation=reservation,
            unit_assignments=[{'unit': unit, 'rate': Decimal('50000')}],
        )
        # Settle the folio
        folio = reservation.folio
        from apps.hospitality.folios.models import FolioCharge
        FolioCharge.objects.create(
            folio=folio, charge_type='ROOM',
            description='Room', amount=Decimal('50000'),
        )
        FolioPayment.objects.create(
            folio=folio, method='CASH_MWK',
            amount=Decimal('50000'),
        )
        check_out_reservation(reservation)
        unit.refresh_from_db()
        assert unit.status == 'CLEAN'
        assert unit.housekeeping_tasks.filter(status='PEND').exists()