from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, FormView,
)
from django.views import View
from django.db.models import Q
from django.utils import timezone
from .models import MaintenanceRequest
from .forms import (
    MaintenanceRequestForm, MaintenanceAssignForm, MaintenanceCompleteForm,
)


class MaintenanceListView(LoginRequiredMixin, ListView):
    model = MaintenanceRequest
    template_name = 'pages/property/maintenance_list.html'
    context_object_name = 'requests'
    paginate_by = 25

    def get_queryset(self):
        qs = MaintenanceRequest.objects.select_related(
            'unit', 'unit__property', 'assigned_to', 'submitted_by'
        ).order_by('-created_at')

        status = self.request.GET.get('status', '')
        if status in MaintenanceRequest.Status.values:
            qs = qs.filter(status=status)

        priority = self.request.GET.get('priority', '')
        if priority in MaintenanceRequest.Priority.values:
            qs = qs.filter(priority=priority)

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(unit__identifier__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = MaintenanceRequest.Status.choices
        ctx['priorities'] = MaintenanceRequest.Priority.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['current_priority'] = self.request.GET.get('priority', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class MaintenanceDetailView(LoginRequiredMixin, DetailView):
    model = MaintenanceRequest
    template_name = 'pages/property/maintenance_detail.html'
    context_object_name = 'request'

    def get_queryset(self):
        return MaintenanceRequest.objects.select_related(
            'unit', 'unit__property', 'assigned_to', 'submitted_by'
        )


class MaintenanceCreateView(LoginRequiredMixin, CreateView):
    model = MaintenanceRequest
    form_class = MaintenanceRequestForm
    template_name = 'pages/property/maintenance_form.html'

    def form_valid(self, form):
        form.instance.submitted_by = self.request.user.person if hasattr(
            self.request.user, 'person'
        ) else None
        messages.success(self.request, 'Maintenance request logged.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('property:maintenance:detail',
                            kwargs={'pk': self.object.pk})


class MaintenanceAssignView(LoginRequiredMixin, UpdateView):
    model = MaintenanceRequest
    form_class = MaintenanceAssignForm
    template_name = 'pages/property/maintenance_assign.html'

    def form_valid(self, form):
        form.instance.status = MaintenanceRequest.Status.ACKNOWLEDGED
        messages.success(self.request, 'Maintenance request assigned.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('property:maintenance:detail',
                            kwargs={'pk': self.object.pk})


class MaintenanceCompleteView(LoginRequiredMixin, UpdateView):
    model = MaintenanceRequest
    form_class = MaintenanceCompleteForm
    template_name = 'pages/property/maintenance_complete.html'

    def get_queryset(self):
        return MaintenanceRequest.objects.filter(
            status__in=[
                MaintenanceRequest.Status.ACKNOWLEDGED,
                MaintenanceRequest.Status.IN_PROGRESS,
            ]
        )

    def form_valid(self, form):
        form.instance.status = MaintenanceRequest.Status.COMPLETED
        messages.success(self.request, 'Maintenance request completed.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('property:maintenance:detail',
                            kwargs={'pk': self.object.pk})


class MaintenanceStatusUpdateView(LoginRequiredMixin, View):
    """Quick status transition for the mobile task list."""

    def post(self, request, pk):
        req = get_object_or_404(MaintenanceRequest, pk=pk)
        new_status = request.POST.get('status')

        valid_transitions = {
            MaintenanceRequest.Status.SUBMITTED: [
                MaintenanceRequest.Status.ACKNOWLEDGED,
                MaintenanceRequest.Status.CANCELLED,
            ],
            MaintenanceRequest.Status.ACKNOWLEDGED: [
                MaintenanceRequest.Status.IN_PROGRESS,
                MaintenanceRequest.Status.CANCELLED,
            ],
            MaintenanceRequest.Status.IN_PROGRESS: [
                MaintenanceRequest.Status.COMPLETED,
            ],
            MaintenanceRequest.Status.COMPLETED: [
                MaintenanceRequest.Status.VERIFIED,
            ],
        }

        allowed = valid_transitions.get(req.status, [])
        if new_status not in allowed:
            messages.error(
                request,
                f'Cannot move from {req.get_status_display()} to that status.',
            )
            return redirect('property:maintenance:list')

        req.status = new_status
        req.save()

        messages.success(request, f'Request updated to {req.get_status_display()}.')
        return redirect('property:maintenance:detail', pk=pk)