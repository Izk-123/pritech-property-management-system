"""
Broadcast model changes to WebSocket groups.

Every handler derives the tenant group from the instance's tenant
schema and sends a JSON payload to the channel layer, which fans
out to every connected consumer.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .utils import broadcast_to_tenant, current_tenant_schema

logger = logging.getLogger(__name__)


# ─── Reservation created or status changed ─────────────────────────
@receiver(post_save, sender='reservations.Reservation')
def on_reservation_change(sender, instance, created, **kwargs):
    schema = current_tenant_schema()
    if not schema:
        return

    event = 'created' if created else 'updated'
    broadcast_to_tenant(
        'frontdesk',
        'frontdesk_update',
        {
            'event': f'reservation_{event}',
            'id': instance.pk,
            'reservation_number': instance.reservation_number,
            'guest_id': instance.primary_guest_id,
            'status': instance.status,
            'check_in': instance.check_in.isoformat() if instance.check_in else None,
            'check_out': instance.check_out.isoformat() if instance.check_out else None,
            'property_id': instance.property_id,
        },
        schema=schema,
    )


# ─── Folio payment ──────────────────────────────────────────────────
@receiver(post_save, sender='folios.FolioPayment')
def on_folio_payment(sender, instance, created, **kwargs):
    if not created:
        return
    schema = current_tenant_schema()
    if not schema:
        return

    folio = instance.folio
    reservation = folio.reservation

    # Broadcast to the front desk board
    broadcast_to_tenant(
        'frontdesk',
        'frontdesk_update',
        {
            'event': 'payment_received',
            'folio_id': folio.pk,
            'reservation_id': reservation.pk,
            'amount': str(instance.amount),
            'currency': instance.currency,
            'method': instance.method,
            'balance': str(folio.balance),
            'guest_id': reservation.primary_guest_id,
        },
        schema=schema,
    )

    # Personal notification to the guest-facing staff member
    # who posted the payment
    if instance.received_by_id:
        broadcast_to_tenant(
            f'user_{instance.received_by_id}',
            'notify',
            {
                'type': 'success',
                'title': 'Payment recorded',
                'message': (
                    f'{instance.currency} {instance.amount} '
                    f'from {reservation.primary_guest.full_name}'
                ),
                'url': f'/reservations/{reservation.pk}/',
            },
            schema=schema,
        )

    # Queue the guest WhatsApp receipt
    try:
        from apps.communications.tasks import send_payment_receipt
        send_payment_receipt.delay(instance.pk)
    except Exception:
        logger.exception('Could not queue payment receipt task')


# ─── Folio charge ───────────────────────────────────────────────────
@receiver(post_save, sender='folios.FolioCharge')
def on_folio_charge(sender, instance, created, **kwargs):
    if not created:
        return
    schema = current_tenant_schema()
    if not schema:
        return

    folio = instance.folio
    broadcast_to_tenant(
        'frontdesk',
        'frontdesk_update',
        {
            'event': 'charge_posted',
            'folio_id': folio.pk,
            'reservation_id': folio.reservation_id,
            'amount': str(instance.amount),
            'currency': instance.currency,
            'charge_type': instance.charge_type,
            'balance': str(folio.balance),
        },
        schema=schema,
    )


# ─── Housekeeping task ─────────────────────────────────────────────
@receiver(post_save, sender='housekeeping.HousekeepingTask')
def on_housekeeping_change(sender, instance, created, **kwargs):
    schema = current_tenant_schema()
    if not schema:
        return

    broadcast_to_tenant(
        'rooms',
        'room_update',
        {
            'event': 'task_created' if created else 'task_updated',
            'task_id': instance.pk,
            'unit_id': instance.unit_id,
            'unit_identifier': instance.unit.identifier,
            'task_status': instance.status,
            'unit_status': instance.unit.status,
            'priority': instance.priority,
            'assigned_to': instance.assigned_to_id,
        },
        schema=schema,
    )

    # Notify the assigned housekeeper directly
    if instance.assigned_to_id and created:
        broadcast_to_tenant(
            f'user_{instance.assigned_to_id}',
            'notify',
            {
                'type': 'info',
                'title': 'New task assigned',
                'message': f'{instance.get_task_type_display()} — {instance.unit.identifier}',
                'url': '/housekeeping/tasks/',
            },
            schema=schema,
        )


# ─── Unit status ───────────────────────────────────────────────────
@receiver(post_save, sender='properties.Unit')
def on_unit_status_change(sender, instance, created, **kwargs):
    if created:
        return
    schema = current_tenant_schema()
    if not schema:
        return

    broadcast_to_tenant(
        'rooms',
        'room_update',
        {
            'event': 'unit_status_changed',
            'unit_id': instance.pk,
            'unit_identifier': instance.identifier,
            'unit_status': instance.status,
            'property_id': instance.property_id,
        },
        schema=schema,
    )


# ─── Lease status change ───────────────────────────────────────────
@receiver(post_save, sender='leases.Lease')
def on_lease_change(sender, instance, created, **kwargs):
    schema = current_tenant_schema()
    if not schema:
        return

    broadcast_to_tenant(
        'property',
        'property_update',
        {
            'event': 'lease_created' if created else 'lease_updated',
            'lease_id': instance.pk,
            'lease_number': instance.lease_number,
            'tenant_id': instance.tenant_id,
            'unit_id': instance.unit_id,
            'status': instance.status,
            'end_date': instance.end_date.isoformat() if instance.end_date else None,
        },
        schema=schema,
    )


# ─── Rent invoice issued ───────────────────────────────────────────
@receiver(post_save, sender='rent_invoicing.RentInvoice')
def on_rent_invoice_change(sender, instance, created, **kwargs):
    schema = current_tenant_schema()
    if not schema:
        return

    # Only broadcast on meaningful transitions
    if created and instance.status in ('DRAFT', 'ISSUED'):
        event = 'invoice_issued'
    elif instance.status == 'PAID':
        event = 'invoice_paid'
    elif instance.status == 'OVERDUE':
        event = 'invoice_overdue'
    else:
        return

    broadcast_to_tenant(
        'property',
        'property_update',
        {
            'event': event,
            'invoice_id': instance.pk,
            'invoice_number': instance.invoice_number,
            'tenant_id': instance.tenant_id,
            'unit_id': instance.unit_id,
            'total_due': str(instance.total_due),
            'balance': str(instance.balance),
            'status': instance.status,
            'due_date': instance.due_date.isoformat(),
        },
        schema=schema,
    )