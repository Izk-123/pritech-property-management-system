"""
Subscription billing lifecycle — every task is tenant-agnostic and
iterates over the public schema (subscriptions live there).

Run order (see CELERY_BEAT_SCHEDULE):
  02:00  process_expired_trials
  02:15  generate_period_invoices
  06:00  send_renewal_reminders
  09:00  send_payment_reminders
  09:30  mark_invoices_overdue
  10:00  suspend_delinquent_tenants
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from .models import (
    Subscription, SubscriptionInvoice, SubscriptionPlan,
)
from .services import (
    activate_subscription, generate_invoice_for_subscription,
    suspend_subscription,
)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# 02:00 — Trial conversions
# ─────────────────────────────────────────────────────────────────────

@shared_task
def process_expired_trials():
    """
    Find trials that have expired and generate their first paid invoice.
    Tenant keeps access (PAST_DUE status) until the invoice is overdue.
    """
    now = timezone.now()
    expired = Subscription.objects.filter(
        status=Subscription.Status.TRIAL,
        trial_ends_at__lte=now,
    ).select_related('plan', 'tenant')

    created = 0
    for sub in expired:
        try:
            sub.status = Subscription.Status.PAST_DUE
            sub.save(update_fields=['status', 'updated_at'])
            generate_invoice_for_subscription(sub)
            created += 1
        except Exception as exc:
            logger.exception(f'Trial conversion failed for {sub.tenant.schema_name}: {exc}')

    return f'{created} trials converted to PAST_DUE'


# ─────────────────────────────────────────────────────────────────────
# 02:15 — Period renewals
# ─────────────────────────────────────────────────────────────────────

@shared_task
def generate_period_invoices():
    """
    For every ACTIVE subscription whose period ends within the next
    7 days, generate the invoice for the next period.
    """
    now = timezone.now()
    soon = now + timedelta(days=7)
    candidates = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        current_period_end__lte=soon,
        current_period_end__gte=now,
    ).select_related('plan', 'tenant')

    created = 0
    for sub in candidates:
        try:
            inv = generate_invoice_for_subscription(
                sub,
                period_start=sub.current_period_end,
                period_end=sub.current_period_end + timedelta(days=30),
                due_date=sub.current_period_end.date(),
            )
            if inv:
                created += 1
        except Exception as exc:
            logger.exception(f'Renewal invoice failed for {sub.tenant.schema_name}: {exc}')

    return f'{created} renewal invoices generated'


# ─────────────────────────────────────────────────────────────────────
# 06:00 — Renewal reminders (7 days out)
# ─────────────────────────────────────────────────────────────────────

@shared_task
def send_renewal_reminders():
    """
    Notify tenants whose subscription renews within 7 days.
    Uses WhatsApp if the number is set, otherwise email.
    """
    from apps.communications.services import (
        WhatsAppClient, normalise_mw_phone, send_email,
    )

    now = timezone.now()
    soon = now + timedelta(days=7)
    subs = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        current_period_end__lte=soon,
        current_period_end__gte=now,
    ).select_related('plan', 'tenant')

    sent = 0
    for sub in subs:
        tenant = sub.tenant
        phone = normalise_mw_phone(sub.billing_phone or tenant.contact_phone)
        amount = sub.plan.price_mwk
        message = (
            f'Hi {tenant.name}, your Pritech PMS subscription for '
            f'{sub.plan.name} renews on {sub.current_period_end:%d %b}. '
            f'Amount: MWK {amount:,.0f}. '
            f'Pay online at https://{tenant.schema_name}.pms.pritechmw.com/billing/'
        )

        if phone:
            client = WhatsAppClient()
            if client.is_configured():
                client.send_text(to=phone, body=message)
                sent += 1
                continue

        if tenant.contact_email:
            send_email(
                to=tenant.contact_email,
                subject=f'Pritech PMS — subscription renews on {sub.current_period_end:%d %b}',
                text_body=message,
            )
            sent += 1

    return f'{sent} renewal reminders sent'


# ─────────────────────────────────────────────────────────────────────
# 09:00 — Payment reminders (1 day before due)
# ─────────────────────────────────────────────────────────────────────

@shared_task
def send_payment_reminders():
    """
    For invoices due tomorrow or today, remind the tenant.
    """
    from apps.communications.services import (
        WhatsAppClient, normalise_mw_phone, send_email,
    )

    tomorrow = timezone.now().date() + timedelta(days=1)
    today = timezone.now().date()
    invoices = SubscriptionInvoice.objects.filter(
        status=SubscriptionInvoice.Status.ISSUED,
        due_date__in=[today, tomorrow],
    ).select_related('tenant', 'plan')

    sent = 0
    for inv in invoices:
        tenant = inv.tenant
        phone = normalise_mw_phone(inv.subscription.billing_phone or tenant.contact_phone)
        message = (
            f'Pritech PMS invoice {inv.invoice_number}: '
            f'{inv.currency} {inv.amount:,.0f} is due on '
            f'{inv.due_date:%d %b}. Pay online at '
            f'https://{tenant.schema_name}.pms.pritechmw.com/billing/'
        )

        if phone:
            client = WhatsAppClient()
            if client.is_configured():
                client.send_text(to=phone, body=message)
                sent += 1
                continue

        if tenant.contact_email:
            send_email(
                to=tenant.contact_email,
                subject=f'Invoice {inv.invoice_number} — due {inv.due_date:%d %b}',
                text_body=message,
            )
            sent += 1

    return f'{sent} payment reminders sent'


# ─────────────────────────────────────────────────────────────────────
# 09:30 — Mark overdue
# ─────────────────────────────────────────────────────────────────────

@shared_task
def mark_invoices_overdue():
    """Flag ISSUED invoices past their due date as OVERDUE."""
    today = timezone.now().date()
    updated = SubscriptionInvoice.objects.filter(
        status=SubscriptionInvoice.Status.ISSUED,
        due_date__lt=today,
    ).update(status=SubscriptionInvoice.Status.OVERDUE)

    # Also flip the subscription to PAST_DUE for UI clarity
    Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        invoices__status=SubscriptionInvoice.Status.OVERDUE,
    ).distinct().update(status=Subscription.Status.PAST_DUE)

    return f'{updated} invoices marked OVERDUE'


# ─────────────────────────────────────────────────────────────────────
# 10:00 — Suspend delinquent tenants
# ─────────────────────────────────────────────────────────────────────

@shared_task
def suspend_delinquent_tenants(grace_days=14):
    """
    Suspend tenants whose subscription has been PAST_DUE for more than
    `grace_days`. This is the last resort — trial conversion is the
    first notice.
    """
    cutoff = timezone.now().date() - timedelta(days=grace_days)
    delinquent = Subscription.objects.filter(
        status=Subscription.Status.PAST_DUE,
    ).select_related('tenant')

    suspended = 0
    for sub in delinquent:
        latest = sub.invoices.filter(
            status=SubscriptionInvoice.Status.OVERDUE,
            due_date__lt=cutoff,
        ).order_by('-due_date').first()
        if latest:
            try:
                suspend_subscription(sub, reason=f'Invoice {latest.invoice_number} overdue')
                suspended += 1
            except Exception as exc:
                logger.exception(f'Suspend failed for {sub.tenant.schema_name}: {exc}')

    return f'{suspended} tenants suspended'