import pytest
from tests.factories.properties import PropertyFactory, UnitFactory
from tests.factories.people import PersonFactory


@pytest.fixture
def property(db):
    return PropertyFactory()


@pytest.fixture
def unit(db, property):
    return UnitFactory(property=property)


@pytest.fixture
def person(db):
    return PersonFactory()