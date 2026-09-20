"""
Public property browsing views.

PropertyListView and PropertyDetailView are available to anonymous
visitors browsing the tenant's public listings. Data is automatically
scoped to the current tenant schema by django-tenants.
"""
from django.db.models import Count, Prefetch, Q
from django.views.generic import ListView, DetailView
from .models import Property, Unit


class PropertyListView(ListView):
    """
    Public list of active properties with search and filtering.
    Mobile-first, paginated, dark-mode aware.
    """
    model = Property
    template_name = 'pages/properties/list.html'
    context_object_name = 'properties'
    paginate_by = 12

    def get_queryset(self):
        qs = (
            Property.objects
            .filter(status=Property.Status.ACTIVE)
            .annotate(
                unit_count=Count('units', filter=Q(units__is_active=True)),
                available_count=Count(
                    'units',
                    filter=Q(
                        units__is_active=True,
                        units__status=Unit.Status.AVAILABLE,
                    ),
                ),
            )
            .order_by('name')
        )

        # Search: name, district, description
        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(district__icontains=search) |
                Q(description__icontains=search)
            )

        # Filter by property type
        property_type = self.request.GET.get('type', '').strip()
        if property_type in Property.PropertyType.values:
            qs = qs.filter(property_type=property_type)

        # Filter by region
        region = self.request.GET.get('region', '').strip()
        if region in Property.Region.values:
            qs = qs.filter(region=region)

        # Filter by district
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
            .filter(status=Property.Status.ACTIVE)
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
    Public detail view of a single property with its units.
    """
    model = Property
    template_name = 'pages/properties/detail.html'
    context_object_name = 'property'

    def get_queryset(self):
        return (
            Property.objects
            .filter(status=Property.Status.ACTIVE)
            .prefetch_related(
                Prefetch(
                    'units',
                    queryset=Unit.objects
                        .filter(is_active=True)
                        .prefetch_related('amenities')
                        .order_by('identifier'),
                    to_attr='active_units',
                )
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