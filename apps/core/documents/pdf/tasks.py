"""Celery tasks for bulk PDF generation."""
import logging

from celery import shared_task
from django_tenants.utils import schema_context

from apps.shared.tenants.models import Tenant

logger = logging.getLogger(__name__)


@shared_task
def generate_monthly_statements_for_all_tenants():
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

                last_month_end = (
                    timezone.now().date().replace(day=1)
                    - timedelta(days=1)
                )
                last_month_start = last_month_end.replace(day=1)

                for prop in Property.objects.filter(status='ACTIVE'):
                    try:
                        render_landlord_statement(
                            prop, last_month_start, last_month_end,
                        )
                        total += 1
                    except Exception as exc:
                        logger.exception(
                            f'Statement failed for {prop.name}: {exc}'
                        )
            except Exception as exc:
                logger.exception(
                    f'Statements failed for tenant '
                    f'{tenant.schema_name}: {exc}'
                )

    return f'Generated {total} landlord statements'