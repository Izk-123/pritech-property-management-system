import logging
from django.core.management import call_command
from django.db import transaction
from django_tenants.utils import schema_context
from .models import Tenant, Domain


logger = logging.getLogger(__name__)


@transaction.atomic
def provision_tenant(name, schema_name, domain_name, plan='STARTER',
                     admin_email=None, admin_password=None,
                     contact_name='', contact_email='', contact_phone=''):
    """
    Provision a new tenant with schema, domain, and optional admin user.

    Args:
        name: Human-readable tenant name
        schema_name: PostgreSQL schema name (lowercase, no spaces)
        domain_name: Full subdomain (e.g., lakeview.pms.pritechmw.com)
        plan: Subscription plan
        admin_email: Email for the tenant admin user
        admin_password: Password for the tenant admin user

    Returns:
        Tenant instance
    """
    # Create the tenant (schema auto-created by django-tenants)
    tenant = Tenant.objects.create(
        name=name,
        schema_name=schema_name,
        plan=plan,
        on_trial=True,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
    )

    # Map the domain
    Domain.objects.create(
        domain=domain_name,
        tenant=tenant,
        is_primary=True,
    )

    # Ensure migrations run against the new schema
    call_command(
        'migrate_schemas',
        schema_name=schema_name,
        interactive=False,
        verbosity=0,
    )

    # Create admin user inside the tenant schema (optional)
    # Note: since User lives in the public schema, we create it there
    if admin_email and admin_password:
        from apps.shared.users.models import User

        User.objects.create_user(
            username=admin_email,
            email=admin_email,
            password=admin_password,
            is_staff=True,
            is_superuser=False,
            is_platform_admin=False,
        )

    logger.info(f'Provisioned tenant {schema_name} at {domain_name}')
    return tenant


@transaction.atomic
def deprovision_tenant(tenant, drop_schema=False):
    """
    Deactivate a tenant. Optionally drop the schema.

    By default, the schema is preserved for data recovery.
    Dropping the schema is a destructive, irreversible action.
    """
    tenant.is_active = False
    tenant.save(update_fields=['is_active'])

    if drop_schema:
        tenant.auto_drop_schema = True
        tenant.delete(force_drop=True)
        logger.warning(f'Dropped schema for tenant {tenant.schema_name}')
    else:
        logger.info(f'Deactivated tenant {tenant.schema_name}')

    return tenant


@transaction.atomic
def reactivate_tenant(tenant):
    """Reactivate a suspended tenant."""
    tenant.is_active = True
    tenant.save(update_fields=['is_active'])
    logger.info(f'Reactivated tenant {tenant.schema_name}')
    return tenant