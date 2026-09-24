"""
Sync handlers for offline-capable operations.

Each handler receives the queued operation and returns a result
dict. Handlers must be idempotent — the same operation may be
replayed if a network error occurred after the server processed
it but before the client received the response.
"""
import logging

from .views import register_sync_handler, ConflictError

logger = logging.getLogger(__name__)


# ─── Housekeeping status update ───────────────────────────────────
def handle_housekeeping_status(op, request):
    """
    POST /api/v1/sync/housekeeping/<task_id>/status/
    {"status": "COMP"}
    """
    from apps.hospitality.housekeeping.models import HousekeepingTask

    endpoint = op['endpoint'].rstrip('/')
    parts = endpoint.split('/')
    task_id = parts[-2] if parts[-1] == 'status' else parts[-1]

    try:
        task = HousekeepingTask.objects.get(pk=task_id)
    except HousekeepingTask.DoesNotExist:
        return {'deleted': True, 'task_id': task_id}

    new_status = op['payload'].get('status')

    # Idempotency: already in this status
    if task.status == new_status:
        return {'task_id': task_id, 'status': new_status, 'duplicate': True}

    valid_transitions = {
        'PEND': ['PROG', 'SKIP'],
        'PROG': ['COMP'],
        'COMP': ['INSP'],
    }
    allowed = valid_transitions.get(task.status, [])
    if new_status not in allowed:
        raise ConflictError(
            f'Cannot transition task {task_id} from {task.status} to {new_status}',
            server_state={'status': task.status},
        )

    task.status = new_status
    if new_status == 'INSP':
        task.inspected_by = request.user
    task.save()

    return {'task_id': task_id, 'status': new_status}


register_sync_handler('/api/v1/sync/housekeeping/', handle_housekeeping_status)


# ─── Folio charge ─────────────────────────────────────────────────
def handle_folio_charge(op, request):
    """
    POST /api/v1/sync/folios/<folio_id>/charge/
    {"charge_type": "FNB", "description": "...", "amount": "15000", "currency": "MWK"}
    """
    from apps.hospitality.folios.models import Folio, FolioCharge

    endpoint = op['endpoint'].rstrip('/')
    parts = endpoint.split('/')
    folio_id = parts[-2] if parts[-1] == 'charge' else parts[-1]

    try:
        folio = Folio.objects.get(pk=folio_id)
    except Folio.DoesNotExist:
        return {'deleted': True, 'folio_id': folio_id}

    charge = FolioCharge.objects.create(
        folio=folio,
        charge_type=op['payload']['charge_type'],
        description=op['payload']['description'],
        amount=op['payload']['amount'],
        currency=op['payload'].get('currency', folio.currency),
        posted_by=request.user,
    )
    folio.recalculate_totals()

    return {'folio_id': folio_id, 'charge_id': charge.pk}


# ─── Folio payment ────────────────────────────────────────────────
def handle_folio_payment(op, request):
    """
    POST /api/v1/sync/folios/<folio_id>/payment/
    {"method": "CASH_MWK", "amount": "50000", "currency": "MWK", "reference": "..."}
    """
    from apps.hospitality.folios.models import Folio, FolioPayment

    endpoint = op['endpoint'].rstrip('/')
    parts = endpoint.split('/')
    folio_id = parts[-2] if parts[-1] == 'payment' else parts[-1]

    try:
        folio = Folio.objects.get(pk=folio_id)
    except Folio.DoesNotExist:
        return {'deleted': True, 'folio_id': folio_id}

    # Idempotency: check for an identical payment by reference
    reference = op['payload'].get('reference', '')
    if reference:
        existing = FolioPayment.objects.filter(
            folio=folio, reference=reference,
        ).first()
        if existing:
            return {
                'folio_id': folio_id,
                'payment_id': existing.pk,
                'duplicate': True,
            }

    payment = FolioPayment.objects.create(
        folio=folio,
        method=op['payload']['method'],
        amount=op['payload']['amount'],
        currency=op['payload'].get('currency', folio.currency),
        reference=reference,
        received_by=request.user,
    )
    folio.recalculate_totals()

    return {'folio_id': folio_id, 'payment_id': payment.pk}


# Route folio operations by the last path segment — charge or payment.
# We register a single handler under /api/v1/sync/folios/ and dispatch inside.
def _route_folio_operation(op, request):
    endpoint = op['endpoint']
    if '/charge/' in endpoint:
        return handle_folio_charge(op, request)
    elif '/payment/' in endpoint:
        return handle_folio_payment(op, request)
    raise ConflictError(f'Unknown folio operation: {endpoint}')


register_sync_handler('/api/v1/sync/folios/', _route_folio_operation)


# ─── Reservation check-in / check-out ─────────────────────────────
def handle_reservation_status(op, request):
    """
    POST /api/v1/sync/reservations/<reservation_id>/status/
    {"status": "CHIN", "unit_id": 42, "rate": "50000"}
    """
    from apps.hospitality.reservations.models import Reservation
    from apps.hospitality.reservations.services import (
        check_in_reservation, check_out_reservation, CheckInError,
    )

    endpoint = op['endpoint'].rstrip('/')
    parts = endpoint.split('/')
    reservation_id = parts[-2] if parts[-1] == 'status' else parts[-1]

    try:
        reservation = Reservation.objects.get(pk=reservation_id)
    except Reservation.DoesNotExist:
        return {'deleted': True, 'reservation_id': reservation_id}

    new_status = op['payload'].get('status')

    if new_status == 'CHIN':
        if reservation.status == Reservation.Status.CHECKED_IN:
            return {'reservation_id': reservation_id, 'already_checked_in': True}

        from apps.core.properties.models import Unit
        unit = Unit.objects.get(pk=op['payload']['unit_id'])

        try:
            check_in_reservation(
                reservation=reservation,
                unit_assignments=[{
                    'unit': unit,
                    'rate': op['payload']['rate'],
                }],
                user=request.user,
            )
        except CheckInError as e:
            raise ConflictError(str(e), server_state={'status': reservation.status})

    elif new_status == 'CHOUT':
        if reservation.status == Reservation.Status.CHECKED_OUT:
            return {'reservation_id': reservation_id, 'already_checked_out': True}

        try:
            check_out_reservation(reservation, user=request.user)
        except CheckInError as e:
            raise ConflictError(str(e), server_state={'status': reservation.status})

    return {'reservation_id': reservation_id, 'status': new_status}


register_sync_handler('/api/v1/sync/reservations/', handle_reservation_status)


# ─── EIS offline invoice ──────────────────────────────────────────
def handle_eis_offline_invoice(op, request):
    """
    POST /api/v1/sync/eis/invoices/
    {"folio_id": 42, "invoice_number": "...", "offline_hmac": "...", "property_id": 1}
    """
    from apps.compliance.eis.models import EISInvoiceLog, EISTerminal

    payload = op['payload']

    terminal = EISTerminal.objects.filter(
        property_id=payload['property_id'],
    ).first()

    if not terminal:
        raise ConflictError('No EIS terminal registered for this property')

    log, created = EISInvoiceLog.objects.get_or_create(
        invoice_number=payload['invoice_number'],
        defaults={
            'terminal': terminal,
            'offline_hmac_signature': payload.get('offline_hmac', ''),
            'offline_generated_at': op['created_at'],
            'submission_status': EISInvoiceLog.SubmissionStatus.OFFLINE_QUEUED,
        },
    )

    if not created:
        return {'invoice_number': payload['invoice_number'], 'duplicate': True}

    from apps.compliance.eis.tasks import sync_offline_eis_invoices
    sync_offline_eis_invoices.delay()

    return {'invoice_number': payload['invoice_number'], 'queued': True}


register_sync_handler('/api/v1/sync/eis/', handle_eis_offline_invoice)