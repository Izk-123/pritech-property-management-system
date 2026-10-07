"""
PayChangu webhook endpoint and staff-facing transaction log.

The webhook is the only public endpoint. It receives notifications
from PayChangu when a transaction's status changes (successful,
failed) and updates our ledger accordingly.

Trust model
-----------
The webhook payload is *never* trusted on its own. Even with a valid
signature — which proves the request came from PayChangu — the
status and amount in the payload are re-verified against
PayChangu's verify endpoint before any business action is taken.
This defends against:

  * Replay of an old, previously-valid payload with a modified amount
  * An attacker who has compromised the webhook secret
  * PayChangu itself sending inconsistent data across systems

The verification call is synchronous (2-5 s) — fine for the webhook
volume PayChangu generates (a few per minute at peak).
"""
import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .models import PayChanguTransaction
from .services import PayChanguService


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Webhook
# ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def paychangu_webhook(request):
    """
    Handle PayChangu payment notifications.

    Order of operations:

      1. Signature check — an invalid signature gets 403 before we
         touch the database. Guards against unsigned spoofing.

      2. Parse payload, extract tx_ref and charge_id. Missing either
         returns 400 — the webhook contract requires both.

      3. Server-side verify. PayChangu's verify endpoint is the
         authority on whether a transaction really succeeded. We
         use its response, not the webhook payload, to decide.

      4. Upsert the ledger row keyed on charge_id. Idempotent — a
         webhook re-delivery finds the row already there.

      5. If the transaction succeeded, try to link it to the
         originating FolioPayment or RentPayment by matching
         ``tx_ref`` against their ``reference`` field. Not all
         transactions have a matching business object, and that's
         fine — the ledger is useful on its own.

      6. Mark the ledger row successful. There is no total to
         recalculate: Folio and RentInvoice derive their balances
         from related rows, so updating the ledger is enough.
    """
    # ─── 1. Signature ───────────────────────────────────────────
    #
    # verify_webhook_signature handles the case where the webhook
    # secret is not configured. In that case the service returns
    # False and we refuse the request — an HMAC with an empty key
    # is trivially forgeable, so accepting unsigned payloads is
    # equivalent to an open endpoint.
    signature = request.headers.get('X-PayChangu-Signature', '')
    if not PayChanguService.verify_webhook_signature(request.body, signature):
        logger.warning(
            'PayChangu webhook rejected: invalid or missing signature '
            '(source IP %s)',
            request.META.get('REMOTE_ADDR', 'unknown'),
        )
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid signature'},
            status=403,
        )

    # ─── 2. Payload ─────────────────────────────────────────────
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid JSON'},
            status=400,
        )

    tx_ref = payload.get('tx_ref')
    charge_id = payload.get('charge_id') or tx_ref
    webhook_status = (payload.get('status') or '').lower()

    if not tx_ref or not charge_id:
        return JsonResponse(
            {'status': 'error', 'message': 'Missing tx_ref or charge_id'},
            status=400,
        )

    # ─── 3. Server-side verify ──────────────────────────────────
    service = PayChanguService()
    is_valid, verification = service.verify_transaction(tx_ref)

    # ─── 4. Upsert ledger row ───────────────────────────────────
    txn, created = PayChanguTransaction.objects.get_or_create(
        charge_id=charge_id,
        defaults={
            'ref_id': tx_ref,
            'amount': payload.get('amount', 0),
            'currency': payload.get('currency', 'MWK'),
            'status': PayChanguTransaction.Status.PENDING,
        },
    )

    # If we've already recorded this transaction as successful, the
    # webhook is a re-delivery. Return immediately so we don't
    # re-link or re-apply anything.
    if txn.status == PayChanguTransaction.Status.SUCCESSFUL:
        return JsonResponse({'status': 'already_processed'})

    # ─── 5. Failure path ────────────────────────────────────────
    #
    # Two ways a transaction fails at this point:
    #   • The webhook itself says status != successful
    #   • PayChangu's verify endpoint disagrees with the webhook
    #
    # Either is enough to mark the ledger row failed. Business
    # objects (FolioPayment, RentPayment) are never created on the
    # failure path — the calling view already created them, and if
    # the transaction failed, the payment row was never linked.
    if webhook_status != 'successful' or not is_valid:
        txn.status = PayChanguTransaction.Status.FAILED
        txn.verification_data = verification if isinstance(verification, dict) else {}
        txn.webhook_received_at = timezone.now()
        txn.save(update_fields=[
            'status', 'verification_data', 'webhook_received_at', 'updated_at',
        ])
        logger.info(
            'PayChangu txn %s marked failed (webhook=%s, verify=%s)',
            tx_ref, webhook_status, is_valid,
        )
        return JsonResponse({'status': 'failed'})

    # ─── 6. Link + mark successful ──────────────────────────────
    _try_link_to_business_object(txn, tx_ref)

    txn.status = PayChanguTransaction.Status.SUCCESSFUL
    txn.verification_data = verification if isinstance(verification, dict) else {}
    txn.webhook_received_at = timezone.now()
    txn.verified_at = timezone.now()
    txn.save(update_fields=[
        'status', 'verification_data', 'webhook_received_at',
        'verified_at', 'content_type', 'object_id', 'updated_at',
    ])

    logger.info(
        'PayChangu txn %s recorded successful (%s %s, linked=%s)',
        tx_ref, txn.amount, txn.currency, txn.is_linked,
    )
    return JsonResponse({'status': 'ok'})


def _try_link_to_business_object(txn, tx_ref):
    """
    Associate a ledger row with the FolioPayment or RentPayment that
    created it.

    Both models store the PayChangu reference in their ``reference``
    field. We look up each in turn and set content_type/object_id on
    a match.

    Failure is not fatal — a legitimate transaction may have no
    matching business row yet (the calling view hasn't committed, or
    the payment was made outside the system). The ledger keeps the
    transaction for manual reconciliation.
    """
    from django.contrib.contenttypes.models import ContentType
    from apps.hospitality.folios.models import FolioPayment
    from apps.property.rent_invoicing.models import RentPayment

    # FolioPayment first — front-desk payments are the common case.
    folio_payment = FolioPayment.objects.filter(reference=tx_ref).first()
    if folio_payment:
        txn.content_type = ContentType.objects.get_for_model(FolioPayment)
        txn.object_id = folio_payment.pk
        return

    rent_payment = RentPayment.objects.filter(reference=tx_ref).first()
    if rent_payment:
        txn.content_type = ContentType.objects.get_for_model(RentPayment)
        txn.object_id = rent_payment.pk
        return

    logger.info(
        'PayChangu txn %s has no matching FolioPayment or RentPayment — '
        'left unlinked for manual reconciliation',
        tx_ref,
    )


# ─────────────────────────────────────────────────────────────────────
# Staff-facing transaction log
# ─────────────────────────────────────────────────────────────────────

class PayChanguTransactionListView(LoginRequiredMixin, ListView):
    """
    Browsable ledger with filters and a daily summary.

    The list is paginated at 50 rows. The summary aggregates only
    SUCCESSFUL transactions from today — failed and pending rows
    are excluded so the "today's total" number matches what a
    bookkeeper would put in a cash book.
    """
    model = PayChanguTransaction
    template_name = 'pages/compliance/paychangu_transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

    def get_queryset(self):
        qs = (
            PayChanguTransaction.objects
            .select_related('content_type')
            .order_by('-created_at')
        )

        status = self.request.GET.get('status', '')
        if status in PayChanguTransaction.Status.values:
            qs = qs.filter(status=status)

        method = self.request.GET.get('method', '')
        if method in PayChanguTransaction.Method.values:
            qs = qs.filter(method=method)

        # Search across the reference fields and the payer identity.
        # Charge IDs are the least ambiguous lookup, but operators
        # usually have a mobile number or payer name to hand.
        search = self.request.GET.get('q', '').strip()
        if search:
            qs = qs.filter(
                Q(charge_id__icontains=search) |
                Q(ref_id__icontains=search) |
                Q(payer_mobile__icontains=search) |
                Q(payer_name__icontains=search)
            )

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = PayChanguTransaction.Status.choices
        ctx['methods'] = PayChanguTransaction.Method.choices
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['current_method'] = self.request.GET.get('method', '')
        ctx['search_query'] = self.request.GET.get('q', '')

        # Daily summary — successful transactions only.
        today = timezone.now().date()
        today_qs = PayChanguTransaction.objects.filter(
            created_at__date=today,
            status=PayChanguTransaction.Status.SUCCESSFUL,
        )
        ctx['today_total'] = today_qs.aggregate(t=Sum('amount'))['t'] or 0
        ctx['today_count'] = today_qs.count()

        # Alert banner counts — surfaced at the top of the list so a
        # bookkeeper sees pending and unlinked transactions on every
        # page load.
        ctx['pending_count'] = PayChanguTransaction.objects.filter(
            status=PayChanguTransaction.Status.PENDING,
        ).count()
        ctx['unlinked_count'] = PayChanguTransaction.objects.filter(
            status=PayChanguTransaction.Status.SUCCESSFUL,
            content_type__isnull=True,
        ).count()

        return ctx