"""
Tenant provisioning services.

``provision_tenant`` is the single entry point used by:
  • The platform-admin Create Tenant view
  • The public email-signup flow
  • The Google-signup completion flow (Phase 9.1)

It creates the Tenant row, the Domain mapping, runs migrations
against the new schema, and — when credentials are supplied —
creates and registers an admin User.
"""
import logging

from django.core.management import call_command
from django.db import transaction

from .models import Tenant, Domain


logger = logging.getLogger(__name__)


@transaction.atomic
def provision_tenant(
    name,
    schema_name,
    domain_name,
    plan='STARTER',
    admin_email=None,
    admin_password=None,
    contact_name='',
    contact_email='',
    contact_phone='',
    modules=None,
):
    """
    Provision a new tenant with schema, domain, and optional admin user.

    Args:
        name:             Human-readable tenant name (e.g. "Lakeview Lodge")
        schema_name:      PostgreSQL schema name (lowercase, no spaces)
        domain_name:      Full subdomain (e.g. "lakeview.pms.pritechmw.com")
        plan:             Subscription plan choice
        admin_email:      Email for a new tenant-admin User. Omit when
                          the caller is already authenticated (Google flow).
        admin_password:   Password for that User. Omit with admin_email=None.
        contact_name:     Display name shown on invoices / headers
        contact_email:    Primary contact
        contact_phone:    Malawi mobile in E.164 (e.g. "+265991234567")
        modules:          List of Tenant.Module values

    Returns:
        The created Tenant instance.
    """
    # Create the tenant — django-tenants auto-creates the schema
    tenant = Tenant.objects.create(
        name=name,
        schema_name=schema_name,
        plan=plan,
        on_trial=True,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        modules=modules or [],
    )

    # Map the domain
    Domain.objects.create(
        domain=domain_name,
        tenant=tenant,
        is_primary=True,
    )

    # Run migrations against the new schema
    call_command(
        'migrate_schemas',
        schema_name=schema_name,
        interactive=False,
        verbosity=0,
    )

    # Create the tenant admin user (optional — omit for Google flow)
    if admin_email and admin_password:
        from apps.shared.users.models import User
        from allauth.account.models import EmailAddress

        user = User.objects.create_user(
            username=admin_email,
            email=admin_email,
            password=admin_password,
            is_staff=True,
            is_superuser=False,
            is_platform_admin=False,
        )

        # Register the email with allauth so account management works
        EmailAddress.objects.get_or_create(
            user=user,
            email=admin_email,
            defaults={'primary': True, 'verified': False},
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