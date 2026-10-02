"""
Celery tasks for bulk PDF generation.

Each task iterates over a queryset, renders each document, and
optionally saves the result as a Document record or emails it.
"""
import logging

from celery import shared_task
from django_tenants.utils import schema_context

from apps.shared.tenants.models import Tenant

logger = logging.getLogger(__name__)


@shared_task
def bulk_render_rent_invoices(invoice_ids):
    """
    Render a batch of rent invoices. Returns a list of (id, byte length)
    for verification; the caller usually then emails or uploads them.
    """
    from apps.property.rent_invoicing.models import RentInvoice
    from .rent_invoice import render_rent_invoice

    results = []
    for invoice in RentInvoice.objects.filter(id__in=invoice_ids):
        try:
            pdf = render_rent_invoice(invoice)
            results.append((invoice.id, len(pdf)))
        except Exception as exc:
            logger.exception(f'Failed to render invoice {invoice.id}: {exc}')
            results.append((invoice.id, 0))
    return results


@shared_task
def generate_monthly_statements_for_all_tenants():
    """
    Runs on the 1st of each month at 05:00. Iterates every tenant,
    enters their schema, and generates landlord statements for each
    property.
    """
    tenants = Tenant.objects.filter(is_active=True).exclude(
        schema_name='public',
    )
    total = 0

    for tenant in tenants:
        with schema_context(tenant.schema_name):
            try:
                from apps.core.properties.models import Property
                from .statements import render_landlord_statement
                from django.utils import timezone
                from datetime import timedelta

                last_month_end = timezone.now().date().replace(day=1) - timedelta(days=1)
                last_month_start = last_month_end.replace(day=1)

                for prop in Property.objects.filter(status='ACTIVE'):
                    try:
                        pdf = render_landlord_statement(prop, last_month_start, last_month_end)
                        total += 1
                        # Optionally: save as Document record or email to landlord
                    except Exception as exc:
                        logger.exception(
                            f'Statement failed for {prop.name}: {exc}'
                        )
            except Exception as exc:
                logger.exception(
                    f'Monthly statements failed for tenant {tenant.schema_name}: {exc}'
                )

    return f'Generated {total} landlord statements'