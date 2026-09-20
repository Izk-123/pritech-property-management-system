from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic import ListView
from .models import ForexRate
from .tasks import fetch_forex_rates


class ForexRateListView(LoginRequiredMixin, ListView):
    model = ForexRate
    template_name = 'pages/compliance/forex_rate_list.html'
    context_object_name = 'rates'
    paginate_by = 50

    def get_queryset(self):
        qs = ForexRate.objects.order_by('-effective_from')

        currency = self.request.GET.get('currency', '')
        if currency in ['USD', 'EUR']:
            qs = qs.filter(quote_currency=currency)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['currencies'] = ['USD', 'EUR']
        ctx['current_currency'] = self.request.GET.get('currency', '')
        ctx['current_rates'] = {
            'USD': ForexRate.get_current_rate('USD'),
            'EUR': ForexRate.get_current_rate('EUR'),
        }
        return ctx


class ForexRefreshView(LoginRequiredMixin, View):
    """Trigger a manual forex rate refresh."""

    def post(self, request):
        fetch_forex_rates.delay()
        messages.info(
            request,
            'Forex rate refresh queued. New rates will appear shortly.',
        )
        return redirect('compliance:forex:rate_list')