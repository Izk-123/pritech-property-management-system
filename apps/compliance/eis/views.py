from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView
from django.views import View
from django.db.models import Q, Count
from django.utils import timezone
from .models import EISTerminal, EISInvoiceLog, EISProductMapping
from .services import EISClient
from .tasks import sync_all_terminal_configs


class EISTerminalListView(LoginRequiredMixin, ListView):
    model = EISTerminal
    template_name = 'pages/compliance/eis_terminal_list.html'
    context_object_name = 'terminals'

    def get_queryset(self):
        return EISTerminal.objects.select_related('property').order_by(
            'property__name', 'terminal_code',
        )


class EISTerminalDetailView(LoginRequiredMixin, DetailView):
    model = EISTerminal
    template_name = 'pages/compliance/eis_terminal_detail.html'
    context_object_name = 'terminal'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['recent_logs'] = self.object.invoice_logs.order_by(
            '-created_at'
        )[:20]
        ctx['stats'] = {
            'validated': self.object.invoice_logs.filter(
                submission_status='VAL'
            ).count(),
            'offline_queued': self.object.invoice_logs.filter(
                submission_status='OFFQ'
            ).count(),
            'failed': self.object.invoice_logs.filter(
                submission_status='FAIL'
            ).count(),
        }
        return ctx


class EISTerminalSyncView(LoginRequiredMixin, View):
    """Trigger a config sync for one terminal."""

    def post(self, request, pk):
        terminal = get_object_or_404(EISTerminal, pk=pk)
        client = EISClient(terminal)
        if client.sync_configuration():
            messages.success(request, 'Terminal configuration synced.')
        else:
            messages.error(request, 'Sync failed. Check MRA credentials.')
        return redirect('compliance:eis:terminal_detail', pk=pk)


class EISTerminalPingView(LoginRequiredMixin, View):
    """Ping MRA EIS API to test connectivity."""

    def post(self, request, pk):
        terminal = get_object_or_404(EISTerminal, pk=pk)
        client = EISClient(terminal)
        if client.ping():
            messages.success(request, 'MRA EIS API is reachable.')
        else:
            messages.error(request, 'MRA EIS API is unreachable.')
        return redirect('compliance:eis:terminal_detail', pk=pk)


class EISInvoiceLogListView(LoginRequiredMixin, ListView):
    model = EISInvoiceLog
    template_name = 'pages/compliance/eis_invoice_log_list.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        qs = EISInvoiceLog.objects.select_related(
            'terminal', 'terminal__property'
        ).order_by('-created_at')

        status = self.request.GET.get('status', '')
        if status in EISInvoiceLog.SubmissionStatus.values:
            qs = qs.filter(submission_status=status)

        terminal_id = self.request.GET.get('terminal', '')
        if terminal_id.isdigit():
            qs = qs.filter(terminal_id=terminal_id)

        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(invoice_number__icontains=search) |
                Q(mra_invoice_number__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = EISInvoiceLog.SubmissionStatus.choices
        ctx['terminals'] = EISTerminal.objects.select_related('property')
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['current_terminal'] = self.request.GET.get('terminal', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class EISOfflineQueueView(LoginRequiredMixin, ListView):
    """Invoices waiting to sync to MRA EIS."""

    model = EISInvoiceLog
    template_name = 'pages/compliance/eis_offline_queue.html'
    context_object_name = 'queued_logs'

    def get_queryset(self):
        return EISInvoiceLog.objects.filter(
            submission_status__in=['OFFQ', 'PEND', 'FAIL']
        ).select_related('terminal', 'terminal__property').order_by(
            'created_at'
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Use self.object_list — this is what ListView populates
        # from get_queryset() before calling get_context_data()
        ctx['failed_count'] = self.object_list.filter(
            submission_status='FAIL'
        ).count()
        ctx['queued_count'] = self.object_list.filter(
            submission_status='OFFQ'
        ).count()
        return ctx


class EISForceSyncView(LoginRequiredMixin, View):
    """Manually trigger offline invoice sync."""

    def post(self, request):
        from .tasks import sync_offline_eis_invoices
        result = sync_offline_eis_invoices.delay()
        messages.info(
            request,
            'Offline invoice sync queued. Check back in a minute.',
        )
        return redirect('compliance:eis:offline_queue')


class EISProductMappingListView(LoginRequiredMixin, ListView):
    model = EISProductMapping
    template_name = 'pages/compliance/eis_product_list.html'
    context_object_name = 'products'

    def get_queryset(self):
        return EISProductMapping.objects.select_related(
            'property'
        ).order_by('property__name', 'internal_code')