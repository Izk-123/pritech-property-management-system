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
