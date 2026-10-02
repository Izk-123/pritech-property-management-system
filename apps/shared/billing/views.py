"""
Billing views.

Two audiences:
  • Tenant staff — see their own subscription, upgrade, pay
  • Platform admins — see all subscriptions, mark manual payments

Billing lives in the PUBLIC schema (apps.shared.billing), so a
tenant-schema request reaches these views through the tenant URLconf
which mounts them at /billing/. The `request.tenant` is still set by
django-tenants, so we can scope tenant-side views by the current
schema.
"""
import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView

from apps.core.mixins import PlatformAdminRequiredMixin, PublicSchemaOnlyMixin
from apps.compliance.paychangu.services import PayChanguService

from .models import (
    Subscription, SubscriptionChange, SubscriptionInvoice,
    SubscriptionPayment, SubscriptionPlan,
)
from .services import (
    cancel_subscription, change_plan, record_subscription_payment,
)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Tenant-side views
# ─────────────────────────────────────────────────────────────────────

class BillingDashboardView(LoginRequiredMixin, TemplateView):
    """
    The tenant's billing home.

    Shows:
      • Current plan, status, and renewal date
      • Any outstanding invoice with a Pay Now button
      • Recent invoices and payments
      • Link to the plan catalogue
    """
    template_name = 'pages/billing/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        subscription = getattr(tenant, 'subscription', None)

        ctx['tenant'] = tenant
        ctx['subscription'] = subscription

        if subscription:
            ctx['invoices'] = (
                subscription.invoices
                .select_related('plan')
                .order_by('-issue_date')[:10]
            )
            ctx['upcoming_invoice'] = (
                subscription.invoices
                .filter(status__in=[
                    SubscriptionInvoice.Status.ISSUED,
                    SubscriptionInvoice.Status.OVERDUE,
                ])
                .order_by('due_date')
                .first()
            )
            ctx['payments'] = (
                SubscriptionPayment.objects
                .filter(invoice__subscription=subscription)
                .order_by('-received_at')[:10]
            )
            ctx['plan_changes'] = (
                subscription.changes
                .select_related('from_plan', 'to_plan')
                .order_by('-created_at')[:5]
            )

        return ctx


class PlanListView(LoginRequiredMixin, ListView):
    """
    Plan catalogue. Shows all active, public plans with pricing and
    feature comparison. Each plan has a "Switch to this plan" button.
    """
    model = SubscriptionPlan
    template_name = 'pages/billing/plans.html'
    context_object_name = 'plans'

    def get_queryset(self):
        return (
            SubscriptionPlan.objects
            .filter(is_active=True, is_public=True)
            .order_by('display_order', 'price_mwk')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.request.tenant
        ctx['tenant'] = tenant
        ctx['subscription'] = getattr(tenant, 'subscription', None)
        return ctx


class ChangePlanView(LoginRequiredMixin, View):
    """
    Handle POST from the plans page. Validates the target plan,
    calls the change service, and redirects back to the dashboard.
    """

    def post(self, request, plan_id):
        tenant = request.tenant
        subscription = getattr(tenant, 'subscription', None)

        if not subscription:
            messages.error(
                request,
                'No subscription found for this workspace. '
                'Please contact support.',
            )
            return redirect('billing:dashboard')

        new_plan = get_object_or_404(
            SubscriptionPlan, pk=plan_id, is_active=True, is_public=True,
        )

        if new_plan.pk == subscription.plan.pk:
            messages.info(request, 'You are already on this plan.')
            return redirect('billing:plans')

        old_plan = subscription.plan
        change_plan(subscription, new_plan, performed_by=request.user)

        direction = (
            'upgraded' if new_plan.price_mwk > old_plan.price_mwk
            else 'changed'
        )
        messages.success(
            request,
            f'Plan {direction} from {old_plan.name} to {new_plan.name}. '
            f'Your next invoice will reflect the new pricing.',
        )
        return redirect('billing:dashboard')


class CancelSubscriptionView(LoginRequiredMixin, View):
    """
    Cancel at end of current period. Tenant keeps access until then.
    Requires confirmation via the billing dashboard form.
    """

    def post(self, request):
        subscription = getattr(request.tenant, 'subscription', None)
        if not subscription:
            messages.error(request, 'No subscription to cancel.')
            return redirect('billing:dashboard')

        if subscription.status == Subscription.Status.CANCELLED:
            messages.info(request, 'This subscription is already cancelled.')
            return redirect('billing:dashboard')

        reason = request.POST.get('reason', '').strip()
        cancel_subscription(subscription, performed_by=request.user, note=reason)

        messages.warning(
            request,
            'Subscription cancelled. You will keep access until '
            f'{subscription.current_period_end:%d %b %Y}.',
        )
        return redirect('billing:dashboard')


class PayInvoiceView(LoginRequiredMixin, View):
    """
    Initiate a PayChangu transaction for an invoice and redirect the
    user to the hosted checkout page.
    """

    def post(self, request, invoice_id):
        invoice = get_object_or_404(
            SubscriptionInvoice,
            pk=invoice_id,
            tenant=request.tenant,
        )

        if invoice.status == SubscriptionInvoice.Status.PAID:
            messages.info(request, 'This invoice is already paid.')
            return redirect('billing:dashboard')

        if invoice.status == SubscriptionInvoice.Status.VOID:
            messages.error(request, 'This invoice has been voided.')
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
            title=f'Pritech PMS — {invoice.invoice_number}',
            description=invoice.description,
        )

        if success and checkout_url:
            invoice.paychangu_ref = tx_ref
            invoice.save(update_fields=['paychangu_ref', 'updated_at'])
            logger.info(
                f'PayChangu checkout initiated for {invoice.invoice_number} '
                f'(ref={tx_ref})'
            )
            return redirect(checkout_url)

        logger.error(
            f'PayChangu initiation failed for {invoice.invoice_number}'
        )
        messages.error(
            request,
            'Could not start payment. Please check your internet '
            'connection and try again, or contact support.',
        )
        return redirect('billing:dashboard')


class InvoicePDFView(LoginRequiredMixin, View):
    """Serve a subscription invoice as a PDF."""

    def get(self, request, invoice_id):
        invoice = get_object_or_404(
            SubscriptionInvoice,
            pk=invoice_id,
            tenant=request.tenant,
        )

        from apps.shared.billing.pdf import render_subscription_invoice
        pdf_bytes = render_subscription_invoice(invoice)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        disposition = (
            'attachment' if request.GET.get('download') == '1' else 'inline'
        )
        response['Content-Disposition'] = (
            f'{disposition}; filename="{invoice.invoice_number}.pdf"'
        )
        response['Cache-Control'] = 'private, no-store'
        return response


# ─────────────────────────────────────────────────────────────────────
# PayChangu webhook
# ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def paychangu_callback(request):
    """
    Webhook endpoint for PayChangu subscription payments.

    Steps:
      1. Parse the payload.
      2. Verify with PayChangu server-side (never trust the payload alone).
      3. Find the invoice by tx_ref.
      4. Record the payment idempotently.
    """
    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'bad-json'}, status=400)

    tx_ref = payload.get('tx_ref')
    status = payload.get('status')
    charge_id = payload.get('charge_id') or tx_ref

    if not tx_ref:
        return JsonResponse({'status': 'missing-tx-ref'}, status=400)

    if status != 'successful':
        logger.info(f'PayChangu webhook ignored (status={status})')
        return JsonResponse({'status': 'ignored'})

    # Server-side verification — never trust the payload alone
    service = PayChanguService()
    is_valid, verification = service.verify_transaction(tx_ref)
    if not is_valid:
        logger.warning(f'PayChangu verification failed for {tx_ref}')
        return JsonResponse({'status': 'invalid'}, status=400)

    invoice = SubscriptionInvoice.objects.filter(paychangu_ref=tx_ref).first()
    if not invoice:
        logger.warning(f'No invoice found for tx_ref={tx_ref}')
        return JsonResponse({'status': 'no-invoice'}, status=404)

    method_map = {
        'airtel': SubscriptionPayment.Method.AIRTEL_MONEY,
        'tnm': SubscriptionPayment.Method.TNM_MPAMBA,
        'card': SubscriptionPayment.Method.CARD,
        'bank': SubscriptionPayment.Method.BANK_TRANSFER,
    }
    method_code = (payload.get('payment_method') or '').lower()
    method = method_map.get(method_code, SubscriptionPayment.Method.CARD)

    customer = payload.get('customer', {}) or {}

    payment = record_subscription_payment(
        invoice=invoice,
        amount=payload.get('amount', invoice.amount),
        method=method,
        reference=tx_ref,
        paychangu_charge_id=charge_id,
        payer_name=customer.get('name', ''),
        payer_phone=customer.get('phone', ''),
    )
    logger.info(
        f'Subscription payment recorded: {invoice.invoice_number} '
        f'({payment.amount} {invoice.currency})'
    )
    return JsonResponse({'status': 'ok'})


# ─────────────────────────────────────────────────────────────────────
# Platform-admin views
# ─────────────────────────────────────────────────────────────────────

class AdminSubscriptionListView(
    PublicSchemaOnlyMixin,
    PlatformAdminRequiredMixin,
    ListView,
):
    """
    All tenant subscriptions with MRR, trial count, and delinquent count.
    Only reachable from the public schema.
    """
    model = Subscription
    template_name = 'pages/billing/admin_list.html'
    context_object_name = 'subscriptions'
    paginate_by = 50

    def get_queryset(self):
        qs = (
            Subscription.objects
            .select_related('tenant', 'plan')
            .order_by('-updated_at')
        )

        status = self.request.GET.get('status', '')
        if status in Subscription.Status.values:
            qs = qs.filter(status=status)

        search = self.request.GET.get('q', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(tenant__name__icontains=search) |
                Q(tenant__schema_name__icontains=search) |
                Q(tenant__contact_email__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # MRR — monthly recurring revenue across ACTIVE subscriptions
        active = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
        )
        mrr = sum(
            sub.plan.monthly_equivalent_mwk
            for sub in active.select_related('plan')
        )
        ctx['mrr'] = mrr
        ctx['arr'] = mrr * 12

        ctx['trial_count'] = Subscription.objects.filter(
            status=Subscription.Status.TRIAL,
        ).count()
        ctx['past_due_count'] = Subscription.objects.filter(
            status=Subscription.Status.PAST_DUE,
        ).count()
        ctx['suspended_count'] = Subscription.objects.filter(
            status=Subscription.Status.SUSPENDED,
        ).count()

        ctx['statuses'] = Subscription.Status.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['search_query'] = self.request.GET.get('q', '')

        return ctx


class AdminSubscriptionDetailView(
    PublicSchemaOnlyMixin,
    PlatformAdminRequiredMixin,
    TemplateView,
):
    """A single tenant's billing history — platform admin only."""
    template_name = 'pages/billing/admin_detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        subscription = get_object_or_404(
            Subscription.objects.select_related('tenant', 'plan'),
            pk=self.kwargs['pk'],
        )
        ctx['subscription'] = subscription
        ctx['tenant'] = subscription.tenant
        ctx['invoices'] = subscription.invoices.order_by('-issue_date')
        ctx['payments'] = (
            SubscriptionPayment.objects
            .filter(invoice__subscription=subscription)
            .order_by('-received_at')
        )
        ctx['changes'] = subscription.changes.order_by('-created_at')
        return ctx


class AdminMarkPaidView(
    PublicSchemaOnlyMixin,
    PlatformAdminRequiredMixin,
    View,
):
    """
    Manually mark an invoice as paid. Used when a tenant pays by bank
    transfer or cash and doesn't go through PayChangu.
    """

    def post(self, request, invoice_id):
        invoice = get_object_or_404(SubscriptionInvoice, pk=invoice_id)
        reference = request.POST.get('reference', '').strip()
        amount = request.POST.get('amount') or invoice.amount

        try:
            record_subscription_payment(
                invoice=invoice,
                amount=amount,
                method=SubscriptionPayment.Method.MANUAL,
                reference=reference,
                received_by=request.user,
            )
            messages.success(
                request,
                f'Invoice {invoice.invoice_number} marked as paid '
                f'({invoice.currency} {amount}).',
            )
        except Exception as exc:
            logger.exception(f'Manual payment failed: {exc}')
            messages.error(request, f'Payment failed: {exc}')

        return redirect('billing_admin:admin_detail', pk=invoice.subscription.pk)


class AdminExtendTrialView(
    PublicSchemaOnlyMixin,
    PlatformAdminRequiredMixin,
    View,
):
    """Extend a trial by N days. Used for sales negotiations."""

    def post(self, request, pk):
        subscription = get_object_or_404(Subscription, pk=pk)
        days = int(request.POST.get('days', 7))
        note = request.POST.get('note', '').strip()

        if subscription.status != Subscription.Status.TRIAL:
            messages.error(
                request,
                'Only trial subscriptions can be extended.',
            )
            return redirect('billing_admin:admin_detail', pk=pk)

        if subscription.trial_ends_at:
            subscription.trial_ends_at = (
                subscription.trial_ends_at + timezone.timedelta(days=days)
            )
        else:
            subscription.trial_ends_at = timezone.now() + timezone.timedelta(days=days)
        subscription.save(update_fields=['trial_ends_at', 'updated_at'])

        SubscriptionChange.objects.create(
            subscription=subscription,
            kind=SubscriptionChange.Kind.TRIAL_EXTENDED,
            note=note or f'Trial extended by {days} days',
            performed_by=request.user,
        )
        messages.success(request, f'Trial extended by {days} days.')
        return redirect('billing_admin:admin_detail', pk=pk)