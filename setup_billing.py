"""
Phase 10 — Subscription & Billing installer.

Writes all new files, patches existing ones (settings.py, urls.py,
urls_public.py, mixins.py, base.html, requirements.txt).

Idempotent — every patch checks for a marker first.
Run from project root:  python setup_billing.py
"""
from pathlib import Path
import sys

BASE = Path.cwd()
UTF8 = "utf-8"


# ====================================================================
# Helpers
# ====================================================================

def write(path, content):
    p = BASE / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=UTF8)
    print(f"  + {path}")


def patch(path, old, new, marker=None):
    """Replace `old` with `new` in `path` exactly once.

    Skips if `marker` is already present (idempotency).
    """
    p = BASE / path
    if not p.exists():
        print(f"  ! {path} not found - skipping")
        return False
    t = p.read_text(encoding=UTF8)
    if marker and marker in t:
        print(f"  = {path} already patched")
        return True
    if old not in t:
        print(f"  ! anchor not found in {path}")
        return False
    p.write_text(t.replace(old, new, 1), encoding=UTF8)
    print(f"  + patched {path}")
    return True


def append(path, block, marker=None):
    """Append `block` to `path` unless `marker` is already present."""
    p = BASE / path
    if not p.exists():
        print(f"  ! {path} not found - skipping")
        return False
    t = p.read_text(encoding=UTF8)
    if marker and marker in t:
        print(f"  = {path} already has block")
        return True
    p.write_text(t.rstrip() + "\n\n" + block.lstrip() + "\n", encoding=UTF8)
    print(f"  + appended to {path}")
    return True


# ====================================================================
# 1. Folder structure
# ====================================================================

print("Creating folders...")
for d in [
    "apps/shared/billing/migrations",
    "templates/pages/billing",
    "templates/partials",
]:
    (BASE / d).mkdir(parents=True, exist_ok=True)


# ====================================================================
# 2. Python modules
# ====================================================================

print("\nWriting Python modules...")


write("apps/shared/billing/__init__.py", "")
write("apps/shared/billing/migrations/__init__.py", "")


write("apps/shared/billing/apps.py", '''\
from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.shared.billing'
    label = 'billing'
    verbose_name = 'Billing'
''')


write("apps/shared/billing/models.py", '''\
"""
Subscription billing - lives in the PUBLIC schema.

Everything platform-wide: plan catalogue, per-tenant subscriptions,
invoices, payments, and usage records.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SubscriptionPlan(models.Model):
    """A billable plan. Set once by a platform admin."""

    class Interval(models.TextChoices):
        MONTHLY = 'MONTH', _('Monthly')
        ANNUAL = 'YEAR', _('Annual')

    class Tier(models.TextChoices):
        STARTER = 'STARTER', _('Starter')
        PROFESSIONAL = 'PRO', _('Professional')
        ENTERPRISE = 'ENT', _('Enterprise')

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    tier = models.CharField(max_length=10, choices=Tier.choices)

    description = models.TextField(blank=True)
    features = models.JSONField(default=list, blank=True)

    price_mwk = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    price_usd = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    interval = models.CharField(
        max_length=5, choices=Interval.choices, default=Interval.MONTHLY,
    )

    max_properties = models.PositiveIntegerField(default=1)
    max_units = models.PositiveIntegerField(default=10)
    max_staff = models.PositiveIntegerField(default=3)
    max_storage_mb = models.PositiveIntegerField(default=500)

    includes_hospitality = models.BooleanField(default=True)
    includes_rentals = models.BooleanField(default=False)
    includes_sales = models.BooleanField(default=False)
    includes_eis = models.BooleanField(default=True)
    includes_whatsapp = models.BooleanField(default=True)
    includes_priority_support = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    trial_days = models.PositiveIntegerField(default=30)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'price_mwk']

    def __str__(self):
        return f'{self.name} ({self.get_interval_display()})'

    @property
    def is_annual(self):
        return self.interval == self.Interval.ANNUAL

    @property
    def monthly_equivalent_mwk(self):
        if self.is_annual:
            return (self.price_mwk / 12).quantize(Decimal('0.01'))
        return self.price_mwk


class Subscription(models.Model):
    """A tenant's subscription. One per tenant, ever."""

    class Status(models.TextChoices):
        TRIAL = 'TRIAL', _('Free Trial')
        ACTIVE = 'ACTIVE', _('Active')
        PAST_DUE = 'PAST_DUE', _('Past Due')
        SUSPENDED = 'SUSP', _('Suspended')
        CANCELLED = 'CANC', _('Cancelled')

    tenant = models.OneToOneField(
        'tenants.Tenant', on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.TRIAL,
    )

    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)

    billing_email = models.EmailField(blank=True)
    billing_phone = models.CharField(max_length=20, blank=True)
    preferred_currency = models.CharField(
        max_length=3, default='MWK',
        choices=[('MWK', 'MWK'), ('USD', 'USD')],
    )

    last_payment_at = models.DateTimeField(null=True, blank=True)
    last_payment_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    consecutive_failed_payments = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'current_period_end']),
            models.Index(fields=['status', 'trial_ends_at']),
        ]

    def __str__(self):
        return f'{self.tenant.name} / {self.plan.name} / {self.get_status_display()}'

    @property
    def is_trialing(self):
        return (
            self.status == self.Status.TRIAL
            and self.trial_ends_at
            and self.trial_ends_at > timezone.now()
        )

    @property
    def trial_days_remaining(self):
        if not self.trial_ends_at:
            return 0
        delta = self.trial_ends_at - timezone.now()
        return max(0, delta.days)

    @property
    def days_until_period_end(self):
        if not self.current_period_end:
            return 0
        delta = self.current_period_end - timezone.now()
        return max(0, delta.days)

    @property
    def is_past_due(self):
        return self.status == self.Status.PAST_DUE

    @property
    def is_suspended(self):
        return self.status == self.Status.SUSPENDED

    @property
    def can_access_platform(self):
        return self.status in (
            self.Status.TRIAL, self.Status.ACTIVE, self.Status.PAST_DUE,
        )


class SubscriptionInvoice(models.Model):
    """A billable invoice for one billing period."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Draft')
        ISSUED = 'ISSUED', _('Issued')
        PAID = 'PAID', _('Paid')
        OVERDUE = 'OVER', _('Overdue')
        VOID = 'VOID', _('Void')

    invoice_number = models.CharField(
        max_length=30, unique=True, editable=False,
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name='invoices',
    )
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.PROTECT,
        related_name='subscription_invoices',
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)

    period_start = models.DateField()
    period_end = models.DateField()
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    description = models.CharField(max_length=255, blank=True)

    status = models.CharField(
        max_length=5, choices=Status.choices, default=Status.DRAFT,
    )

    paychangu_charge_id = models.CharField(max_length=100, blank=True)
    paychangu_ref = models.CharField(max_length=100, blank=True)
    mra_invoice_number = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['subscription', 'status']),
        ]

    def __str__(self):
        return f'{self.invoice_number} / {self.tenant.name}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            today = timezone.now().strftime('%Y%m')
            last = SubscriptionInvoice.objects.filter(
                invoice_number__startswith=f'PMS-{today}',
            ).count() + 1
            self.invoice_number = f'PMS-{today}-{last:05d}'
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return (
            self.status in (self.Status.ISSUED, self.Status.OVERDUE)
            and self.due_date < timezone.now().date()
        )

    @property
    def days_overdue(self):
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.due_date).days


class SubscriptionPayment(models.Model):
    """A successful payment against a subscription invoice."""

    class Method(models.TextChoices):
        AIRTEL_MONEY = 'AIRTL', _('Airtel Money')
        TNM_MPAMBA = 'TNM', _('TNM Mpamba')
        CARD = 'CARD', _('Card')
        BANK_TRANSFER = 'BANK', _('Bank Transfer')
        MANUAL = 'MANUAL', _('Manual (platform admin)')

    invoice = models.ForeignKey(
        SubscriptionInvoice, on_delete=models.PROTECT, related_name='payments',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    method = models.CharField(max_length=6, choices=Method.choices)
    reference = models.CharField(max_length=100, blank=True)

    paychangu_charge_id = models.CharField(max_length=100, blank=True)
    payer_name = models.CharField(max_length=255, blank=True)
    payer_phone = models.CharField(max_length=20, blank=True)

    received_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f'{self.invoice.invoice_number} / {self.amount} {self.currency}'


class SubscriptionChange(models.Model):
    """Records every plan change, upgrade, downgrade, or cancellation."""

    class Kind(models.TextChoices):
        CREATED = 'CREATED', _('Subscription Created')
        UPGRADED = 'UP', _('Upgraded')
        DOWNGRADED = 'DOWN', _('Downgraded')
        CANCELLED = 'CANC', _('Cancelled')
        SUSPENDED = 'SUSP', _('Suspended')
        REACTIVATED = 'REACT', _('Reactivated')
        TRIAL_EXTENDED = 'TRIAL_EXT', _('Trial Extended')

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name='changes',
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    from_plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='changes_from',
    )
    to_plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='changes_to',
    )
    note = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        'shared_users.User', on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.subscription.tenant.name} / {self.get_kind_display()}'
''')


write("apps/shared/billing/services.py", '''\
"""
Billing services - all the business logic in one place so views and
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


@transaction.atomic
def start_trial(tenant, plan=None):
    """Called from provision_tenant() right after a tenant is created."""
    if plan is None:
        plan = SubscriptionPlan.objects.filter(
            tier=SubscriptionPlan.Tier.STARTER,
            is_active=True, is_public=True,
        ).order_by('price_mwk').first()

    if plan is None:
        logger.error(
            f'No Starter plan configured - cannot start trial '
            f'for {tenant.schema_name}'
        )
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
    """Upgrade or downgrade. Takes effect immediately."""
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

    subscription.invoices.filter(
        status__in=[
            SubscriptionInvoice.Status.DRAFT,
            SubscriptionInvoice.Status.ISSUED,
        ],
    ).update(status=SubscriptionInvoice.Status.VOID)

    logger.info(
        f'Plan changed for {subscription.tenant.schema_name}: '
        f'{old_plan.name} -> {new_plan.name}'
    )
    return subscription


@transaction.atomic
def cancel_subscription(subscription, performed_by=None, note=''):
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
    subscription.status = Subscription.Status.SUSPENDED
    subscription.suspended_at = timezone.now()
    subscription.save()

    tenant = subscription.tenant
    tenant.is_active = False
    tenant.save(update_fields=['is_active'])

    SubscriptionChange.objects.create(
        subscription=subscription,
        kind=SubscriptionChange.Kind.SUSPENDED,
        note=reason,
    )
    logger.warning(f'Suspended {subscription.tenant.schema_name}: {reason}')


@transaction.atomic
def reactivate_subscription(subscription, performed_by=None):
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


def _next_period_end(start, plan):
    if plan.interval == SubscriptionPlan.Interval.ANNUAL:
        return start + relativedelta(years=1)
    return start + relativedelta(months=1)


@transaction.atomic
def generate_invoice_for_subscription(subscription, period_start=None,
                                       period_end=None, due_date=None):
    """Generate a SubscriptionInvoice. Idempotent per period."""
    plan = subscription.plan
    now = timezone.now()
    period_start = period_start or subscription.current_period_end or now
    period_end = period_end or _next_period_end(period_start, plan)
    due_date = due_date or (now.date() + timedelta(days=7))

    ps = period_start.date() if hasattr(period_start, 'date') else period_start

    existing = subscription.invoices.filter(
        period_start=ps,
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
        period_start=ps,
        period_end=period_end.date() if hasattr(period_end, 'date') else period_end,
        due_date=due_date,
        amount=amount,
        currency=currency,
        description=f'{plan.name} / {plan.get_interval_display()} subscription',
        status=SubscriptionInvoice.Status.ISSUED,
    )
    logger.info(
        f'Generated {invoice.invoice_number} for '
        f'{subscription.tenant.schema_name}'
    )
    return invoice


@transaction.atomic
def record_subscription_payment(invoice, amount, method, reference='',
                                paychangu_charge_id='', payer_name='',
                                payer_phone='', received_by=None):
    """Idempotent. Called by webhook, admin action, or task."""
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

    if sum(p.amount for p in invoice.payments.all()) >= invoice.amount:
        invoice.status = SubscriptionInvoice.Status.PAID
        invoice.paid_date = timezone.now().date()
        invoice.save(update_fields=['status', 'paid_date', 'updated_at'])

    subscription = invoice.subscription
    subscription.last_payment_at = timezone.now()
    subscription.last_payment_amount = amount
    subscription.consecutive_failed_payments = 0

    if invoice.period_end >= timezone.now().date():
        subscription.current_period_start = timezone.make_aware(
            timezone.datetime.combine(
                invoice.period_start, timezone.datetime.min.time(),
            )
        )
        subscription.current_period_end = timezone.make_aware(
            timezone.datetime.combine(
                invoice.period_end, timezone.datetime.min.time(),
            )
        )

    if subscription.status == Subscription.Status.TRIAL:
        subscription.status = Subscription.Status.ACTIVE

    if subscription.status == Subscription.Status.PAST_DUE:
        subscription.status = Subscription.Status.ACTIVE
        if subscription.tenant and not subscription.tenant.is_active:
            subscription.tenant.is_active = True
            subscription.tenant.save(update_fields=['is_active'])

    subscription.save()

    logger.info(
        f'Payment recorded for {invoice.invoice_number}: '
        f'{amount} {invoice.currency} via {method}'
    )
    return payment
''')


write("apps/shared/billing/tasks.py", '''\
"""
Subscription billing lifecycle - every task iterates the public
schema (subscriptions live there).
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Subscription, SubscriptionInvoice
from .services import generate_invoice_for_subscription, suspend_subscription


logger = logging.getLogger(__name__)


@shared_task
def process_expired_trials():
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
            logger.exception(
                f'Trial conversion failed for {sub.tenant.schema_name}: {exc}'
            )

    return f'{created} trials converted to PAST_DUE'


@shared_task
def generate_period_invoices():
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
            logger.exception(
                f'Renewal invoice failed for {sub.tenant.schema_name}: {exc}'
            )

    return f'{created} renewal invoices generated'


@shared_task
def send_renewal_reminders():
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
        phone = normalise_mw_phone(
            sub.billing_phone or tenant.contact_phone,
        )
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
                subject=(
                    f'Pritech PMS - subscription renews on '
                    f'{sub.current_period_end:%d %b}'
                ),
                text_body=message,
            )
            sent += 1

    return f'{sent} renewal reminders sent'


@shared_task
def send_payment_reminders():
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
        phone = normalise_mw_phone(
            inv.subscription.billing_phone or tenant.contact_phone,
        )
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
                subject=f'Invoice {inv.invoice_number} - due {inv.due_date:%d %b}',
                text_body=message,
            )
            sent += 1

    return f'{sent} payment reminders sent'


@shared_task
def mark_invoices_overdue():
    today = timezone.now().date()
    updated = SubscriptionInvoice.objects.filter(
        status=SubscriptionInvoice.Status.ISSUED,
        due_date__lt=today,
    ).update(status=SubscriptionInvoice.Status.OVERDUE)

    Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        invoices__status=SubscriptionInvoice.Status.OVERDUE,
    ).distinct().update(status=Subscription.Status.PAST_DUE)

    return f'{updated} invoices marked OVERDUE'


@shared_task
def suspend_delinquent_tenants(grace_days=14):
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
                suspend_subscription(
                    sub, reason=f'Invoice {latest.invoice_number} overdue',
                )
                suspended += 1
            except Exception as exc:
                logger.exception(
                    f'Suspend failed for {sub.tenant.schema_name}: {exc}'
                )

    return f'{suspended} tenants suspended'
''')


write("apps/shared/billing/views.py", '''\
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
''')


write("apps/shared/billing/urls.py", '''\
from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('', views.BillingDashboardView.as_view(), name='dashboard'),
    path('plans/', views.PlanListView.as_view(), name='plans'),
    path('plans/<int:plan_id>/change/', views.ChangePlanView.as_view(),
         name='change_plan'),
    path('invoice/<int:invoice_id>/pay/', views.PayInvoiceView.as_view(),
         name='pay_invoice'),
    path('invoice/<int:invoice_id>/pdf/', views.InvoicePDFView.as_view(),
         name='invoice_pdf'),
    path('paychangu/callback/', views.paychangu_callback,
         name='paychangu_callback'),
]
''')


write("apps/shared/billing/urls_admin.py", '''\
from django.urls import path
from . import views

app_name = 'billing_admin'

urlpatterns = [
    path('', views.AdminSubscriptionListView.as_view(), name='admin_list'),
    path('invoice/<int:invoice_id>/mark-paid/',
         views.AdminMarkPaidView.as_view(), name='mark_paid'),
]
''')


write("apps/shared/billing/admin.py", '''\
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Subscription, SubscriptionChange, SubscriptionInvoice,
    SubscriptionPayment, SubscriptionPlan,
)


class InvoiceInline(TabularInline):
    model = SubscriptionInvoice
    extra = 0
    fields = ('invoice_number', 'period_start', 'period_end',
              'amount', 'currency', 'status')
    readonly_fields = ('invoice_number',)


class ChangeInline(TabularInline):
    model = SubscriptionChange
    extra = 0
    fields = ('kind', 'from_plan', 'to_plan', 'note', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(ModelAdmin):
    list_display = ('name', 'tier', 'interval', 'price_mwk',
                    'max_properties', 'max_units', 'is_active')
    list_filter = ('tier', 'interval', 'is_active', 'is_public')
    ordering = ('display_order', 'price_mwk')


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ('tenant', 'plan', 'status',
                    'current_period_end', 'trial_ends_at')
    list_filter = ('status', 'plan')
    search_fields = ('tenant__name', 'tenant__schema_name')
    readonly_fields = ('created_at', 'updated_at', 'last_payment_at')
    inlines = [InvoiceInline, ChangeInline]


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(ModelAdmin):
    list_display = ('invoice_number', 'tenant', 'amount', 'currency',
                    'due_date', 'status')
    list_filter = ('status', 'currency')
    search_fields = ('invoice_number', 'tenant__name')
    readonly_fields = ('invoice_number',)


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(ModelAdmin):
    list_display = ('invoice', 'amount', 'currency', 'method', 'received_at')
    list_filter = ('method', 'currency')


@admin.register(SubscriptionChange)
class SubscriptionChangeAdmin(ModelAdmin):
    list_display = ('subscription', 'kind', 'from_plan', 'to_plan', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('created_at',)
''')


write("apps/shared/billing/pdf.py", '''\
"""Subscription invoice PDF - STUB.

Implements render_subscription_invoice() by adapting the pattern in
apps/core/documents/pdf/folio.py. Kept as a stub so imports don't
fail at startup.
"""


def render_subscription_invoice(invoice):
    raise NotImplementedError(
        'render_subscription_invoice() is not implemented yet. '
        'See apps/core/documents/pdf/folio.py for the pattern.'
    )
''')


# ====================================================================
# 3. Templates
# ====================================================================

print("\nWriting templates...")


write("templates/partials/_subscription_banner.html", '''\
{% load i18n %}

{% if request.subscription_state and request.subscription_state.show %}
<div data-animate="fade-down" data-animate-now
     class="border-b
            {% if request.subscription_state.kind == 'trial' %}border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-900/30
            {% elif request.subscription_state.kind == 'past_due' %}border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/30
            {% else %}border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-white/5{% endif %}">
  <div class="mx-auto flex max-w-6xl items-center justify-between gap-3
              px-4 py-2 text-xs sm:px-6">
    <p class="text-slate-700 dark:text-slate-200">
      {{ request.subscription_state.message }}
    </p>
    <a href="{% url 'billing:dashboard' %}"
       class="shrink-0 rounded-lg
              {% if request.subscription_state.kind == 'trial' %}
              bg-blue-600 text-white hover:bg-blue-500
              {% elif request.subscription_state.kind == 'past_due' %}
              bg-amber-600 text-white hover:bg-amber-500
              {% else %}
              bg-slate-700 text-white hover:bg-slate-600
              {% endif %}
              px-3 py-1 text-xs font-medium transition-colors">
      {% if request.subscription_state.kind == 'past_due' %}
      {% trans "Pay now" %}
      {% else %}
      {% trans "View billing" %}
      {% endif %}
    </a>
  </div>
</div>
{% endif %}
''')


write("templates/pages/billing/dashboard.html", '''\
{% extends "base.html" %}
{% load i18n humanize %}

{% block title %}{% trans "Billing" %} - {{ request.tenant.name }}{% endblock %}

{% block content %}
<div class="mx-auto max-w-4xl px-4 py-8 sm:px-6">

  <h1 data-animate="fade-up" data-animate-now
      class="text-2xl font-bold tracking-tight sm:text-3xl">
    {% trans "Billing & Subscription" %}
  </h1>

  {% if subscription %}
  <section data-animate="fade-up" data-animate-delay="80"
           class="card mt-6 overflow-hidden !p-0">
    <div class="border-b border-slate-200 p-5 dark:border-slate-700">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-xs font-bold uppercase tracking-wider
                    text-slate-500 dark:text-slate-400">
            {% trans "Current plan" %}
          </p>
          <p class="mt-1 text-2xl font-bold">{{ subscription.plan.name }}</p>
          <p class="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
            MWK {{ subscription.plan.price_mwk|floatformat:0|intcomma }}
            / {{ subscription.plan.get_interval_display|lower }}
          </p>
        </div>
        <span class="chip
          {% if subscription.status == 'TRIAL' %}bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-200
          {% elif subscription.status == 'ACTIVE' %}chip-green
          {% elif subscription.status == 'PAST_DUE' %}bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200
          {% else %}bg-red-100 text-red-800 dark:bg-red-900/60 dark:text-red-200{% endif %}">
          {{ subscription.get_status_display }}
        </span>
      </div>

      {% if subscription.is_trialing %}
      <p class="mt-3 text-sm text-slate-600 dark:text-slate-300">
        {% blocktrans with days=subscription.trial_days_remaining ends=subscription.trial_ends_at|date:"d M Y" %}
        Free trial - {{ days }} days remaining (ends {{ ends }})
        {% endblocktrans %}
      </p>
      {% elif subscription.current_period_end %}
      <p class="mt-3 text-sm text-slate-600 dark:text-slate-300">
        {% blocktrans with date=subscription.current_period_end|date:"d M Y" %}
        Renews on {{ date }}
        {% endblocktrans %}
      </p>
      {% endif %}
    </div>

    <div class="flex flex-wrap gap-2 p-5">
      <a href="{% url 'billing:plans' %}"
         data-press data-hover="grow"
         class="btn btn-primary">
        {% trans "Change plan" %}
      </a>
    </div>
  </section>

  {% if upcoming_invoice %}
  <section data-animate="fade-up" data-animate-delay="140"
           class="card mt-6 border-amber-200 bg-amber-50 dark:border-amber-800
                  dark:bg-amber-900/20">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p class="text-xs font-bold uppercase tracking-wider
                  text-amber-700 dark:text-amber-300">
          {% trans "Payment due" %}
        </p>
        <p class="mt-1 text-lg font-semibold">
          {{ upcoming_invoice.currency }} {{ upcoming_invoice.amount|floatformat:0|intcomma }}
        </p>
        <p class="text-xs text-amber-700 dark:text-amber-300 mt-0.5">
          {% blocktrans with number=upcoming_invoice.invoice_number due=upcoming_invoice.due_date|date:"d M Y" %}
          Invoice {{ number }} - due {{ due }}
          {% endblocktrans %}
        </p>
      </div>
      <form method="post"
            action="{% url 'billing:pay_invoice' upcoming_invoice.pk %}">
        {% csrf_token %}
        <button type="submit" data-press data-hover="grow"
                class="btn bg-amber-600 text-white hover:bg-amber-500">
          {% trans "Pay now" %}
        </button>
      </form>
    </div>
  </section>
  {% endif %}

  {% if invoices %}
  <section data-animate="fade-up" data-animate-delay="200" class="mt-8">
    <h2 class="mb-3 text-lg font-semibold">{% trans "Recent invoices" %}</h2>
    <div class="card overflow-hidden !p-0">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 dark:bg-white/5">
          <tr class="text-left text-xs uppercase tracking-wider
                     text-slate-500 dark:text-slate-400">
            <th class="px-4 py-2">{% trans "Invoice" %}</th>
            <th class="px-4 py-2">{% trans "Period" %}</th>
            <th class="px-4 py-2 text-right">{% trans "Amount" %}</th>
            <th class="px-4 py-2">{% trans "Status" %}</th>
            <th class="px-4 py-2 text-right">{% trans "Actions" %}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100 dark:divide-slate-700/60">
          {% for inv in invoices %}
          <tr>
            <td class="px-4 py-3 font-mono text-xs">{{ inv.invoice_number }}</td>
            <td class="px-4 py-3 text-xs">
              {{ inv.period_start|date:"d M" }} - {{ inv.period_end|date:"d M Y" }}
            </td>
            <td class="px-4 py-3 text-right font-medium">
              {{ inv.currency }} {{ inv.amount|floatformat:0|intcomma }}
            </td>
            <td class="px-4 py-3">
              <span class="chip
                {% if inv.status == 'PAID' %}chip-green
                {% elif inv.status == 'OVER' %}bg-red-100 text-red-800 dark:bg-red-900/60 dark:text-red-200
                {% elif inv.status == 'VOID' %}chip-slate
                {% else %}bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-200{% endif %}">
                {{ inv.get_status_display }}
              </span>
            </td>
            <td class="px-4 py-3 text-right">
              <a href="{% url 'billing:invoice_pdf' inv.pk %}"
                 target="_blank" rel="noopener"
                 class="text-xs text-primary-600 hover:underline
                        dark:text-primary-400">
                {% trans "PDF" %}
              </a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </section>
  {% endif %}

  {% else %}
  <div class="card mt-6 text-center py-10">
    <p class="text-slate-500 dark:text-slate-400">
      {% trans "No subscription found. Please contact support." %}
    </p>
  </div>
  {% endif %}

</div>
{% endblock %}
''')


write("templates/pages/billing/plans.html", '''\
{% extends "base.html" %}
{% load i18n humanize %}

{% block title %}{% trans "Plans" %} - {{ request.tenant.name }}{% endblock %}

{% block content %}
<div class="mx-auto max-w-5xl px-4 py-8 sm:px-6">

  <h1 data-animate="fade-up" data-animate-now
      class="text-center text-3xl font-bold tracking-tight">
    {% trans "Choose your plan" %}
  </h1>
  <p data-animate="fade-up" data-animate-delay="80"
     class="mt-2 text-center text-slate-500 dark:text-slate-400">
    {% trans "Change at any time. Cancel at end of period." %}
  </p>

  <div data-stagger="0.08" class="mt-8 grid gap-5 sm:grid-cols-3">
    {% for plan in plans %}
    <div data-animate="fade-up" data-hover="lift"
         class="card flex flex-col
                {% if subscription and subscription.plan.pk == plan.pk %}
                ring-2 ring-primary-500
                {% endif %}">
      <h2 class="text-lg font-bold">{{ plan.name }}</h2>
      <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
        {{ plan.get_interval_display }}
      </p>

      <p class="mt-4 text-3xl font-bold text-primary-600 dark:text-primary-400">
        MWK {{ plan.price_mwk|floatformat:0|intcomma }}
        <span class="text-sm font-normal text-slate-500">
          / {% if plan.is_annual %}{% trans "year" %}{% else %}{% trans "month" %}{% endif %}
        </span>
      </p>
      {% if plan.price_usd %}
      <p class="text-xs text-slate-500 dark:text-slate-400">
        approx USD {{ plan.price_usd|floatformat:0 }}
      </p>
      {% endif %}

      <ul class="mt-5 flex-1 space-y-2 text-sm">
        <li class="flex items-start gap-2">
          <span class="text-primary-500">+</span>
          {% if plan.max_properties == 0 %}
          {% trans "Unlimited properties" %}
          {% else %}
          {{ plan.max_properties }} {% trans "properties" %}
          {% endif %}
        </li>
        <li class="flex items-start gap-2">
          <span class="text-primary-500">+</span>
          {% if plan.max_units == 0 %}
          {% trans "Unlimited units" %}
          {% else %}
          {{ plan.max_units }} {% trans "units" %}
          {% endif %}
        </li>
        <li class="flex items-start gap-2">
          <span class="text-primary-500">+</span>
          {% if plan.max_staff == 0 %}
          {% trans "Unlimited staff" %}
          {% else %}
          {{ plan.max_staff }} {% trans "staff accounts" %}
          {% endif %}
        </li>
        {% if plan.includes_hospitality %}
        <li class="flex items-start gap-2">
          <span class="text-primary-500">+</span>
          {% trans "Hospitality module" %}
        </li>
        {% endif %}
        {% if plan.includes_rentals %}
        <li class="flex items-start gap-2">
          <span class="text-primary-500">+</span>
          {% trans "Rental management" %}
        </li>
        {% endif %}
        {% if plan.includes_sales %}
        <li class="flex items-start gap-2">
          <span class="text-primary-500">+</span>
          {% trans "Property sales" %}
        </li>
        {% endif %}
        {% if plan.includes_eis %}
        <li class="flex items-start gap-2">
          <span class="text-primary-500">+</span>
          {% trans "MRA EIS compliance" %}
        </li>
        {% endif %}
        {% if plan.includes_priority_support %}
        <li class="flex items-start gap-2">
          <span class="text-primary-500">+</span>
          {% trans "Priority support" %}
        </li>
        {% endif %}
      </ul>

      <form method="post"
            action="{% url 'billing:change_plan' plan.pk %}"
            class="mt-5">
        {% csrf_token %}
        {% if subscription and subscription.plan.pk == plan.pk %}
        <button type="button" disabled
                class="btn w-full bg-slate-100 text-slate-500
                       dark:bg-white/5 dark:text-slate-500">
          {% trans "Current plan" %}
        </button>
        {% else %}
        <button type="submit" data-press data-hover="grow"
                class="btn btn-primary w-full">
          {% trans "Switch to this plan" %}
        </button>
        {% endif %}
      </form>
    </div>
    {% endfor %}
  </div>

</div>
{% endblock %}
''')


write("templates/pages/billing/admin_list.html", '''\
{% extends "admin/base_site.html" %}
{% load i18n humanize %}

{% block content %}
<div class="p-6">
  <h1 class="text-2xl font-bold">{% trans "Tenant subscriptions" %}</h1>

  <div class="mt-4 grid grid-cols-3 gap-4">
    <div class="rounded-lg bg-slate-50 p-4">
      <p class="text-xs uppercase text-slate-500">MRR (MWK)</p>
      <p class="mt-1 text-2xl font-bold">{{ mrr|floatformat:0|intcomma }}</p>
    </div>
    <div class="rounded-lg bg-blue-50 p-4">
      <p class="text-xs uppercase text-blue-700">Trials</p>
      <p class="mt-1 text-2xl font-bold text-blue-700">{{ trial_count }}</p>
    </div>
    <div class="rounded-lg bg-amber-50 p-4">
      <p class="text-xs uppercase text-amber-700">Past due</p>
      <p class="mt-1 text-2xl font-bold text-amber-700">{{ past_due_count }}</p>
    </div>
  </div>

  <form method="get" class="mt-6 flex gap-2">
    <select name="status" class="rounded border px-3 py-2">
      <option value="">{% trans "All statuses" %}</option>
      {% for code, label in statuses %}
      <option value="{{ code }}" {% if current_status == code %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <button type="submit" class="rounded bg-slate-700 px-4 py-2 text-white">
      {% trans "Filter" %}
    </button>
  </form>

  <table class="mt-6 w-full text-sm">
    <thead class="bg-slate-50">
      <tr>
        <th class="px-3 py-2 text-left">{% trans "Tenant" %}</th>
        <th class="px-3 py-2 text-left">{% trans "Plan" %}</th>
        <th class="px-3 py-2 text-left">{% trans "Status" %}</th>
        <th class="px-3 py-2 text-left">{% trans "Renews" %}</th>
      </tr>
    </thead>
    <tbody>
      {% for sub in subscriptions %}
      <tr class="border-b">
        <td class="px-3 py-2">{{ sub.tenant.name }}</td>
        <td class="px-3 py-2">{{ sub.plan.name }}</td>
        <td class="px-3 py-2">{{ sub.get_status_display }}</td>
        <td class="px-3 py-2">{{ sub.current_period_end|date:"d M Y"|default:"-" }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="4" class="px-3 py-6 text-center text-slate-500">{% trans "No subscriptions." %}</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
''')


# ====================================================================
# 4. Patch existing files
# ====================================================================

print("\nPatching existing files...")


# ---- settings.py: add 'apps.shared.billing' to SHARED_APPS ----
patch(
    "config/settings.py",
    old="    'apps.shared.users',\n    'apps.core.sync',",
    new="    'apps.shared.users',\n    'apps.shared.billing',\n    'apps.core.sync',",
    marker="'apps.shared.billing'",
)

# ---- settings.py: add Phase 10 Celery beat entries ----
celery_entries = """\
    # ─── Phase 10 — Subscription billing ───────────────────────────
    'process-expired-trials': {
        'task': 'apps.shared.billing.tasks.process_expired_trials',
        'schedule': crontab(hour=2, minute=0),
    },
    'generate-period-invoices': {
        'task': 'apps.shared.billing.tasks.generate_period_invoices',
        'schedule': crontab(hour=2, minute=15),
    },
    'send-renewal-reminders': {
        'task': 'apps.shared.billing.tasks.send_renewal_reminders',
        'schedule': crontab(hour=6, minute=0),
    },
    'send-payment-reminders': {
        'task': 'apps.shared.billing.tasks.send_payment_reminders',
        'schedule': crontab(hour=9, minute=0),
    },
    'mark-invoices-overdue': {
        'task': 'apps.shared.billing.tasks.mark_invoices_overdue',
        'schedule': crontab(hour=9, minute=30),
    },
    'suspend-delinquent-tenants': {
        'task': 'apps.shared.billing.tasks.suspend_delinquent_tenants',
        'schedule': crontab(hour=10, minute=0),
    },
    'celery-heartbeat': {"""

patch(
    "config/settings.py",
    old="    'celery-heartbeat': {",
    new=celery_entries,
    marker="process-expired-trials",
)


# ---- config/urls.py: add billing include before admin ----
patch(
    "config/urls.py",
    old="    # ─── Admin ─────────────────────────────────────────────────────\n    path('admin/', admin.site.urls),",
    new=(
        "    # ─── Billing (Phase 10) ────────────────────────────────────────\n"
        "    path('billing/', include('apps.shared.billing.urls')),\n\n"
        "    # ─── Admin ─────────────────────────────────────────────────────\n"
        "    path('admin/', admin.site.urls),"
    ),
    marker="apps.shared.billing.urls",
)


# ---- config/urls_public.py: add billing admin include after platform ----
patch(
    "config/urls_public.py",
    old="    path('platform/', include('apps.shared.tenants.urls_platform')),",
    new=(
        "    path('platform/', include('apps.shared.tenants.urls_platform')),\n\n"
        "    # ─── Billing admin (Phase 10) ──────────────────────────────────\n"
        "    path('platform/billing/', include('apps.shared.billing.urls_admin')),"
    ),
    marker="apps.shared.billing.urls_admin",
)


# ---- apps/core/mixins.py: append subscription mixins ----
mixins_block = '''\
# ─────────────────────────────────────────────────────────────────────
# Phase 10 - Subscription enforcement
# ─────────────────────────────────────────────────────────────────────


class SubscriptionRequiredMixin:
    """
    Redirect suspended or cancelled tenants to the billing page.
    Applied to every authenticated view.
    """

    def dispatch(self, request, *args, **kwargs):
        user = getattr(request, 'user', None)
        tenant = getattr(request, 'tenant', None)

        if not tenant or tenant.schema_name == 'public':
            return super().dispatch(request, *args, **kwargs)

        if user and user.is_authenticated and (
            getattr(user, 'is_platform_admin', False) or user.is_superuser
        ):
            return super().dispatch(request, *args, **kwargs)

        subscription = getattr(tenant, 'subscription', None)
        if subscription is None:
            return super().dispatch(request, *args, **kwargs)

        request.subscription = subscription
        request.subscription_state = _subscription_banner_state(subscription)

        if subscription.is_suspended:
            from django.shortcuts import redirect
            return redirect('billing:dashboard')

        return super().dispatch(request, *args, **kwargs)


def _subscription_banner_state(subscription):
    """Return a dict describing what banner (if any) the UI should show."""
    if subscription.status == subscription.Status.TRIAL:
        days = subscription.trial_days_remaining
        return {
            'kind': 'trial',
            'days_remaining': days,
            'message': (
                f'Free trial - {days} day'
                f'{"s" if days != 1 else ""} remaining'
            ),
            'show': True,
        }
    if subscription.status == subscription.Status.PAST_DUE:
        return {
            'kind': 'past_due',
            'days_remaining': 0,
            'message': 'Payment overdue - please pay to avoid suspension.',
            'show': True,
        }
    if 0 < subscription.days_until_period_end <= 7:
        return {
            'kind': 'renewal',
            'days_remaining': subscription.days_until_period_end,
            'message': (
                f'Subscription renews in '
                f'{subscription.days_until_period_end} day'
                f'{"s" if subscription.days_until_period_end != 1 else ""}'
            ),
            'show': True,
        }
    return {'show': False}


class TenantStaffRequiredMixin(SubscriptionRequiredMixin, StaffRequiredMixin):
    """Staff-only view that also enforces an active subscription."""
'''

append("apps/core/mixins.py", mixins_block, marker="SubscriptionRequiredMixin")


# ---- requirements.txt: add python-dateutil ----
req_path = BASE / "requirements.txt"
if req_path.exists():
    t = req_path.read_text(encoding=UTF8)
    if "python-dateutil" not in t:
        req_path.write_text(
            t.rstrip() + "\n\n# Phase 10 - subscription billing\npython-dateutil\n",
            encoding=UTF8,
        )
        print("  + appended python-dateutil to requirements.txt")
    else:
        print("  = requirements.txt already has python-dateutil")


# ---- base.html: add subscription banner ----
base_html = BASE / "templates/base.html"
if base_html.exists():
    t = base_html.read_text(encoding=UTF8)
    if "_subscription_banner.html" in t:
        print("  = templates/base.html already includes banner")
    else:
        anchor = '{% include "partials/_header_tenant.html" %}'
        if anchor in t:
            t = t.replace(
                anchor,
                anchor + '\n    {% include "partials/_subscription_banner.html" %}',
                1,
            )
            base_html.write_text(t, encoding=UTF8)
            print("  + added subscription banner to templates/base.html")
        else:
            print("  ! no _header_tenant include found in templates/base.html")
else:
    print("  ! templates/base.html not found")


# ====================================================================
# Done
# ====================================================================

print()
print("=" * 60)
print(" Phase 10 billing module installed.")
print("=" * 60)
print()
print("Next steps:")
print("  1. pip install python-dateutil")
print("  2. python manage.py makemigrations billing")
print("  3. python manage.py migrate_schemas --shared")
print("  4. python manage.py shell  (then run the seed script)")
print()
print("Seed script (paste into the shell):")
print()
print("  from apps.shared.billing.models import SubscriptionPlan")
print("  plans = [")
print("      dict(code='starter-monthly', name='Starter', tier='STARTER',")
print("           interval='MONTH', price_mwk=25000, price_usd=15,")
print("           max_properties=1, max_units=10, max_staff=3,")
print("           includes_hospitality=True, display_order=1),")
print("      dict(code='starter-annual', name='Starter (Annual)',")
print("           tier='STARTER', interval='YEAR', price_mwk=250000,")
print("           price_usd=150, max_properties=1, max_units=10,")
print("           max_staff=3, includes_hospitality=True, display_order=2),")
print("      dict(code='professional-monthly', name='Professional',")
print("           tier='PRO', interval='MONTH', price_mwk=60000,")
print("           price_usd=35, max_properties=5, max_units=100,")
print("           max_staff=15, includes_hospitality=True,")
print("           includes_rentals=True, includes_sales=True, display_order=3),")
print("      dict(code='professional-annual', name='Professional (Annual)',")
print("           tier='PRO', interval='YEAR', price_mwk=600000,")
print("           price_usd=350, max_properties=5, max_units=100,")
print("           max_staff=15, includes_hospitality=True,")
print("           includes_rentals=True, includes_sales=True, display_order=4),")
print("      dict(code='enterprise-monthly', name='Enterprise', tier='ENT',")
print("           interval='MONTH', price_mwk=150000, price_usd=90,")
print("           max_properties=0, max_units=0, max_staff=0,")
print("           includes_hospitality=True, includes_rentals=True,")
print("           includes_sales=True, includes_priority_support=True,")
print("           display_order=5),")
print("  ]")
print("  for p in plans:")
print("      SubscriptionPlan.objects.update_or_create(code=p['code'], defaults=p)")
print("  print(f'{SubscriptionPlan.objects.count()} plans configured')")
print()