import factory
from factory.django import DjangoModelFactory
from apps.core.people.models import Person, PersonPropertyRole


class PersonFactory(DjangoModelFactory):
    class Meta:
        model = Person

    full_name = factory.Faker('name')
    phone_primary = factory.Sequence(lambda n: f'+265991{n:06d}')
    email = factory.Faker('email')
    nationality = 'Malawian'
    preferred_language = 'en'


class PersonPropertyRoleFactory(DjangoModelFactory):
    class Meta:
        model = PersonPropertyRole

    person = factory.SubFactory(PersonFactory)
    property = factory.SubFactory('tests.factories.properties.PropertyFactory')
    role = 'GUEST'
    is_active = True