from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel


class SaleListing(TimeStampedModel):
    """A property or unit listed for sale."""

    class Status(models.TextChoices):
        LISTED = 'LIST', 'Listed'
        UNDER_OFFER = 'OFFER', 'Under Offer'
        AGREEMENT = 'AGR', 'Agreement Signed'
        COMPLETED = 'COMP', 'Completed'
        WITHDRAWN = 'WDR', 'Withdrawn'

    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='sale_listings',
    )
    unit = models.ForeignKey(
        'properties.Unit', on_delete=models.CASCADE,
        related_name='sale_listings', null=True, blank=True,
    )
    asking_price = models.DecimalField(max_digits=14, decimal_places=2)
    minimum_price = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
    )
    currency = models.CharField(max_length=3, default='MWK')
    listing_date = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=5, choices=Status.choices, default=Status.LISTED,
    )
    description = models.TextField()
    agent = models.ForeignKey(
        'people.Person', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='listings',
    )

    class Meta:
        ordering = ['-listing_date']
        indexes = [models.Index(fields=['status'])]

    def __str__(self):
        return f'Listing: {self.property.name} ({self.get_status_display()})'


class SaleOffer(TimeStampedModel):
    """A buyer's offer on a listing."""

    class Status(models.TextChoices):
        PENDING = 'PEND', 'Pending'
        ACCEPTED = 'ACC', 'Accepted'
        REJECTED = 'REJ', 'Rejected'
        COUNTERED = 'CNTR', 'Countered'
        WITHDRAWN = 'WDR', 'Withdrawn'

    listing = models.ForeignKey(
        SaleListing, on_delete=models.CASCADE, related_name='offers',
    )
    buyer = models.ForeignKey(
        'people.Person', on_delete=models.CASCADE,
        related_name='sale_offers',
    )
    offer_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    status = models.CharField(
        max_length=5, choices=Status.choices, default=Status.PENDING,
    )
    conditions = models.TextField(
        blank=True,
        help_text='e.g., mortgage approval, survey, board approval',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Offer {self.offer_amount} by {self.buyer.full_name}'


class SaleAgreement(TimeStampedModel):
    """A legal sale contract with payment terms."""

    class PaymentType(models.TextChoices):
        LUMP_SUM = 'LUMP', 'Lump Sum'
        INSTALLMENT = 'INST', 'Installment Plan'

    agreement_number = models.CharField(max_length=20, unique=True, editable=False)
    listing = models.OneToOneField(
        SaleListing, on_delete=models.PROTECT, related_name='agreement',
    )
    buyer = models.ForeignKey(
        'people.Person', on_delete=models.PROTECT,
        related_name='sale_agreements',
    )
    seller = models.ForeignKey(
        'people.Person', on_delete=models.PROTECT,
        related_name='seller_agreements', null=True, blank=True,
    )
    sale_price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='MWK')
    deposit_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
    )
    deposit_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
    )
    payment_type = models.CharField(max_length=5, choices=PaymentType.choices)
    completion_date = models.DateField()
    document = models.ForeignKey(
        'documents.Document', on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.agreement_number:
            today = timezone.now().strftime('%Y%m%d')
            last = SaleAgreement.objects.filter(
                agreement_number__startswith=f'SAL-{today}'
            ).count() + 1
            self.agreement_number = f'SAL-{today}-{last:04d}'
        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        return self.sale_price - self.deposit_paid

    def __str__(self):
        return f'{self.agreement_number} — {self.buyer.full_name}'


class SaleInstallment(TimeStampedModel):
    """An individual installment in a payment plan."""

    agreement = models.ForeignKey(
        SaleAgreement, on_delete=models.CASCADE, related_name='installments',
    )
    installment_number = models.PositiveIntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
    )
    paid_date = models.DateField(null=True, blank=True)
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ['installment_number']
        unique_together = [('agreement', 'installment_number')]

    def __str__(self):
        return f'Installment {self.installment_number}: {self.amount}'

    @property
    def balance(self):
        return self.amount - self.amount_paid


class SaleCommission(TimeStampedModel):
    """Agent commission for a sale deal."""

    agreement = models.ForeignKey(
        SaleAgreement, on_delete=models.CASCADE, related_name='commissions',
    )
    agent = models.ForeignKey(
        'people.Person', on_delete=models.PROTECT,
        related_name='commissions',
    )
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = [('agreement', 'agent')]

    def __str__(self):
        return f'{self.agent.full_name}: {self.commission_amount}'