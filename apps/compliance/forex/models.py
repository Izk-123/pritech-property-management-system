from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from apps.core.models import TimeStampedModel


class ForexRate(TimeStampedModel):
    """Cached foreign exchange rates."""

    class Source(models.TextChoices):
        PYX_RATE = 'PYX', 'pyxrate (auto)'
        MANUAL = 'MAN', 'Manual Override'
        BANK = 'BANK', 'Bank Rate'

    base_currency = models.CharField(max_length=3, default='MWK')
    quote_currency = models.CharField(max_length=3)  # USD, EUR
    rate = models.DecimalField(max_digits=14, decimal_places=6)
    source = models.CharField(
        max_length=4, choices=Source.choices,
        default=Source.PYX_RATE,
    )
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-effective_from']
        indexes = [
            models.Index(fields=['quote_currency', 'effective_from']),
        ]

    @classmethod
    def get_current_rate(cls, quote_currency):
        """Get the most recent rate for a currency pair."""
        return cls.objects.filter(
            quote_currency=quote_currency,
            effective_to__isnull=True,
        ).first()

    def __str__(self):
        return f'1 {self.quote_currency} = {self.rate} {self.base_currency}'


class CurrencyLock(TimeStampedModel):
    """Locks an FX rate for a specific reservation or lease."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    from_currency = models.CharField(max_length=3)
    to_currency = models.CharField(max_length=3, default='MWK')
    locked_rate = models.DecimalField(max_digits=14, decimal_places=6)
    locked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f'{self.from_currency}→{self.to_currency} @ {self.locked_rate}'