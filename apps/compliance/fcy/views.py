from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView
from django.views import View
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from .models import FCYBankAccount, RBMReturn
from .services import generate_rbm_return


class FCYDashboardView(LoginRequiredMixin, ListView):
    """Dashboard showing FCY bank accounts and recent RBM returns."""
    model = FCYBankAccount
    template_name = 'pages/compliance/fcy_dashboard.html'
    context_object_name = 'accounts'

    def get_queryset(self):
        return FCYBankAccount.objects.filter(
            is_active=True
        ).select_related('property').order_by(
            'property__name', 'bank_name'
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['recent_returns'] = RBMReturn.objects.select_related(
            'property'
        ).order_by('-return_month')[:12]

        # Current month stats
        today = timezone.now().date()
        current_month = today.replace(day=1)
        ctx['current_month_summary'] = RBMReturn.objects.filter(
            return_month=current_month,
        ).aggregate(
            total=Sum('total_receipts'),
            count=Count('id'),
        )
        return ctx


class RBMReturnListView(LoginRequiredMixin, ListView):
    model = RBMReturn
    template_name = 'pages/compliance/rbm_return_list.html'
    context_object_name = 'returns'
    paginate_by = 25

    def get_queryset(self):
        qs = RBMReturn.objects.select_related('property').order_by(
            '-return_month', 'property__name'
        )

        month = self.request.GET.get('month', '')
        if month:
            try:
                year, m = month.split('-')
                qs = qs.filter(
                    return_month__year=int(year),
                    return_month__month=int(m),
                )
            except (ValueError, AttributeError):
                pass

        currency = self.request.GET.get('currency', '')
        if currency in ['USD', 'EUR']:
            qs = qs.filter(currency=currency)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['currencies'] = ['USD', 'EUR']
        ctx['current_month'] = self.request.GET.get('month', '')
        ctx['current_currency'] = self.request.GET.get('currency', '')
        return ctx


class RBMReturnGenerateView(LoginRequiredMixin, View):
    """Manually generate RBM returns for the previous month."""

    def post(self, request):
        today = timezone.now().date()
        last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

        from apps.core.properties.models import Property
        properties = Property.objects.filter(status='ACTIVE')
        total = 0
        for prop in properties:
            returns = generate_rbm_return(prop.id, last_month)
            total += len(returns)

        messages.success(
            request,
            f'Generated {total} RBM returns for {last_month.strftime("%B %Y")}.',
        )
        return redirect('compliance:fcy:rbm_return_list')


class RBMReturnMarkSubmittedView(LoginRequiredMixin, View):
    """Mark an RBM return as submitted."""

    def post(self, request, pk):
        rbm_return = get_object_or_404(RBMReturn, pk=pk)
        rbm_return.submitted_to_rbm = True
        rbm_return.submitted_at = timezone.now()
        rbm_return.save(
            update_fields=['submitted_to_rbm', 'submitted_at', 'updated_at']
        )
        messages.success(request, 'Return marked as submitted to RBM.')
        return redirect('compliance:fcy:rbm_return_list')