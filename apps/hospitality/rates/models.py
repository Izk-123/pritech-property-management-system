from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel


class RatePlan(TimeStampedModel):
    """A pricing policy for a property (flexible, non-refundable, etc.)."""

    class Policy(models.TextChoices):
        FLEXIBLE = 'FLEX', 'Flexible (Free cancellation 48h)'
        NON_REFUNDABLE = 'NONREF', 'Non-Refundable'
        BED_BREAKFAST = 'BB', 'Bed & Breakfast'
        ALL_INCLUSIVE = 'AI', 'All-Inclusive'

    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='rate_plans',
    )
    name = models.CharField(max_length=100)
    policy = models.CharField(max_length=6, choices=Policy.choices)
    deposit_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Percentage of total required as deposit at booking',
    )
    cancellation_hours = models.PositiveIntegerField(
        default=48,
        help_text='Hours before check-in within which cancellation is free',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['property', 'name']
        unique_together = [('property', 'name')]

    def __str__(self):
        return f'{self.name} ({self.get_policy_display()})'


class PricingSeason(TimeStampedModel):
    """A date range during which unit rates are overridden."""

    property = models.ForeignKey(
        'properties.Property', on_delete=models.CASCADE,
        related_name='pricing_seasons',
    )
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text='e.g., 1.50 = 50% increase over base rate',
    )
    fixed_rate_mwk = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Overrides multiplier if set',
    )

    class Meta:
        ordering = ['start_date']
        indexes = [
            models.Index(fields=['property', 'start_date', 'end_date']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F('start_date')),
                name='pricing_season_end_after_start',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.start_date} → {self.end_date})'

    def applies_to(self, date):
        return self.start_date <= date <= self.end_date

    def clean(self):
        if not self.multiplier and not self.fixed_rate_mwk:
            raise ValidationError('Set either a multiplier or a fixed rate.')