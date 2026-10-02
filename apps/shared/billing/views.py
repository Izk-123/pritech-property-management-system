"""Billing views - tenant side and platform admin side."""
import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView

from apps.compliance.paychangu.services import PayChanguService
from apps.core.mixins import PlatformAdminRequiredMixin, PublicSchemaOnlyMixin

from .models import (
    Subscription, SubscriptionInvoice, SubscriptionPayment,
    SubscriptionPlan,
)
from .services import change_plan, record_subscription_payment


logger = logging.getLogger(__name__)


class BillingDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'pages/billing/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        subscription = getattr(tenant, 'subscription', None)

        ctx['tenant'] = tenant
        ctx['subscription'] = subscription
        ctx['plans'] = SubscriptionPlan.objects.filter(
            is_active=True, is_public=True,
        ).order_by('display_order', 'price_mwk')

        if subscription:
            ctx['invoices'] = subscription.invoices.order_by('-issue_date')[:10]
            ctx['upcoming_invoice'] = subscription.invoices.filter(
                status__in=[
                    SubscriptionInvoice.Status.ISSUED,
                    SubscriptionInvoice.Status.OVERDUE,
                ],
            ).order_by('due_date').first()
            ctx['payments'] = SubscriptionPayment.objects.filter(
                invoice__subscription=subscription,
            ).order_by('-received_at')[:10]

        return ctx


class PlanListView(LoginRequiredMixin, ListView):
    model = SubscriptionPlan
    template_name = 'pages/billing/plans.html'
    context_object_name = 'plans'

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(
            is_active=True, is_public=True,
        ).order_by('display_order', 'price_mwk')


class ChangePlanView(LoginRequiredMixin, View):
    def post(self, request, plan_id):
        tenant = request.tenant
        subscription = getattr(tenant, 'subscription', None)
        if not subscription:
            messages.error(request, 'No subscription found for this workspace.')
            return redirect('billing:dashboard')

        new_plan = get_object_or_404(
            SubscriptionPlan, pk=plan_id, is_active=True,
        )
        change_plan(subscription, new_plan, performed_by=request.user)
        messages.success(
            request,
            f'Plan changed to {new_plan.name}. '
            f'Your next invoice will reflect the new pricing.',
        )
        return redirect('billing:dashboard')


class PayInvoiceView(LoginRequiredMixin, View):
    def post(self, request, invoice_id):
        invoice = get_object_or_404(
            SubscriptionInvoice, pk=invoice_id, tenant=request.tenant,
        )
        if invoice.status == SubscriptionInvoice.Status.PAID:
            messages.info(request, 'This invoice is already paid.')
            return redirect('billing:dashboard')

        service = PayChanguService()
        callback_url = request.build_absolute_uri(
            reverse('billing:paychangu_callback'),
        )
        return_url = request.build_absolute_uri(
            reverse('billing:dashboard'),
        )

        success, checkout_url, tx_ref = service.initiate_payment(
            amount=invoice.amount,
            currency=invoice.currency,
            email=request.user.email,
            first_name=request.user.first_name or 'Billing',
            last_name=request.user.last_name or 'Contact',
            tx_ref=invoice.invoice_number,
            callback_url=callback_url,
            return_url=return_url,
            title=f'Pritech PMS - {invoice.invoice_number}',
            description=invoice.description,
        )

        if success and checkout_url:
            invoice.paychangu_ref = tx_ref
            invoice.save(update_fields=['paychangu_ref', 'updated_at'])
            return redirect(checkout_url)

        messages.error(request, 'Could not start payment. Please try again.')
        return redirect('billing:dashboard')


class InvoicePDFView(LoginRequiredMixin, View):
    def get(self, request, invoice_id):
        invoice = get_object_or_404(
            SubscriptionInvoice, pk=invoice_id, tenant=request.tenant,
        )
        try:
            from apps.shared.billing.pdf import render_subscription_invoice
            pdf = render_subscription_invoice(invoice)
        except NotImplementedError:
            return HttpResponse(
                'PDF generation not yet implemented.', status=501,
            )
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'inline; filename="{invoice.invoice_number}.pdf"'
        )
        return response


@csrf_exempt
@require_POST
def paychangu_callback(request):
    """Webhook for PayChangu subscription payments."""
    payload = json.loads(request.body or b'{}')
    tx_ref = payload.get('tx_ref')
    status = payload.get('status')
    charge_id = payload.get('charge_id') or tx_ref

    if status != 'successful':
        return JsonResponse({'status': 'ignored'})

    service = PayChanguService()
    is_valid, verification = service.verify_transaction(tx_ref)
    if not is_valid:
        return JsonResponse({'status': 'invalid'}, status=400)

    invoice = SubscriptionInvoice.objects.filter(
        paychangu_ref=tx_ref,
    ).first()
    if not invoice:
        return JsonResponse({'status': 'no-invoice'}, status=404)

    method_map = {
        'airtel': SubscriptionPayment.Method.AIRTEL_MONEY,
        'tnm': SubscriptionPayment.Method.TNM_MPAMBA,
        'card': SubscriptionPayment.Method.CARD,
    }
    method_code = payload.get('payment_method', '').lower()
    method = method_map.get(method_code, SubscriptionPayment.Method.CARD)

    record_subscription_payment(
        invoice=invoice,
        amount=payload.get('amount', invoice.amount),
        method=method,
        reference=tx_ref,
        paychangu_charge_id=charge_id,
        payer_name=payload.get('customer', {}).get('name', ''),
        payer_phone=payload.get('customer', {}).get('phone', ''),
    )
    return JsonResponse({'status': 'ok'})


class AdminSubscriptionListView(
    PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, ListView,
):
    model = Subscription
    template_name = 'pages/billing/admin_list.html'
    context_object_name = 'subscriptions'
    paginate_by = 50

    def get_queryset(self):
        qs = Subscription.objects.select_related('tenant', 'plan').order_by(
            '-updated_at',
        )
        status = self.request.GET.get('status', '')
        if status in Subscription.Status.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = Subscription.Status.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['mrr'] = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
        ).aggregate(
            total=Sum('plan__price_mwk'),
        )['total'] or 0
        ctx['trial_count'] = Subscription.objects.filter(
            status=Subscription.Status.TRIAL,
        ).count()
        ctx['past_due_count'] = Subscription.objects.filter(
            status=Subscription.Status.PAST_DUE,
        ).count()
        return ctx


class AdminMarkPaidView(
    PublicSchemaOnlyMixin, PlatformAdminRequiredMixin, View,
):
    def post(self, request, invoice_id):
        invoice = get_object_or_404(SubscriptionInvoice, pk=invoice_id)
        reference = request.POST.get('reference', '').strip()
        amount = request.POST.get('amount') or invoice.amount
        record_subscription_payment(
            invoice=invoice,
            amount=amount,
            method=SubscriptionPayment.Method.MANUAL,
            reference=reference,
            received_by=request.user,
        )
        messages.success(request, f'Invoice {invoice.invoice_number} marked paid.')
        return redirect('billing_admin:admin_list')
