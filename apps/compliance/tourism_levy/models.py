from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel


class TourismLevyConfig(TimeStampedModel):
    """Tourism levy configuration per property."""

    property = models.OneToOneField(
        'properties.Property', on_delete=models.CASCADE,
        related_name='levy_config',
    )
    levy_percent = models.DecimalField(
        max_digits=4, decimal_places=2, default=1.00,
        help_text='Default 1% per Tourism and Hotels Act',
    )
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField()

    class Meta:
        verbose_name_plural = 'Tourism Levy Configurations'

    def __str__(self):
        return f'{self.property.name} — {self.levy_percent}%'


class TourismLevyRecord(TimeStampedModel):
    """Record of Tourism Levy applied to a folio."""

    folio = models.ForeignKey(
        'folios.Folio', on_delete=models.CASCADE,
        related_name='levy_records',
    )
    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
    )
    room_charge_amount = models.DecimalField(max_digits=12, decimal_places=2)
    levy_rate = models.DecimalField(max_digits=4, decimal_places=2)
    levy_amount = models.DecimalField(max_digits=12, decimal_places=2)
    period_month = models.DateField(help_text='Month of levy applicability')
    is_remitted = models.BooleanField(default=False)
    remitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['property', 'period_month']),
            models.Index(fields=['is_remitted']),
        ]

    def __str__(self):
        return f'{self.folio.reservation.reservation_number} — MWK {self.levy_amount}'