"""
Staff-only views for managing Person records.

All views require authentication and staff status. Data is scoped
to the current tenant schema by django-tenants.
"""
from django.contrib import messages
from django.db.models import Q, Count
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from apps.core.mixins import StaffRequiredMixin
from .models import Person
from .forms import PersonForm


class PersonListView(StaffRequiredMixin, ListView):
    """List all people (guests, tenants, buyers, landlords) in the tenant."""
    model = Person
    template_name = 'pages/people/list.html'
    context_object_name = 'people'
    paginate_by = 25

    def get_queryset(self):
        qs = Person.objects.annotate(
            role_count=Count('property_roles'),
        ).order_by('full_name')

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search) |
                Q(phone_primary__icontains=search) |
                Q(phone_secondary__icontains=search) |
                Q(email__icontains=search) |
                Q(id_number__icontains=search)
            )

        nationality = self.request.GET.get('nationality', '').strip()
        if nationality:
            qs = qs.filter(nationality__iexact=nationality)

        if self.request.GET.get('blacklisted') == '1':
            qs = qs.filter(is_blacklisted=True)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['nationalities'] = (
            Person.objects
            .values_list('nationality', flat=True)
            .distinct()
            .order_by('nationality')
        )
        ctx['current_nationality'] = self.request.GET.get('nationality', '')
        ctx['show_blacklisted'] = self.request.GET.get('blacklisted') == '1'
        ctx['total_people'] = Person.objects.count()
        ctx['blacklisted_count'] = Person.objects.filter(is_blacklisted=True).count()
        return ctx


class PersonDetailView(StaffRequiredMixin, DetailView):
    """View a single person's full profile with their property roles."""
    model = Person
    template_name = 'pages/people/detail.html'
    context_object_name = 'person'

    def get_queryset(self):
        return Person.objects.prefetch_related(
            'property_roles__property',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['roles'] = self.object.property_roles.select_related(
            'property',
        ).order_by('-is_active', '-start_date')
        return ctx


class PersonCreateView(StaffRequiredMixin, CreateView):
    """Register a new person."""
    model = Person
    form_class = PersonForm
    template_name = 'pages/people/form.html'

    def form_valid(self, form):
        messages.success(
            self.request,
            f'{form.instance.full_name} registered successfully.',
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('people:detail', kwargs={'pk': self.object.pk})


class PersonUpdateView(StaffRequiredMixin, UpdateView):
    """Edit an existing person's details."""
    model = Person
    form_class = PersonForm
    template_name = 'pages/people/form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Person details updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('people:detail', kwargs={'pk': self.object.pk})