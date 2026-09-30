# apps/core/properties/views.py
"""
Public property browsing views plus the tenant home landing page.

All views here are available to anonymous visitors. Data is
automatically scoped to the current tenant schema by django-tenants —
no manual filtering by tenant is needed.

Three public-facing pages:

    PropertyListView   → /properties/         (hotels & lodges)
    RentListView       → /properties/rent/    (vacant rentals)
    PropertyDetailView → /properties/<pk>/    (single property)

And one guest landing page:

    TenantHomeView     → /                    (tenant home, guest-facing)
"""
from django.db.models import Count, Min, Prefetch, Q
from django.shortcuts import redirect
from django.views.generic import DetailView, ListView, TemplateView

from .models import Property, Unit


# ─────────────────────────────────────────────────────────────────────
# Listing pages
# ─────────────────────────────────────────────────────────────────────

class PropertyListView(ListView):
    """
    Public list of active, published properties with search and filtering.

    Only shows properties flagged `is_public=True` and `status=ACTIVE`.
    Ranked by name; annotated with unit counts for the availability chip.
    """
    model = Property
    template_name = 'pages/properties/list.html'
    context_object_name = 'properties'
    paginate_by = 12

    def get_queryset(self):
        qs = (
            Property.objects
            .filter(status=Property.Status.ACTIVE, is_public=True)
            .annotate(
                unit_count=Count('units', filter=Q(units__is_active=True)),
                available_count=Count(
                    'units',
                    filter=Q(
                        units__is_active=True,
                        units__is_public=True,
                        units__status=Unit.Status.AVAILABLE,
                    ),
                ),
            )
            .prefetch_related('images')
            .order_by('name')
        )

        # Free-text search across name, district, description
        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(district__icontains=search) |
                Q(description__icontains=search)
            )

        # Property type filter
        property_type = self.request.GET.get('type', '').strip()
        if property_type in Property.PropertyType.values:
            qs = qs.filter(property_type=property_type)

        # Region filter
        region = self.request.GET.get('region', '').strip()
        if region in Property.Region.values:
            qs = qs.filter(region=region)

        # District filter (free-form, matches stored text exactly)
        district = self.request.GET.get('district', '').strip()
        if district:
            qs = qs.filter(district__iexact=district)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['property_types'] = Property.PropertyType.choices
        ctx['regions'] = Property.Region.choices
        ctx['districts'] = (
            Property.objects
            .filter(status=Property.Status.ACTIVE, is_public=True)
            .exclude(district='')
            .values_list('district', flat=True)
            .distinct()
            .order_by('district')
        )
        ctx['current_filters'] = {
            'q': self.request.GET.get('q', ''),
            'type': self.request.GET.get('type', ''),
            'region': self.request.GET.get('region', ''),
            'district': self.request.GET.get('district', ''),
        }
        return ctx


class PropertyDetailView(DetailView):
    """
    Public detail view of a single property with its units and photos.

    Prefetches active units and their amenities + images so the template
    doesn't N+1. Splits units into available vs unavailable for display.
    """
    model = Property
    template_name = 'pages/properties/detail.html'
    context_object_name = 'property'

    def get_queryset(self):
        return (
            Property.objects
            .filter(status=Property.Status.ACTIVE, is_public=True)
            .prefetch_related(
                'images',
                Prefetch(
                    'units',
                    queryset=Unit.objects
                        .filter(is_active=True)
                        .prefetch_related('amenities', 'images')
                        .order_by('identifier'),
                    to_attr='active_units',
                ),
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        units = self.object.active_units
        ctx['available_units'] = [
            u for u in units if u.status == Unit.Status.AVAILABLE
        ]
        ctx['unavailable_units'] = [
            u for u in units if u.status != Unit.Status.AVAILABLE
        ]
        return ctx


class RentListView(ListView):
    """
    Public page showing vacant rental units (apartments and houses only).

    Reuses the Unit model — no separate data structure needed. Only
    surfaces units that are:
      • is_public = True
      • is_active = True
      • status = AVAILABLE
      • unit_type in (APARTMENT, HOUSE)
      • belong to a public, active property
    """
    model = Unit
    template_name = 'pages/properties/rent_list.html'
    context_object_name = 'units'
    paginate_by = 12

    def get_queryset(self):
        qs = (
            Unit.objects
            .filter(
                is_public=True,
                is_active=True,
                status=Unit.Status.AVAILABLE,
                unit_type__in=[
                    Unit.UnitType.APARTMENT,
                    Unit.UnitType.HOUSE,
                ],
                property__status=Property.Status.ACTIVE,
                property__is_public=True,
            )
            .select_related('property')
            .prefetch_related('amenities', 'images')
            .order_by('property__district', 'base_rate_mwk')
        )

        district = self.request.GET.get('district', '').strip()
        if district:
            qs = qs.filter(property__district__iexact=district)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['districts'] = (
            Property.objects
            .filter(is_public=True, status=Property.Status.ACTIVE)
            .exclude(district='')
            .values_list('district', flat=True)
            .distinct()
            .order_by('district')
        )
        ctx['current_district'] = self.request.GET.get('district', '')
        return ctx


# ─────────────────────────────────────────────────────────────────────
# Tenant home page — the guest-facing landing page
# ─────────────────────────────────────────────────────────────────────

class TenantHomeView(TemplateView):
    """
    The tenant's guest-facing home page at `/`.

    Shows:
      • Hero with live stat counts (rooms available, vacant rentals)
      • Featured hospitality (hotels & lodges with rooms ready to book)
      • Recently added vacant rentals
      • WhatsApp CTA at the bottom

    Behavior:
      • Anonymous visitors and non-staff see the marketing page.
      • Authenticated staff are redirected to the /dashboard/ view,
        which is their daily tool hub.

    All data is automatically scoped to the current tenant schema.
    """
    template_name = 'pages/home.html'

    def get(self, request, *args, **kwargs):
        # Staff bypass the guest home — send them to the dashboard
        if request.user.is_authenticated and request.user.is_staff:
            return redirect('dashboard')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # ── Featured hospitality ─────────────────────────────────────
        # Rank by: photo count (trust signal), then available rooms,
        # then alphabetical. Limited to hotels and lodges only — this
        # carousel is for places to stay, not long-term rentals.
        ctx['featured_hospitality'] = (
            Property.objects
            .filter(
                is_public=True,
                status=Property.Status.ACTIVE,
                property_type__in=[
                    Property.PropertyType.HOTEL,
                    Property.PropertyType.LODGE,
                ],
            )
            .annotate(
                available_count=Count(
                    'units',
                    filter=Q(
                        units__is_public=True,
                        units__is_active=True,
                        units__status=Unit.Status.AVAILABLE,
                    ),
                ),
                photo_count=Count('images', distinct=True),
                min_rate=Min(
                    'units__base_rate_mwk',
                    filter=Q(
                        units__is_public=True,
                        units__is_active=True,
                    ),
                ),
            )
            .filter(available_count__gt=0)
            .order_by('-photo_count', '-available_count', 'name')
            .prefetch_related('images')
            [:6]
        )

        # ── Recent vacant rentals ────────────────────────────────────
        # Newest apartments and houses that are publicly available.
        # Deliberately different from the rent list page (which orders
        # by district for browsing); here we surface "just added".
        ctx['recent_rentals'] = (
            Unit.objects
            .filter(
                is_public=True,
                is_active=True,
                status=Unit.Status.AVAILABLE,
                unit_type__in=[
                    Unit.UnitType.APARTMENT,
                    Unit.UnitType.HOUSE,
                ],
                property__status=Property.Status.ACTIVE,
                property__is_public=True,
            )
            .select_related('property')
            .prefetch_related('images', 'amenities')
            .order_by('-created_at')
            [:6]
        )

        # ── Live stat counts for the hero strip ─────────────────────
        # "Rooms available" counts all bookable unit types across all
        # public, active properties — rooms, chalets, dorm beds.
        ctx['stay_count'] = Unit.objects.filter(
            is_public=True,
            is_active=True,
            unit_type__in=[
                Unit.UnitType.ROOM,
                Unit.UnitType.CHALET,
                Unit.UnitType.BED,
            ],
            property__status=Property.Status.ACTIVE,
            property__is_public=True,
        ).count()

        # "Vacant rentals" is what guests will see on the Rentals tab.
        ctx['rent_count'] = Unit.objects.filter(
            is_public=True,
            is_active=True,
            status=Unit.Status.AVAILABLE,
            unit_type__in=[
                Unit.UnitType.APARTMENT,
                Unit.UnitType.HOUSE,
            ],
            property__status=Property.Status.ACTIVE,
            property__is_public=True,
        ).count()

        return ctx