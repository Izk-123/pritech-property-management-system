"""
Seed a complete demo environment for Pritech PMS.

Usage
-----
    python manage.py seed_demo                    # full demo
    python manage.py seed_demo --skip-tenants     # only platform (plans + public tenant)
    python manage.py seed_demo --tenant lakeview  # only Lakeview Lodge
    python manage.py seed_demo --tenant sunbird   # only Sunbird Hotel
    python manage.py seed_demo --reset            # drop + recreate demo tenants first

Idempotent
----------
Safe to run multiple times. All creates use get_or_create or
update_or_create keyed on stable identifiers.

Credentials created
-------------------
Platform admin:  admin@pritechmw.com    / PlatformAdmin2026!
Lakeview admin:  admin@lakeview.mw      / LakeviewDemo2026!
Lakeview mgr:    manager@lakeview.mw    / LakeviewDemo2026!
Lakeview desk:   desk@lakeview.mw       / LakeviewDemo2026!
Lakeview hk:     housekeeping@lakeview.mw / LakeviewDemo2026!
Lakeview acct:   accounts@lakeview.mw   / LakeviewDemo2026!
Sunbird admin:   admin@sunbird.mw       / SunbirdDemo2026!
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from django_tenants.utils import schema_context

from apps.shared.tenants.models import Tenant, Domain
from apps.shared.tenants.services import provision_tenant
from apps.shared.users.models import UserTenantMembership


User = get_user_model()


# ─────────────────────────────────────────────────────────────────────
# Command
# ─────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Seed sample data for Pritech PMS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Drop and recreate demo tenants before seeding',
        )
        parser.add_argument(
            '--skip-tenants',
            action='store_true',
            help='Only seed plans and the public tenant',
        )
        parser.add_argument(
            '--tenant',
            choices=['all', 'lakeview', 'sunbird'],
            default='all',
            help='Which tenant(s) to seed',
        )

    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING('━' * 60))
        self.stdout.write(self.style.MIGRATE_HEADING('  Pritech PMS — Demo Seed'))
        self.stdout.write(self.style.MIGRATE_HEADING('━' * 60))

        if opts['reset']:
            self._reset_demo_tenants()

        # ── Platform-level data (public schema) ────────────────
        self._seed_subscription_plans()
        self._seed_public_tenant()
        self._seed_platform_admin()

        if opts['skip_tenants']:
            self._done()
            return

        # ── Demo tenants ──────────────────────────────────────
        wanted = opts['tenant']
        if wanted in ('all', 'lakeview'):
            self._seed_lakeview()
        if wanted in ('all', 'sunbird'):
            self._seed_sunbird()

        self._done()

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────

    def _log(self, msg):
        self.stdout.write(f'  {msg}')

    def _ok(self, msg):
        self.stdout.write(self.style.SUCCESS(f'  ✓ {msg}'))

    def _warn(self, msg):
        self.stdout.write(self.style.WARNING(f'  ⚠ {msg}'))

    def _section(self, title):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'▸ {title}'))

    def _done(self):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('━' * 60))
        self.stdout.write(self.style.SUCCESS('  Demo seed complete.'))
        self.stdout.write(self.style.MIGRATE_HEADING('━' * 60))
        self.stdout.write('')
        self.stdout.write('  Logins:')
        self.stdout.write('    Platform:  admin@pritechmw.com    / PlatformAdmin2026!')
        self.stdout.write('    Lakeview:  admin@lakeview.mw      / LakeviewDemo2026!')
        self.stdout.write('               manager@lakeview.mw    / LakeviewDemo2026!')
        self.stdout.write('               desk@lakeview.mw       / LakeviewDemo2026!')
        self.stdout.write('               housekeeping@lakeview.mw / LakeviewDemo2026!')
        self.stdout.write('               accounts@lakeview.mw   / LakeviewDemo2026!')
        self.stdout.write('    Sunbird:   admin@sunbird.mw       / SunbirdDemo2026!')
        self.stdout.write('')
        self.stdout.write('  URLs (dev):')
        self.stdout.write('    http://pms.lvh.me:8000/')
        self.stdout.write('    http://lakeview.pms.lvh.me:8000/')
        self.stdout.write('    http://sunbird.pms.lvh.me:8000/')
        self.stdout.write('')

    # ─────────────────────────────────────────────────────────
    # Reset
    # ─────────────────────────────────────────────────────────

    def _reset_demo_tenants(self):
        self._section('Resetting demo tenants')
        for schema in ['lakeview', 'sunbird']:
            tenant = Tenant.objects.filter(schema_name=schema).first()
            if tenant:
                tenant.auto_drop_schema = True
                tenant.delete(force_drop=True)
                self._warn(f'Dropped schema: {schema}')
            # Also clean up users
            User.objects.filter(email__endswith=f'@{schema}.mw').delete()

    # ─────────────────────────────────────────────────────────
    # Platform: subscription plans
    # ─────────────────────────────────────────────────────────

    def _seed_subscription_plans(self):
        self._section('Subscription plans')

        from apps.shared.billing.models import SubscriptionPlan

        plans = [
            {
                'code': 'starter-monthly',
                'name': 'Starter',
                'tier': 'STARTER',
                'interval': 'MONTH',
                'price_mwk': Decimal('25000.00'),
                'price_usd': Decimal('15.00'),
                'max_properties': 1,
                'max_units': 10,
                'max_staff': 3,
                'max_storage_mb': 500,
                'includes_hospitality': True,
                'includes_rentals': False,
                'includes_sales': False,
                'includes_eis': True,
                'includes_whatsapp': True,
                'includes_priority_support': False,
                'display_order': 1,
                'description': 'Perfect for small guesthouses and single-property operations.',
                'features': [
                    '1 property · 10 units',
                    '3 staff accounts',
                    'Hospitality module',
                    'MRA EIS compliance',
                    'WhatsApp notifications',
                    'Offline PWA',
                ],
            },
            {
                'code': 'starter-annual',
                'name': 'Starter (Annual)',
                'tier': 'STARTER',
                'interval': 'YEAR',
                'price_mwk': Decimal('250000.00'),
                'price_usd': Decimal('150.00'),
                'max_properties': 1,
                'max_units': 10,
                'max_staff': 3,
                'max_storage_mb': 500,
                'includes_hospitality': True,
                'includes_eis': True,
                'includes_whatsapp': True,
                'display_order': 2,
                'description': 'Same as Starter, billed annually — 2 months free.',
                'features': [
                    '1 property · 10 units',
                    '3 staff accounts',
                    'Hospitality module',
                    'MRA EIS compliance',
                    'WhatsApp notifications',
                    '2 months free',
                ],
            },
            {
                'code': 'professional-monthly',
                'name': 'Professional',
                'tier': 'PRO',
                'interval': 'MONTH',
                'price_mwk': Decimal('60000.00'),
                'price_usd': Decimal('35.00'),
                'max_properties': 5,
                'max_units': 100,
                'max_staff': 15,
                'max_storage_mb': 5000,
                'includes_hospitality': True,
                'includes_rentals': True,
                'includes_sales': True,
                'includes_eis': True,
                'includes_whatsapp': True,
                'includes_priority_support': False,
                'display_order': 3,
                'description': 'For growing hotel groups and property managers.',
                'features': [
                    '5 properties · 100 units',
                    '15 staff accounts',
                    'Hospitality + Rentals + Sales',
                    'MRA EIS compliance',
                    'WhatsApp notifications',
                    '5 GB storage',
                ],
            },
            {
                'code': 'professional-annual',
                'name': 'Professional (Annual)',
                'tier': 'PRO',
                'interval': 'YEAR',
                'price_mwk': Decimal('600000.00'),
                'price_usd': Decimal('350.00'),
                'max_properties': 5,
                'max_units': 100,
                'max_staff': 15,
                'max_storage_mb': 5000,
                'includes_hospitality': True,
                'includes_rentals': True,
                'includes_sales': True,
                'includes_eis': True,
                'includes_whatsapp': True,
                'display_order': 4,
                'description': 'Professional billed annually — 2 months free.',
                'features': [
                    '5 properties · 100 units',
                    '15 staff accounts',
                    'All modules',
                    'MRA EIS compliance',
                    'WhatsApp notifications',
                    '2 months free',
                ],
            },
            {
                'code': 'enterprise-monthly',
                'name': 'Enterprise',
                'tier': 'ENT',
                'interval': 'MONTH',
                'price_mwk': Decimal('150000.00'),
                'price_usd': Decimal('90.00'),
                'max_properties': 0,
                'max_units': 0,
                'max_staff': 0,
                'max_storage_mb': 0,
                'includes_hospitality': True,
                'includes_rentals': True,
                'includes_sales': True,
                'includes_eis': True,
                'includes_whatsapp': True,
                'includes_priority_support': True,
                'display_order': 5,
                'description': 'Unlimited scale with priority support.',
                'features': [
                    'Unlimited properties · units · staff',
                    'All modules',
                    'Priority support',
                    'Unlimited storage',
                    'Custom integrations',
                ],
            },
        ]

        for plan_data in plans:
            code = plan_data.pop('code')
            SubscriptionPlan.objects.update_or_create(
                code=code, defaults=plan_data,
            )
            plan_data['code'] = code  # restore for readability

        self._ok(f'{len(plans)} subscription plans seeded')

    # ─────────────────────────────────────────────────────────
    # Platform: public tenant + platform admin
    # ─────────────────────────────────────────────────────────

    def _seed_public_tenant(self):
        self._section('Public tenant')

        public, created = Tenant.objects.get_or_create(
            schema_name='public',
            defaults={
                'name': 'Pritech PMS',
                'plan': 'ENT',
                'on_trial': False,
                'is_active': True,
                'contact_email': 'support@pritechmw.com',
                'contact_phone': '+265 99 123 4567',
                'default_language': 'en',
            },
        )

        # Add both dev and prod domains so either works
        for domain in ['pms.lvh.me', 'pms.pritechmw.com']:
            Domain.objects.get_or_create(
                domain=domain,
                defaults={'tenant': public, 'is_primary': domain == 'pms.lvh.me'},
            )

        if created:
            self._ok('Created public tenant')
        else:
            self._ok('Public tenant already exists')

    def _seed_platform_admin(self):
        self._section('Platform admin')

        email = 'admin@pritechmw.com'
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': 'Platform',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
                'is_platform_admin': True,
                'is_active': True,
            },
        )
        if created:
            user.set_password('PlatformAdmin2026!')
            user.save()
            self._ok(f'Created platform admin: {email}')
        else:
            self._ok(f'Platform admin already exists: {email}')

    # ─────────────────────────────────────────────────────────
    # Lakeview Lodge — full demo
    # ─────────────────────────────────────────────────────────

    def _seed_lakeview(self):
        self._section('Tenant: Lakeview Lodge')

        tenant = self._get_or_create_tenant(
            schema_name='lakeview',
            name='Lakeview Lodge',
            contact_name='Chikondi Banda',
            contact_email='admin@lakeview.mw',
            contact_phone='+265 99 123 4567',
            plan_tier='PRO',
        )

        # ── Users (public schema) ─────────────────────────────
        self._create_tenant_users(
            tenant,
            users=[
                ('admin@lakeview.mw', 'Chikondi', 'Banda', 'TADMIN', True),
                ('manager@lakeview.mw', 'Thandiwe', 'Mwale', 'MGR', True),
                ('desk@lakeview.mw', 'Mphatso', 'Phiri', 'FD', True),
                ('housekeeping@lakeview.mw', 'Grace', 'Chirwa', 'HK', False),
                ('accounts@lakeview.mw', 'Chisomo', 'Tembo', 'ACC', True),
            ],
            password='LakeviewDemo2026!',
        )

        # ── Tenant-schema data ─────────────────────────────────
        with schema_context('lakeview'):
            self._seed_lakeview_content(tenant)

        self._ok('Lakeview Lodge seeded')

    def _seed_lakeview_content(self, tenant):
        """Everything inside the lakeview schema."""
        amenities = self._seed_amenities()
        properties = self._seed_lakeview_properties()
        units = self._seed_lakeview_units(properties, amenities)
        rate_plans = self._seed_lakeview_rate_plans(properties)
        guests = self._seed_lakeview_guests()
        self._seed_lakeview_reservations(properties, units, rate_plans, guests)
        self._seed_lakeview_leases(properties, units, guests)
        self._seed_lakeview_maintenance(units, guests)
        self._seed_lakeview_sales(properties)
        self._seed_lakeview_compliance(properties)
        self._seed_lakeview_communications()

    # ── Amenities ─────────────────────────────────────────────

    def _seed_amenities(self):
        from apps.core.properties.models import Amenity

        specs = [
            ('Wi-Fi', 'ROOM', 'wifi'),
            ('Air Conditioning', 'ROOM', 'ac_unit'),
            ('En-suite Bathroom', 'ROOM', 'bathtub'),
            ('Hot Shower', 'ROOM', 'shower'),
            ('TV', 'ROOM', 'tv'),
            ('Minibar', 'ROOM', 'local_bar'),
            ('Balcony', 'ROOM', 'balcony'),
            ('Lake View', 'ROOM', 'water'),
            ('Kitchenette', 'ROOM', 'kitchen'),
            ('Swimming Pool', 'PROPERTY', 'pool'),
            ('Restaurant', 'PROPERTY', 'restaurant'),
            ('Bar', 'PROPERTY', 'local_bar'),
            ('Parking', 'PROPERTY', 'local_parking'),
            ('Garden', 'PROPERTY', 'park'),
            ('Beach Access', 'PROPERTY', 'beach_access'),
            ('Boat Dock', 'PROPERTY', 'sailing'),
            ('Room Service', 'SERVICE', 'room_service'),
            ('Laundry', 'SERVICE', 'local_laundry_service'),
            ('Airport Transfer', 'SERVICE', 'airport_shuttle'),
            ('Safari Tours', 'SERVICE', 'explore'),
        ]

        created = []
        for name, category, icon in specs:
            obj, _ = Amenity.objects.update_or_create(
                name=name,
                defaults={'category': category, 'icon': icon},
            )
            created.append(obj)

        self._log(f'Amenities: {len(created)}')
        return {a.name: a for a in created}

    # ── Properties ────────────────────────────────────────────

    def _seed_lakeview_properties(self):
        from apps.core.properties.models import Property

        specs = [
            {
                'name': 'Lakeview Lodge',
                'property_type': 'LODGE',
                'address': 'Cape Maclear Road, Chembe Village',
                'district': 'Mangochi',
                'region': 'SOUTH',
                'phone': '+265 99 123 4567',
                'email': 'stay@lakeview.mw',
                'description': (
                    'A boutique lakeside lodge on the shores of Lake Malawi. '
                    'Six chalets and two rooms, all with lake views. '
                    'Restaurant, bar, swimming pool, and private beach access.'
                ),
                'public_headline': 'Lakeside chalets with pristine views',
                'featured': True,
                'is_public': True,
                'status': 'ACTIVE',
            },
            {
                'name': 'Lakeview Rentals',
                'property_type': 'RENTAL',
                'address': 'Area 47, Sector 3',
                'district': 'Lilongwe',
                'region': 'CENTRAL',
                'phone': '+265 99 123 4568',
                'email': 'rentals@lakeview.mw',
                'description': (
                    'Four modern apartments and one standalone house in '
                    'Lilongwe. Fully furnished, secure compound, backup '
                    'water and power.'
                ),
                'public_headline': 'Executive rentals in Lilongwe',
                'is_public': True,
                'status': 'ACTIVE',
            },
            {
                'name': 'Lakeview Villas',
                'property_type': 'HOUSE',
                'address': 'Namiwawa, Plot 47',
                'district': 'Blantyre',
                'region': 'SOUTH',
                'phone': '+265 99 123 4569',
                'email': 'sales@lakeview.mw',
                'description': (
                    'Two newly built four-bedroom villas for sale in '
                    'Blantyre. Title deed ready, solar backup, borehole.'
                ),
                'public_headline': 'New villas in Namiwawa',
                'is_public': True,
                'status': 'ACTIVE',
            },
        ]

        result = {}
        for spec in specs:
            name = spec.pop('name')
            prop, _ = Property.objects.update_or_create(
                name=name, defaults=spec,
            )
            result[name] = prop

        self._log(f'Properties: {len(result)}')
        return result

    # ── Units ─────────────────────────────────────────────────

    def _seed_lakeview_units(self, properties, amenities):
        from apps.core.properties.models import Unit

        lodge = properties['Lakeview Lodge']
        rentals = properties['Lakeview Rentals']
        villas = properties['Lakeview Villas']

        specs = [
            # Lakeview Lodge — 4 chalets, 2 rooms
            (lodge, 'Chalet A', 'CHALET', 2, 1, 1, '120000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Lake View', 'Balcony']),
            (lodge, 'Chalet B', 'CHALET', 2, 1, 1, '120000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Lake View', 'Balcony']),
            (lodge, 'Chalet C', 'CHALET', 2, 2, 2, '150000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Lake View', 'Balcony']),
            (lodge, 'Chalet D', 'CHALET', 2, 2, 2, '150000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Lake View', 'Balcony']),
            (lodge, 'Room 101', 'ROOM', 2, 0, 1, '65000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower']),
            (lodge, 'Room 102', 'ROOM', 2, 0, 1, '65000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower']),
            # Lakeview Rentals — 4 apartments, 1 house
            (rentals, 'Apt 1A', 'APT', 2, 2, 2, '450000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Kitchenette', 'Parking']),
            (rentals, 'Apt 1B', 'APT', 2, 2, 2, '450000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Kitchenette', 'Parking']),
            (rentals, 'Apt 2A', 'APT', 3, 1, 3, '600000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Kitchenette', 'Parking']),
            (rentals, 'Apt 2B', 'APT', 3, 1, 3, '600000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Kitchenette', 'Parking']),
            (rentals, 'House 5', 'HOUSE', 4, 2, 4, '1200000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Kitchenette', 'Parking', 'Garden']),
            # Lakeview Villas — for sale
            (villas, 'Villa 1', 'HOUSE', 4, 2, 4, '250000000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Kitchenette', 'Parking', 'Garden']),
            (villas, 'Villa 2', 'HOUSE', 4, 2, 4, '320000000', ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'Hot Shower', 'Kitchenette', 'Parking', 'Garden']),
        ]

        result = {}
        for prop, identifier, unit_type, adults, children, beds, rate, amenity_names in specs:
            unit, _ = Unit.objects.update_or_create(
                property=prop,
                identifier=identifier,
                defaults={
                    'unit_type': unit_type,
                    'capacity_adults': adults,
                    'capacity_children': children,
                    'bed_count': beds,
                    'base_rate_mwk': Decimal(rate),
                    'is_public': True,
                    'is_active': True,
                    'status': 'AVAIL',
                },
            )
            for name in amenity_names:
                if name in amenities:
                    unit.amenities.add(amenities[name])
            result[identifier] = unit

        self._log(f'Units: {len(result)}')
        return result

    # ── Rate plans ────────────────────────────────────────────

    def _seed_lakeview_rate_plans(self, properties):
        from apps.hospitality.rates.models import RatePlan

        lodge = properties['Lakeview Lodge']

        specs = [
            {
                'name': 'Flexible Rate',
                'policy': 'FLEX',
                'deposit_percentage': Decimal('0'),
                'cancellation_hours': 48,
            },
            {
                'name': 'Non-Refundable',
                'policy': 'NONREF',
                'deposit_percentage': Decimal('100'),
                'cancellation_hours': 0,
            },
            {
                'name': 'Bed & Breakfast',
                'policy': 'BB',
                'deposit_percentage': Decimal('30'),
                'cancellation_hours': 72,
            },
        ]

        result = {}
        for spec in specs:
            name = spec.pop('name')
            plan, _ = RatePlan.objects.update_or_create(
                property=lodge, name=name, defaults=spec,
            )
            result[name] = plan

        self._log(f'Rate plans: {len(result)}')
        return result

    # ── Guests / People ───────────────────────────────────────

    def _seed_lakeview_guests(self):
        from apps.core.people.models import Person

        specs = [
            # Malawian guests
            {'first_name': 'Chikondi', 'last_name': 'Banda', 'phone_primary': '+265991111001', 'email': 'chikondi@example.mw', 'nationality': 'Malawian', 'district': 'Lilongwe'},
            {'first_name': 'Thandiwe', 'last_name': 'Mwale', 'phone_primary': '+265991111002', 'email': 'thandiwe@example.mw', 'nationality': 'Malawian', 'district': 'Blantyre'},
            {'first_name': 'Mphatso', 'last_name': 'Phiri', 'phone_primary': '+265991111003', 'email': 'mphatso@example.mw', 'nationality': 'Malawian', 'district': 'Mzuzu'},
            {'first_name': 'Grace', 'last_name': 'Chirwa', 'phone_primary': '+265991111004', 'email': 'grace@example.mw', 'nationality': 'Malawian', 'district': 'Zomba'},
            {'first_name': 'Chisomo', 'last_name': 'Tembo', 'phone_primary': '+265991111005', 'email': 'chisomo@example.mw', 'nationality': 'Malawian', 'district': 'Kasungu'},
            {'first_name': 'Takondwa', 'last_name': 'Nkhoma', 'phone_primary': '+265991111006', 'email': 'takondwa@example.mw', 'nationality': 'Malawian', 'district': 'Mangochi'},
            # Foreign guests
            {'first_name': 'James', 'last_name': 'Whitfield', 'phone_primary': '+447700900001', 'email': 'james.whitfield@example.uk', 'nationality': 'British', 'id_type': 'PASS', 'id_number': 'GB1234567'},
            {'first_name': 'Hans', 'last_name': 'Müller', 'phone_primary': '+4915112345678', 'email': 'hans.mueller@example.de', 'nationality': 'German', 'id_type': 'PASS', 'id_number': 'DE7654321'},
            {'first_name': 'Linda', 'last_name': 'Chen', 'phone_primary': '+8613800138000', 'email': 'linda.chen@example.cn', 'nationality': 'Chinese', 'id_type': 'PASS', 'id_number': 'CN9876543'},
            {'first_name': 'Sarah', 'last_name': 'Anderson', 'phone_primary': '+12025550101', 'email': 'sarah.anderson@example.us', 'nationality': 'American', 'id_type': 'PASS', 'id_number': 'US5551234'},
        ]

        result = []
        for spec in specs:
            phone = spec['phone_primary']
            person, _ = Person.objects.update_or_create(
                phone_primary=phone,
                defaults=spec,
            )
            result.append(person)

        self._log(f'Guests: {len(result)}')
        return result

    # ── Reservations ──────────────────────────────────────────

    def _seed_lakeview_reservations(self, properties, units, rate_plans, guests):
        from apps.hospitality.reservations.models import Reservation, ReservationRoom
        from apps.hospitality.folios.models import Folio, FolioCharge, FolioPayment

        lodge = properties['Lakeview Lodge']
        today = timezone.now().date()
        flexible = rate_plans.get('Flexible Rate')
        bb = rate_plans.get('Bed & Breakfast')

        specs = [
            # (guest_idx, unit_id, check_in_offset, check_out_offset, status, rate, num_nights_charged)
            # Currently staying
            (0, 'Chalet A', -2, +2, 'CHIN', '120000', 2),
            (5, 'Chalet C', -1, +3, 'CHIN', '150000', 1),
            (6, 'Chalet D', -3, +2, 'CHIN', '150000', 3),
            # Arriving today
            (1, 'Room 101', 0, +2, 'CONF', '65000', 0),
            (2, 'Room 102', 0, +1, 'CONF', '65000', 0),
            # Future
            (7, 'Chalet B', +5, +8, 'CONF', '120000', 0),
            (8, 'Chalet C', +10, +14, 'CONF', '150000', 0),
            # Checked out
            (3, 'Chalet A', -10, -8, 'CHOUT', '120000', 2),
            (4, 'Chalet B', -15, -12, 'CHOUT', '120000', 3),
            (9, 'Chalet D', -7, -5, 'CHOUT', '150000', 2),
            # Cancelled
            (2, 'Room 101', +3, +5, 'CANC', '65000', 0),
            # No-show
            (4, 'Room 102', -1, +1, 'NOSH', '65000', 0),
        ]

        created_count = 0
        for guest_idx, unit_id, ci_off, co_off, status, rate, nights_charged in specs:
            unit = units[unit_id]
            guest = guests[guest_idx]
            check_in = today + timedelta(days=ci_off)
            check_out = today + timedelta(days=co_off)

            # Idempotency: same guest + same check_in
            reservation, created = Reservation.objects.get_or_create(
                primary_guest=guest,
                property=lodge,
                check_in=check_in,
                defaults={
                    'status': status,
                    'source': 'WALK' if guest_idx < 6 else 'WEBSITE',
                    'check_out': check_out,
                    'adults': 2,
                    'children': 0,
                    'rate_plan': flexible if guest_idx % 2 == 0 else bb,
                },
            )
            if not created:
                continue
            created_count += 1

            ReservationRoom.objects.create(
                reservation=reservation,
                unit=unit,
                rate_per_night=Decimal(rate),
                rate_currency='MWK',
                actual_check_in=(
                    timezone.now() - timedelta(days=abs(ci_off))
                    if status == 'CHIN' else None
                ),
                actual_check_out=(
                    timezone.now() - timedelta(days=abs(co_off))
                    if status == 'CHOUT' else None
                ),
            )

            # Create folio for anyone who was checked in or stayed
            if status in ('CHIN', 'CHOUT'):
                folio, _ = Folio.objects.get_or_create(
                    reservation=reservation,
                    defaults={'currency': 'MWK'},
                )
                # Room charges for nights already charged
                if nights_charged > 0:
                    FolioCharge.objects.get_or_create(
                        folio=folio,
                        charge_type='ROOM',
                        description=f'Room charge — {unit.identifier}',
                        defaults={
                            'amount': Decimal(rate) * nights_charged,
                            'currency': 'MWK',
                        },
                    )
                    # Tourism Levy (1%)
                    FolioCharge.objects.get_or_create(
                        folio=folio,
                        charge_type='LEVY',
                        description='Tourism Levy (1%)',
                        defaults={
                            'amount': (Decimal(rate) * nights_charged / 100).quantize(Decimal('0.01')),
                            'currency': 'MWK',
                        },
                    )

                # Some F&B for the first guest
                if guest_idx == 0:
                    FolioCharge.objects.get_or_create(
                        folio=folio,
                        charge_type='FNB',
                        description='Dinner — restaurant',
                        defaults={'amount': Decimal('35000'), 'currency': 'MWK'},
                    )

                # Payment — checked-out guests fully paid, checked-in partial
                payments = [{
                    'method': 'CASH_MWK',
                    'amount': Decimal(rate) * nights_charged if status == 'CHOUT'
                              else (Decimal(rate) * nights_charged) / 2,
                    'currency': 'MWK',
                    'reference': '',
                }] if nights_charged > 0 else []

                for p in payments:
                    FolioPayment.objects.get_or_create(
                        folio=folio,
                        method=p['method'],
                        amount=p['amount'],
                        defaults={'currency': p['currency'], 'reference': p['reference']},
                    )

        self._log(f'Reservations: {created_count} created ({len(specs)} total in specs)')

    # ── Leases + rent invoices ────────────────────────────────

    def _seed_lakeview_leases(self, properties, units, guests):
        from apps.property.leases.models import Lease
        from apps.property.rent_invoicing.models import (
            RentInvoice, RentInvoiceLine, RentPayment,
        )

        rentals = properties['Lakeview Rentals']
        today = timezone.now().date()

        specs = [
            # (unit_id, guest_idx, start_offset_months, duration_months, rent, status)
            ('Apt 1A', 0, -6, 12, '450000', 'ACT'),
            ('Apt 1B', 1, -3, 12, '450000', 'ACT'),
            ('Apt 2A', 2, -12, 12, '600000', 'ACT'),
            ('House 5', 3, -18, 12, '1200000', 'EXP'),
        ]

        for unit_id, guest_idx, start_off, duration, rent, status in specs:
            unit = units[unit_id]
            tenant = guests[guest_idx]

            start = today + timedelta(days=start_off * 30)
            end = start + timedelta(days=duration * 30)

            lease, created = Lease.objects.get_or_create(
                unit=unit,
                tenant=tenant,
                defaults={
                    'status': status,
                    'start_date': start,
                    'end_date': end,
                    'rent_amount': Decimal(rent),
                    'rent_currency': 'MWK',
                    'payment_frequency': 'MONTH',
                    'payment_due_day': 5,
                    'deposit_amount': Decimal(rent),
                    'deposit_received': Decimal(rent),
                    'escalation_percent': Decimal('5.00'),
                    'grace_period_days': 5,
                },
            )
            if not created:
                continue

            # Only generate invoices for active leases
            if status != 'ACT':
                continue

            # Three past invoices per lease
            for month_offset in range(1, 4):
                period_start = today.replace(day=1) - timedelta(days=month_offset * 30)
                period_start = period_start.replace(day=1)
                period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                due_date = period_start.replace(day=5)

                invoice, inv_created = RentInvoice.objects.get_or_create(
                    lease=lease,
                    period_start=period_start,
                    defaults={
                        'tenant': tenant,
                        'unit': unit,
                        'period_end': period_end,
                        'due_date': due_date,
                        'status': 'PAID' if month_offset > 1 else 'ISSUED',
                        'currency': 'MWK',
                    },
                )
                if not inv_created:
                    continue

                RentInvoiceLine.objects.create(
                    invoice=invoice,
                    line_type='RENT',
                    description=f'Monthly rent — {unit.identifier}',
                    amount=Decimal(rent),
                )
                invoice.recalculate_totals()

                # Pay older invoices, leave current unpaid
                if month_offset > 1:
                    RentPayment.objects.create(
                        invoice=invoice,
                        method='AIRTEL_MONEY',
                        amount=Decimal(rent),
                        currency='MWK',
                        reference=f'AIR{invoice.invoice_number[-6:]}',
                    )
                    invoice.recalculate_totals()

        self._log('Leases and rent invoices seeded')

    # ── Maintenance ───────────────────────────────────────────

    def _seed_lakeview_maintenance(self, units, guests):
        from apps.property.maintenance.models import MaintenanceRequest

        specs = [
            ('Chalet B', 'PLUMB', 'HIGH', 'IN_PROGRESS',
             'Leaking shower head', 'The shower head in Chalet B is dripping constantly.'),
            ('Apt 1B', 'ELEC', 'MED', 'SUBMITTED',
             'Living room light not working', 'One of the ceiling lights stopped working yesterday.'),
            ('House 5', 'PEST', 'LOW', 'SUBMITTED',
             'Ants in the kitchen', 'Small ants appearing near the kitchen sink.'),
            ('Chalet D', 'APPL', 'MED', 'COMPLETED',
             'Fridge not cooling', 'The mini fridge stopped cooling. Fixed by replacing thermostat.'),
            ('Apt 2A', 'STRUC', 'LOW', 'VERIFIED',
             'Crack in bathroom wall', 'Hairline crack in the bathroom wall, cosmetic.'),
        ]

        for unit_id, category, priority, status, title, description in specs:
            unit = units[unit_id]
            MaintenanceRequest.objects.get_or_create(
                unit=unit,
                title=title,
                defaults={
                    'category': category,
                    'priority': priority,
                    'status': status,
                    'description': description,
                    'submitted_by': guests[0] if guests else None,
                },
            )

        self._log(f'Maintenance: {len(specs)} requests')

    # ── Sales ─────────────────────────────────────────────────

    def _seed_lakeview_sales(self, properties):
        from apps.property.sales.models import SaleListing, SaleOffer

        villas = properties['Lakeview Villas']

        listing_1, created = SaleListing.objects.get_or_create(
            property=villas,
            defaults={
                'asking_price': Decimal('250000000'),
                'minimum_price': Decimal('230000000'),
                'currency': 'MWK',
                'status': 'LISTED',
                'description': (
                    'Brand new 4-bedroom villa in Namiwawa. Title deed ready. '
                    'Solar backup, borehole, secure wall.'
                ),
            },
        )

        listing_2, created2 = SaleListing.objects.get_or_create(
            property=villas,
            defaults={
                'asking_price': Decimal('320000000'),
                'minimum_price': Decimal('300000000'),
                'currency': 'MWK',
                'status': 'LISTED',
                'description': (
                    'Premium 4-bedroom villa with double garage and garden. '
                    'Ready to move in.'
                ),
            },
        )

        self._log(f'Sale listings: 2')

    # ── Compliance ────────────────────────────────────────────

    def _seed_lakeview_compliance(self, properties):
        from apps.compliance.eis.models import EISTerminal
        from apps.compliance.tourism_levy.models import TourismLevyConfig
        from apps.compliance.forex.models import ForexRate

        lodge = properties['Lakeview Lodge']

        # EIS terminal for Lakeview Lodge
        EISTerminal.objects.get_or_create(
            terminal_code='LW-001',
            defaults={
                'property': lodge,
                'tin': '1234567890',
                'trading_name': 'Lakeview Lodge',
                'status': 'PENDING',
            },
        )

        # Tourism Levy config
        TourismLevyConfig.objects.get_or_create(
            property=lodge,
            defaults={
                'levy_percent': Decimal('1.00'),
                'is_active': True,
                'effective_from': timezone.now().date(),
            },
        )

        # Forex rates
        rates = [
            ('USD', Decimal('1750.000000')),
            ('EUR', Decimal('1900.000000')),
            ('GBP', Decimal('2200.000000')),
        ]
        for quote, rate in rates:
            ForexRate.objects.update_or_create(
                base_currency='MWK',
                quote_currency=quote,
                effective_to__isnull=True,
                defaults={
                    'rate': rate,
                    'source': 'MAN',
                    'effective_from': timezone.now(),
                },
            )

        self._log('Compliance: EIS terminal, levy config, forex rates')

    # ── Communications ────────────────────────────────────────

    def _seed_lakeview_communications(self):
        from apps.communications.models import NotificationTemplate

        templates = [
            {
                'event': 'booking_confirmed',
                'channel': 'WA',
                'name': 'booking_confirmation',
                'body': (
                    'Hello {guest_name}, your booking at {property_name} is '
                    'confirmed for {check_in} to {check_out}. '
                    'Reference: {reservation_number}. We look forward to welcoming you.'
                ),
            },
            {
                'event': 'payment_receipt',
                'channel': 'WA',
                'name': 'payment_receipt',
                'body': (
                    'Dear {guest_name}, we received your payment of '
                    '{amount} {currency}. Your remaining balance is {balance}. Thank you.'
                ),
            },
            {
                'event': 'check_in_reminder',
                'channel': 'WA',
                'name': 'check_in_reminder',
                'body': (
                    'Hello {guest_name}, this is a reminder that your stay at '
                    '{property_name} begins on {check_in}. See you soon!'
                ),
            },
            {
                'event': 'checkout_thanks',
                'channel': 'WA',
                'name': 'checkout_thanks',
                'body': (
                    'Thank you for staying with us, {guest_name}. We hope you '
                    'enjoyed your visit. Please leave a review if you have a moment.'
                ),
            },
            {
                'event': 'rent_due',
                'channel': 'WA',
                'name': 'rent_due',
                'body': (
                    'Hi {guest_name}, this is a reminder that your rent of '
                    '{amount} {currency} for {unit_identifier} is due on {due_date}.'
                ),
            },
        ]

        for spec in templates:
            NotificationTemplate.objects.update_or_create(
                event=spec['event'],
                channel=spec['channel'],
                language='en',
                defaults={
                    'name': spec['name'],
                    'body': spec['body'],
                    'is_active': True,
                },
            )

        self._log(f'Notification templates: {len(templates)}')

    # ─────────────────────────────────────────────────────────
    # Sunbird Hotel — smaller demo, hospitality only
    # ─────────────────────────────────────────────────────────

    def _seed_sunbird(self):
        self._section('Tenant: Sunbird Hotel')

        tenant = self._get_or_create_tenant(
            schema_name='sunbird',
            name='Sunbird Hotel',
            contact_name='Linda Chen',
            contact_email='admin@sunbird.mw',
            contact_phone='+265 99 234 5678',
            plan_tier='STARTER',
        )

        self._create_tenant_users(
            tenant,
            users=[
                ('admin@sunbird.mw', 'Linda', 'Chen', 'TADMIN', True),
                ('desk@sunbird.mw', 'Mphatso', 'Nkhoma', 'FD', True),
            ],
            password='SunbirdDemo2026!',
        )

        with schema_context('sunbird'):
            self._seed_sunbird_content(tenant)

        self._ok('Sunbird Hotel seeded')

    def _seed_sunbird_content(self, tenant):
        from apps.core.properties.models import Amenity, Property, Unit
        from apps.hospitality.rates.models import RatePlan

        # Minimal amenities
        amenities = {}
        for name, category in [
            ('Wi-Fi', 'ROOM'), ('Air Conditioning', 'ROOM'),
            ('En-suite Bathroom', 'ROOM'), ('TV', 'ROOM'),
            ('Parking', 'PROPERTY'), ('Restaurant', 'PROPERTY'),
        ]:
            obj, _ = Amenity.objects.update_or_create(
                name=name, defaults={'category': category},
            )
            amenities[name] = obj

        # One property
        hotel, _ = Property.objects.update_or_create(
            name='Sunbird Hotel Lilongwe',
            defaults={
                'property_type': 'HOTEL',
                'address': 'Independence Drive, City Centre',
                'district': 'Lilongwe',
                'region': 'CENTRAL',
                'phone': '+265 99 234 5678',
                'email': 'stay@sunbird.mw',
                'description': (
                    'Mid-range city hotel in Lilongwe city centre. '
                    'Eight rooms, restaurant, and secure parking.'
                ),
                'is_public': True,
                'status': 'ACTIVE',
            },
        )

        # Rooms
        for i in range(1, 9):
            unit, _ = Unit.objects.update_or_create(
                property=hotel,
                identifier=f'Room {100 + i}',
                defaults={
                    'unit_type': 'ROOM',
                    'capacity_adults': 2,
                    'capacity_children': 0,
                    'bed_count': 1,
                    'base_rate_mwk': Decimal('85000'),
                    'is_public': True,
                    'status': 'AVAIL',
                },
            )
            for name in ['Wi-Fi', 'Air Conditioning', 'En-suite Bathroom', 'TV']:
                if name in amenities:
                    unit.amenities.add(amenities[name])

        # Rate plans
        for name, policy in [('Standard Rate', 'FLEX'), ('Non-Refundable', 'NONREF')]:
            RatePlan.objects.update_or_create(
                property=hotel, name=name,
                defaults={'policy': policy},
            )

        self._log('Sunbird content seeded')

    # ─────────────────────────────────────────────────────────
    # Shared tenant helpers
    # ─────────────────────────────────────────────────────────

    def _get_or_create_tenant(self, schema_name, name, contact_name,
                              contact_email, contact_phone, plan_tier):
        """Create tenant + domain + subscription in one atomic block."""
        from apps.shared.billing.models import SubscriptionPlan
        from apps.shared.billing.services import start_trial

        tenant = Tenant.objects.filter(schema_name=schema_name).first()
        created = False

        if not tenant:
            plan = SubscriptionPlan.objects.filter(
                tier=plan_tier, is_active=True, is_public=True,
            ).order_by('price_mwk').first()

            tenant = provision_tenant(
                name=name,
                schema_name=schema_name,
                domain_name=f'{schema_name}.pms.lvh.me',
                plan=plan_tier,
                admin_email=None,
                admin_password=None,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                modules=['HOSPITALITY', 'PROPERTY_RENTALS', 'PROPERTY_SALES']
                    if plan_tier == 'PRO' else ['HOSPITALITY'],
            )
            created = True

        # Ensure domains
        for domain in [f'{schema_name}.pms.lvh.me',
                       f'{schema_name}.pms.pritechmw.com']:
            Domain.objects.get_or_create(
                domain=domain,
                defaults={'tenant': tenant, 'is_primary': 'lvh' in domain},
            )

        # Ensure a subscription exists
        if not hasattr(tenant, 'subscription'):
            start_trial(tenant)

        self._ok(f'Tenant {schema_name}: {"created" if created else "exists"}')
        return tenant

    def _create_tenant_users(self, tenant, users, password):
        """
        users: list of (email, first_name, last_name, role, is_staff)
        """
        for email, first_name, last_name, role, is_staff in users:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'is_staff': is_staff,
                    'is_active': True,
                },
            )
            if created:
                user.set_password(password)
                user.save()

            UserTenantMembership.objects.get_or_create(
                user=user, tenant=tenant,
                defaults={'role': role, 'is_active': True},
            )