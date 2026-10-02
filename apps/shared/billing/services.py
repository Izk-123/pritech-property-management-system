"""
Billing services — all the business logic in one place so views and
tasks stay thin.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from .models import (
    Subscription, SubscriptionChange, SubscriptionInvoice,
    SubscriptionPayment, SubscriptionPlan,
)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Subscription lifecycle
# ─────────────────────────────────────────────────────────────────────

@transaction.atomic
def start_trial(tenant, plan=None):
    """
    Called from provision_tenant() right after a tenant is created.
    If no plan is given, default to the first public Starter plan.
    """
    if plan is None:
        plan = SubscriptionPlan.objects.filter(
            tier=SubscriptionPlan.Tier.STARTER,
            is_active=True, is_public=True,
        ).order_by('price_mwk').first()

    if plan is None:
        logger.error(f'No Starter plan configured — cannot start trial for {tenant.schema_name}')
        return None

    now = timezone.now()
    subscription = Subscription.objects.create(
        tenant=tenant,
        plan=plan,
        status=Subscription.Status.TRIAL,
        trial_started_at=now,
        trial_ends_at=now + timedelta(days=plan.trial_days),
        current_period_start=now,
        current_period_end=now + timedelta(days=plan.trial_days),
        billing_email=tenant.contact_email,
        billing_phone=tenant.contact_phone,
        preferred_currency='MWK',
    )

    SubscriptionChange.objects.create(
        subscription=subscription,
        kind=SubscriptionChange.Kind.CREATED,
        to_plan=plan,
        note=f'{plan.trial_days}-day free trial started',
    )

    logger.info(
        f'Started trial for {tenant.schema_name} on {plan.name} '
        f'(ends {subscription.trial_ends_at:%Y-%m-%d})'
    )
    return subscription


@transaction.atomic
def activate_subscription(subscription):
    """Convert a trial to a paid active subscription."""
    now = timezone.now()
    subscription.status = Subscription.Status.ACTIVE
    subscription.current_period_start = now
    subscription.current_period_end = _next_period_end(now, subscription.plan)
    subscription.save()

    SubscriptionChange.objects.create(
        subscription=subscription,
        kind=SubscriptionChange.Kind.CREATED,
        note='Trial converted to active subscription',
    )


@transaction.atomic
def change_plan(subscription, new_plan, performed_by=None):
    """
    Upgrade or downgrade. Takes effect immediately. Any unpaid current
    invoice is voided; a new prorated invoice can be generated if
    needed (kept simple: current period is not prorated).
    """
    old_plan = subscription.plan
    if old_plan == new_plan:
        return subscription

    kind = (
        SubscriptionChange.Kind.UPGRADED
        if new_plan.price_mwk > old_plan.price_mwk
        else SubscriptionChange.Kind.DOWNGRADED
    )

    subscription.plan = new_plan
    subscription.save(update_fields=['plan', 'updated_at'])

    SubscriptionChange.objects.create(
        subscription=subscription,
        kind=kind,
        from_plan=old_plan,
        to_plan=new_plan,
        performed_by=performed_by,
    )

    # Void any unpaid draft/issued invoices so the tenant doesn't
    # get charged twice.
    subscription.invoices.filter(
        status__in=[
            SubscriptionInvoice.Status.DRAFT,
            SubscriptionInvoice.Status.ISSUED,
        ],
    ).update(status=SubscriptionInvoice.Status.VOID)

    logger.info(
        f'Plan changed for {subscription.tenant.schema_name}: '
        f'{old_plan.name} → {new_plan.name}'
    )
    return subscription


@transaction.atomic
def cancel_subscription(subscription, performed_by=None, note=''):
    """
    Cancel at end of current period. Tenant keeps access until then.
    """
    subscription.status = Subscription.Status.CANCELLED
    subscription.cancelled_at = timezone.now()
    subscription.save()

    SubscriptionChange.objects.create(
        subscription=subscription,
        kind=SubscriptionChange.Kind.CANCELLED,
        performed_by=performed_by,
        note=note or 'Cancelled by user',
    )


@transaction.atomic
def suspend_subscription(subscription, reason='Non-payment'):
    """Called by a Celery task when an invoice is too far overdue."""
    subscription.status = Subscription.Status.SUSPENDED
    subscription.suspended_at = timezone.now()
    subscription.save()

    # Also deactivate the tenant so no requests get through
    tenant = subscription.tenant
    tenant.is_active = False
    tenant.save(update_fields=['is_active'])

    SubscriptionChange.objects.create(
        subscription=subscription,
        kind=SubscriptionChange.Kind.SUSPENDED,
        note=reason,
    )
    logger.warning(
        f'Suspended {subscription.tenant.schema_name}: {reason}'
    )


@transaction.atomic
def reactivate_subscription(subscription, performed_by=None):
    """Reverse a suspension."""
    subscription.status = Subscription.Status.ACTIVE
    subscription.suspended_at = None
    subscription.consecutive_failed_payments = 0
    subscription.save()

    tenant = subscription.tenant
    tenant.is_active = True
    tenant.save(update_fields=['is_active'])

    SubscriptionChange.objects.create(
        subscription=subscription,
        kind=SubscriptionChange.Kind.REACTIVATED,
        performed_by=performed_by,
    )


# ─────────────────────────────────────────────────────────────────────
# Invoice generation
# ─────────────────────────────────────────────────────────────────────

def _next_period_end(start, plan):
    if plan.interval == SubscriptionPlan.Interval.ANNUAL:
        return start + relativedelta(years=1)
    return start + relativedelta(months=1)


@transaction.atomic
def generate_invoice_for_subscription(subscription, period_start=None,
                                       period_end=None, due_date=None):
    """
    Generate a SubscriptionInvoice. Idempotent per (subscription, period_start).

    Default behavior:
      • period_start = end of last period, or now
      • period_end   = +1 month or +1 year based on plan interval
      • due_date     = 7 days from issue_date (or immediately for trials
                       about to expire)
    """
    plan = subscription.plan
    now = timezone.now()
    period_start = period_start or subscription.current_period_end or now
    period_end = period_end or _next_period_end(period_start, plan)
    due_date = due_date or (now.date() + timedelta(days=7))

    # Idempotency: skip if an unpaid invoice already exists for this period
    existing = subscription.invoices.filter(
        period_start=period_start.date() if hasattr(period_start, 'date') else period_start,
        status__in=[
            SubscriptionInvoice.Status.DRAFT,
            SubscriptionInvoice.Status.ISSUED,
        ],
    ).first()
    if existing:
        return existing

    currency = subscription.preferred_currency
    amount = plan.price_usd if currency == 'USD' and plan.price_usd else plan.price_mwk

    invoice = SubscriptionInvoice.objects.create(
        subscription=subscription,
        tenant=subscription.tenant,
        plan=plan,
        period_start=period_start.date() if hasattr(period_start, 'date') else period_start,
        period_end=period_end.date() if hasattr(period_end, 'date') else period_end,
        due_date=due_date,
        amount=amount,
        currency=currency,
        description=f'{plan.name} · {plan.get_interval_display()} subscription',
        status=SubscriptionInvoice.Status.ISSUED,
    )
    logger.info(f'Generated {invoice.invoice_number} for {subscription.tenant.schema_name}')
    return invoice


# ─────────────────────────────────────────────────────────────────────
# Payment application
# ─────────────────────────────────────────────────────────────────────

@transaction.atomic
def record_subscription_payment(invoice, amount, method, reference='',
                                paychangu_charge_id='', payer_name='',
                                payer_phone='', received_by=None):
    """
    Idempotent. Called by the PayChangu webhook, by a manual admin
    action, or by a Celery task. Returns the SubscriptionPayment.
    """
    # Idempotency: same charge ID should only create one payment
    if paychangu_charge_id:
        existing = SubscriptionPayment.objects.filter(
            paychangu_charge_id=paychangu_charge_id,
        ).first()
        if existing:
            return existing

    amount = Decimal(amount)
    payment = SubscriptionPayment.objects.create(
        invoice=invoice,
        amount=amount,
        currency=invoice.currency,
        method=method,
        reference=reference,
        paychangu_charge_id=paychangu_charge_id,
        payer_name=payer_name,
        payer_phone=payer_phone,
        received_by=received_by,
    )

    # Mark invoice paid if the total covers it
    if sum(p.amount for p in invoice.payments.all()) >= invoice.amount:
        invoice.status = SubscriptionInvoice.Status.PAID
        invoice.paid_date = timezone.now().date()
        invoice.save(update_fields=['status', 'paid_date', 'updated_at'])

    # Update subscription state
    subscription = invoice.subscription
    subscription.last_payment_at = timezone.now()
    subscription.last_payment_amount = amount
    subscription.consecutive_failed_payments = 0

    # Move period forward if this is the current period invoice
    if invoice.period_end >= timezone.now().date():
        subscription.current_period_start = timezone.make_aware(
            timezone.datetime.combine(invoice.period_start, timezone.datetime.min.time())
        )
        subscription.current_period_end = timezone.make_aware(
            timezone.datetime.combine(invoice.period_end, timezone.datetime.min.time())
        )

    # Convert trial → active on first payment
    if subscription.status == Subscription.Status.TRIAL:
        subscription.status = Subscription.Status.ACTIVE

    if subscription.status == Subscription.Status.PAST_DUE:
        subscription.status = Subscription.Status.ACTIVE
        # Un-suspend the tenant if they were shut off
        if subscription.tenant and not subscription.tenant.is_active:
            subscription.tenant.is_active = True
            subscription.tenant.save(update_fields=['is_active'])

    subscription.save()

    logger.info(
        f'Payment recorded for {invoice.invoice_number}: '
        f'{amount} {invoice.currency} via {method}'
    )
    return payment