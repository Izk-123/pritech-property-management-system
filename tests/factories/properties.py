import factory
from factory.django import DjangoModelFactory
from apps.core.properties.models import Property, Unit, Amenity


class PropertyFactory(DjangoModelFactory):
    class Meta:
        model = Property

    name = factory.Sequence(lambda n: f'Test Property {n}')
    property_type = 'HOTEL'
    address = '123 Test Street'
    district = 'Lilongwe'
    region = 'CENTRAL'
    status = 'ACTIVE'


class AmenityFactory(DjangoModelFactory):
    class Meta:
        model = Amenity

    name = factory.Sequence(lambda n: f'Amenity {n}')
    category = 'ROOM'


class UnitFactory(DjangoModelFactory):
    class Meta:
        model = Unit

    property = factory.SubFactory(PropertyFactory)
    unit_type = 'ROOM'
    identifier = factory.Sequence(lambda n: f'Room {n:03d}')
    capacity_adults = 2
    capacity_children = 0
    bed_count = 1
    base_rate_mwk = 50000.00
    status = 'AVAIL'