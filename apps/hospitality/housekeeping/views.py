from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView
from .models import HousekeepingTask


class TaskListView(LoginRequiredMixin, ListView):
    model = HousekeepingTask
    template_name = 'pages/hospitality/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 50

    def get_queryset(self):
        qs = HousekeepingTask.objects.select_related(
            'unit', 'unit__property', 'assigned_to'
        ).exclude(status__in=[
            HousekeepingTask.Status.COMPLETED,
            HousekeepingTask.Status.INSPECTED,
            HousekeepingTask.Status.SKIPPED,
        ]).order_by('priority', 'created_at')

        # Superusers and staff see all; housekeepers see their own
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            qs = qs.filter(assigned_to=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['completed_today'] = HousekeepingTask.objects.filter(
            status__in=[
                HousekeepingTask.Status.COMPLETED,
                HousekeepingTask.Status.INSPECTED,
            ],
        ).count()
        return ctx


class TaskStatusUpdateView(LoginRequiredMixin, View):
    """Quick status transition from the mobile task list."""

    def post(self, request, pk):
        task = get_object_or_404(HousekeepingTask, pk=pk)
        new_status = request.POST.get('status')

        valid_transitions = {
            HousekeepingTask.Status.PENDING: [
                HousekeepingTask.Status.IN_PROGRESS,
                HousekeepingTask.Status.SKIPPED,
            ],
            HousekeepingTask.Status.IN_PROGRESS: [
                HousekeepingTask.Status.COMPLETED,
            ],
            HousekeepingTask.Status.COMPLETED: [
                HousekeepingTask.Status.INSPECTED,
            ],
        }

        allowed = valid_transitions.get(task.status, [])
        if new_status not in allowed:
            messages.error(
                request,
                f'Cannot move from {task.get_status_display()} to that status.',
            )
            return redirect('housekeeping:tasks')

        task.status = new_status
        if new_status == HousekeepingTask.Status.INSPECTED:
            task.inspected_by = request.user
        task.save()

        messages.success(request, f'Task updated to {task.get_status_display()}.')
        return redirect('housekeeping:tasks')