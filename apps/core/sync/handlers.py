"""
Sync handlers for offline-capable operations.

Each handler receives the queued operation and returns a result
dict. Handlers must be idempotent — the same operation may be
replayed if a network error occurred after the server processed
it but before the client received the response.

Correction (Phase 10 maintenance)
---------------------------------
Every handler used to call ``folio.recalculate_totals()``. Folio
totals are computed properties (``folio.balance``, ``folio.total_charges``,
etc. — see ``apps/hospitality/folios/models.py``) and no such method
exists. The call raised ``AttributeError`` *after* the charge or
payment row had already been committed, which meant a retry
created a duplicate row.

Two fixes applied here:

1. Removed all ``recalculate_totals()`` calls. Nothing needs to be
   recalculated — the properties recompute on every access.

2. Wrapped the row-creation in ``transaction.atomic()``. Even with
   the broken call gone, atomicity matters: the ``auditlog`` app
   has a ``post_save`` receiver on ``FolioCharge``/``FolioPayment``
   that writes a ``LogEntry`` row. If that write ever fails, the
   whole operation must roll back rather than leave an unaudited
   charge in the database.

Idempotency caveat
------------------
``handle_folio_charge`` has no key it can dedupe on — a folio can
legitimately have two charges with the same description and amount
(two identical dinners, for instance). A retried charge op therefore
creates a second row. The correct long-term fix is to have the
client generate a UUID per queued op and pass it in the payload;
until then, staff should treat the Sync Log page
(``/admin/core/synclog/``) as the source of truth when reconciling.
"""
import logging

from django.db import transaction

from .views import register_sync_handler, ConflictError


logger = logging.getLogger(__name__)


# ─── Housekeeping status update ───────────────────────────────────

def handle_housekeeping_status(op, request):
    """
    POST /api/v1/sync/housekeeping/<task_id>/status/
    {"status": "COMP"}

    Transitions a housekeeping task through its allowed state machine:
        PEND → PROG → COMP → INSP
    plus PEND → SKIP. Any other transition is a conflict.

    Idempotent: if the task is already in the requested status, the
    handler returns success without touching the row.
    """
    from apps.hospitality.housekeeping.models import HousekeepingTask

    endpoint = op['endpoint'].rstrip('/')
    parts = endpoint.split('/')
    task_id = parts[-2] if parts[-1] == 'status' else parts[-1]

    try:
        task = HousekeepingTask.objects.get(pk=task_id)
    except HousekeepingTask.DoesNotExist:
        # The task was deleted server-side (or the client is out of
        # sync). Returning success lets the client drop the op from
        # its queue rather than retry forever.
        return {'deleted': True, 'task_id': task_id}

    new_status = op['payload'].get('status')

    # Idempotency: already in this status → no-op
    if task.status == new_status:
        return {'task_id': task_id, 'status': new_status, 'duplicate': True}

    valid_transitions = {
        'PEND': ['PROG', 'SKIP'],
        'PROG': ['COMP'],
        'COMP': ['INSP'],
    }
    allowed = valid_transitions.get(task.status, [])
    if new_status not in allowed:
        # ConflictError carries the server's current state so the
        # client can show the user "someone else already changed
        # this task to X".
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

    Adds a charge to a folio. The charge is created inside
    ``transaction.atomic()`` so a failure anywhere in the write path
    (including any ``post_save`` receivers such as the audit log)
    rolls the whole thing back. Without atomicity, a failed sync
    leaves an orphaned row that a retry would duplicate.
    """
    from apps.hospitality.folios.models import Folio, FolioCharge

    endpoint = op['endpoint'].rstrip('/')
    parts = endpoint.split('/')
    folio_id = parts[-2] if parts[-1] == 'charge' else parts[-1]

    try:
        folio = Folio.objects.get(pk=folio_id)
    except Folio.DoesNotExist:
        return {'deleted': True, 'folio_id': folio_id}

    with transaction.atomic():
        charge = FolioCharge.objects.create(
            folio=folio,
            charge_type=op['payload']['charge_type'],
            description=op['payload']['description'],
            amount=op['payload']['amount'],
            currency=op['payload'].get('currency', folio.currency),
            posted_by=request.user,
        )
    # NOTE: previously the handler called folio.recalculate_totals()
    # here. That method does not exist — Folio.balance and friends
    # are @property computed on access. Do not re-add it.

    return {'folio_id': folio_id, 'charge_id': charge.pk}


# ─── Folio payment ────────────────────────────────────────────────

def handle_folio_payment(op, request):
    """
    POST /api/v1/sync/folios/<folio_id>/payment/
    {"method": "CASH_MWK", "amount": "50000", "currency": "MWK", "reference": "..."}

    Adds a payment to a folio.

    Idempotency: if the payload carries a non-empty ``reference``,
    the handler looks for an existing payment on the same folio with
    the same reference. A match means the operation was already
    applied on a previous attempt and the client just didn't get
    the response. In that case we return the existing payment's ID
    and the caller treats it as a duplicate.

    Payments without a reference (cash, typically) have no dedupe
    key. A replayed op will create a second payment row. Staff
    reconciling a folio should use the Sync Log to spot these.
    """
    from apps.hospitality.folios.models import Folio, FolioPayment

    endpoint = op['endpoint'].rstrip('/')
    parts = endpoint.split('/')
    folio_id = parts[-2] if parts[-1] == 'payment' else parts[-1]

    try:
        folio = Folio.objects.get(pk=folio_id)
    except Folio.DoesNotExist:
        return {'deleted': True, 'folio_id': folio_id}

    reference = op['payload'].get('reference', '')

    # Idempotency check outside the atomic block — this is a read,
    # and the whole point is to skip the write entirely if a
    # duplicate is detected.
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

    with transaction.atomic():
        payment = FolioPayment.objects.create(
            folio=folio,
            method=op['payload']['method'],
            amount=op['payload']['amount'],
            currency=op['payload'].get('currency', folio.currency),
            reference=reference,
            received_by=request.user,
        )
    # NOTE: no folio.recalculate_totals() call — Folio totals are
    # computed properties. Adding a call here would crash the
    # handler and orphan the payment row (see module docstring).

    return {'folio_id': folio_id, 'payment_id': payment.pk}


# Route folio operations by the last path segment — charge or payment.
# We register a single handler under /api/v1/sync/folios/ and dispatch
# inside based on the endpoint. Two registrations (one for /charge/,
# one for /payment/) would also work, but the current pattern lets
# future folio operations be added in one place.
def _route_folio_operation(op, request):
    endpoint = op['endpoint']
    if '/charge/' in endpoint:
        return handle_folio_charge(op, request)
    if '/payment/' in endpoint:
        return handle_folio_payment(op, request)
    raise ConflictError(f'Unknown folio operation: {endpoint}')


register_sync_handler('/api/v1/sync/folios/', _route_folio_operation)


# ─── Reservation check-in / check-out ─────────────────────────────

def handle_reservation_status(op, request):
    """
    POST /api/v1/sync/reservations/<reservation_id>/status/
    {"status": "CHIN", "unit_id": 42, "rate": "50000"}

    Transitions a reservation to CHIN (checked-in) or CHOUT
    (checked-out). The heavy lifting lives in
    ``apps.hospitality.reservations.services`` — this handler is a
    thin wrapper that maps the offline operation onto the same
    service functions used by the online views.

    Idempotency: if the reservation is already in the target state,
    the handler returns success without re-running the service.
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
            raise ConflictError(
                str(e), server_state={'status': reservation.status},
            )

    elif new_status == 'CHOUT':
        if reservation.status == Reservation.Status.CHECKED_OUT:
            return {'reservation_id': reservation_id, 'already_checked_out': True}

        try:
            check_out_reservation(reservation, user=request.user)
        except CheckInError as e:
            raise ConflictError(
                str(e), server_state={'status': reservation.status},
            )

    return {'reservation_id': reservation_id, 'status': new_status}


register_sync_handler('/api/v1/sync/reservations/', handle_reservation_status)


# ─── EIS offline invoice ──────────────────────────────────────────

def handle_eis_offline_invoice(op, request):
    """
    POST /api/v1/sync/eis/invoices/
    {"folio_id": 42, "invoice_number": "...", "offline_hmac": "...", "property_id": 1}

    Queues an MRA EIS invoice that was generated while offline. The
    invoice log row is created here; a Celery task picks it up and
    submits it to MRA.

    Idempotency: ``invoice_number`` is unique on ``EISInvoiceLog``,
    so a replayed op hits ``get_or_create``'s "found existing" path
    and returns without a duplicate.
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
        # Already in the queue (or already submitted). Drop the op
        # from the client's queue — no need to retry.
        return {'invoice_number': payload['invoice_number'], 'duplicate': True}

    # Trigger the submission task. It runs in the background so the
    # sync response returns immediately; MRA may be slow or down.
    from apps.compliance.eis.tasks import sync_offline_eis_invoices
    sync_offline_eis_invoices.delay()

    return {'invoice_number': payload['invoice_number'], 'queued': True}


register_sync_handler('/api/v1/sync/eis/', handle_eis_offline_invoice)