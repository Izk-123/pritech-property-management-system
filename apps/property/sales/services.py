from django.db import transaction
from django.core.exceptions import ValidationError
from .models import SaleListing, SaleOffer, SaleAgreement, SaleInstallment, SaleCommission


class SaleError(ValidationError):
    pass


@transaction.atomic
def accept_offer(offer, user=None):
    """
    Accept an offer: mark it ACCEPTED, reject all other offers on the listing,
    move the listing to UNDER_OFFER.
    """
    if offer.status != SaleOffer.Status.PENDING:
        raise SaleError('Only pending offers can be accepted.')

    listing = offer.listing
    if listing.status != SaleListing.Status.LISTED:
        raise SaleError('Listing is not available for offers.')

    # Reject all other pending offers
    listing.offers.filter(
        status=SaleOffer.Status.PENDING
    ).exclude(pk=offer.pk).update(status=SaleOffer.Status.REJECTED)

    offer.status = SaleOffer.Status.ACCEPTED
    offer.save(update_fields=['status', 'updated_at'])

    listing.status = SaleListing.Status.UNDER_OFFER
    listing.save(update_fields=['status', 'updated_at'])

    return offer


@transaction.atomic
def create_sale_agreement(offer, deposit_amount, payment_type,
                          completion_date, installment_count=1, user=None):
    """
    Create a sale agreement from an accepted offer.
    If payment_type is INSTALLMENT, generate the installment schedule.
    """
    if offer.status != SaleOffer.Status.ACCEPTED:
        raise SaleError('Only accepted offers can become agreements.')

    listing = offer.listing
    agreement = SaleAgreement.objects.create(
        listing=listing,
        buyer=offer.buyer,
        seller=listing.agent,  # Placeholder; seller is set separately
        sale_price=offer.offer_amount,
        currency=offer.currency,
        deposit_amount=deposit_amount,
        payment_type=payment_type,
        completion_date=completion_date,
    )

    listing.status = SaleListing.Status.AGREEMENT
    listing.save(update_fields=['status', 'updated_at'])

    # Generate installment schedule
    if payment_type == SaleAgreement.PaymentType.INSTALLMENT:
        balance = agreement.sale_price - deposit_amount
        per_installment = balance / installment_count
        from datetime import date
        for i in range(1, installment_count + 1):
            due = date(
                completion_date.year,
                completion_date.month,
                min(28, completion_date.day),
            )
            SaleInstallment.objects.create(
                agreement=agreement,
                installment_number=i,
                due_date=due,
                amount=per_installment,
            )

    # Calculate commissions
    calculate_commissions(agreement)

    return agreement


def calculate_commissions(agreement, agency_percent=5):
    """Split commission among agents on the listing."""
    total_commission = agreement.sale_price * (agency_percent / 100)

    # MVP: single agent gets the full commission
    agent = agreement.listing.agent
    if agent:
        SaleCommission.objects.get_or_create(
            agreement=agreement,
            agent=agent,
            defaults={
                'commission_percent': agency_percent,
                'commission_amount': total_commission,
            },
        )


@transaction.atomic
def complete_sale(agreement, user=None):
    """Mark a sale as completed: move listing to COMPLETED, unit to SOLD."""
    agreement.listing.status = SaleListing.Status.COMPLETED
    agreement.listing.save(update_fields=['status', 'updated_at'])

    if agreement.listing.unit:
        unit = agreement.listing.unit
        unit.status = 'SOLD'
        unit.save(update_fields=['status', 'updated_at'])

    return agreement