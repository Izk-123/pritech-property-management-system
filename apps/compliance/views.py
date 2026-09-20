from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.utils import timezone
from django.db.models import Sum, Count
from .eis.models import EISTerminal, EISInvoiceLog
from .paychangu.models import PayChanguTransaction
from .tourism_levy.models import TourismLevyRecord
from .forex.models import ForexRate
from .fcy.models import RBMReturn


class ComplianceDashboardView(LoginRequiredMixin, TemplateView):
    """Overview of all compliance surfaces."""

    template_name = 'pages/compliance/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.now().date()
        current_month = today.replace(day=1)

        # EIS
        ctx['eis_terminals'] = EISTerminal.objects.count()
        ctx['eis_offline_queued'] = EISInvoiceLog.objects.filter(
            submission_status__in=['OFFQ', 'FAIL', 'PEND']
        ).count()
        ctx['eis_validated_this_month'] = EISInvoiceLog.objects.filter(
            submission_status='VAL',
            created_at__gte=current_month,
        ).count()

        # PayChangu
        today_qs = PayChanguTransaction.objects.filter(
            created_at__date=today,
            status='SUCC',
        )
        ctx['paychangu_today_total'] = (
            today_qs.aggregate(t=Sum('amount'))['t'] or 0
        )
        ctx['paychangu_today_count'] = today_qs.count()

        # Tourism Levy
        ctx['levy_this_month'] = TourismLevyRecord.objects.filter(
            period_month=current_month,
        ).aggregate(t=Sum('levy_amount'))['t'] or 0
        ctx['levy_pending_remittance'] = TourismLevyRecord.objects.filter(
            is_remitted=False,
        ).count()

        # Forex
        ctx['usd_rate'] = ForexRate.get_current_rate('USD')
        ctx['eur_rate'] = ForexRate.get_current_rate('EUR')

        # RBM
        ctx['rbm_pending'] = RBMReturn.objects.filter(
            submitted_to_rbm=False,
        ).count()

        return ctx