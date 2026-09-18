import pytest
from apps.core.properties.models import Property, Unit
from apps.core.people.models import Person


@pytest.mark.django_db
class TestProperty:
    def test_create_property(self):
        prop = Property.objects.create(
            name='Lake Malawi Lodge',
            property_type='LODGE',
            address='Cape Maclear',
            district='Mangochi',
            region='SOUTH',
        )
        assert prop.name == 'Lake Malawi Lodge'
        assert prop.get_property_type_display() == 'Lodge'
        assert str(prop) == 'Lake Malawi Lodge (Lodge)'


@pytest.mark.django_db
class TestUnit:
    def test_unit_str(self, unit):
        assert 'Room' in str(unit)

    def test_unit_unique_identifier_per_property(self, property):
        Unit.objects.create(
            property=property, unit_type='ROOM', identifier='Room 101',
            base_rate_mwk=50000,
        )
        with pytest.raises(Exception):  # IntegrityError
            Unit.objects.create(
                property=property, unit_type='ROOM', identifier='Room 101',
                base_rate_mwk=50000,
            )

    def test_unit_capacity_constraint(self, property):
        with pytest.raises(Exception):  # IntegrityError
            Unit.objects.create(
                property=property, unit_type='ROOM', identifier='Room 102',
                capacity_adults=0, base_rate_mwk=50000,
            )


@pytest.mark.django_db
class TestPerson:
    def test_person_creation(self, person):
        assert person.full_name is not None
        assert person.nationality == 'Malawian'

    def test_blacklist(self, person):
        person.is_blacklisted = True
        person.blacklist_reason = 'Unpaid rent'
        person.save()
        person.refresh_from_db()
        assert person.is_blacklisted is True