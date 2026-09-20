import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.db.models import Q, Sum
from .models import PayChanguTransaction
from .services import PayChanguService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def paychangu_webhook(request):
    """
    Handle PayChangu payment notifications.
    Verify signature, then update the linked payment record.
    """
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    signature = request.headers.get('X-PayChangu-Signature', '')
    if not PayChanguService.verify_webhook_signature(
        request.body.decode(), signature
    ):
        logger.warning('Invalid PayChangu webhook signature')
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid signature'}, status=403,
        )

    tx_ref = payload.get('tx_ref')
    status = payload.get('status')
    charge_id = payload.get('charge_id', tx_ref)

    txn, created = PayChanguTransaction.objects.get_or_create(
        charge_id=charge_id,
        defaults={
            'ref_id': tx_ref,
            'amount': payload.get('amount', 0),
            'currency': payload.get('currency', 'MWK'),
            'status': PayChanguTransaction.Status.PENDING,
        },
    )

    if not created and txn.status == PayChanguTransaction.Status.SUCCESSFUL:
        return JsonResponse({'status': 'already_processed'})

    if status == 'successful':
        service = PayChanguService()
        is_valid, verification = service.verify_transaction(tx_ref)

        if is_valid:
            txn.status = PayChanguTransaction.Status.SUCCESSFUL
            txn.verification_data = verification
            txn.webhook_received_at = timezone.now()
            txn.verified_at = timezone.now()
            txn.save()
            _apply_payment(txn)
        else:
            txn.status = PayChanguTransaction.Status.FAILED
            txn.save()

    return JsonResponse({'status': 'ok'})


def _apply_payment(txn):
    """Apply a successful payment to the linked folio or invoice."""
    obj = txn.content_object
    if obj is None:
        return

    if hasattr(obj, 'folio'):
        obj.folio.recalculate_totals()
    elif hasattr(obj, 'invoice'):
        obj.invoice.recalculate_totals()


class PayChanguTransactionListView(LoginRequiredMixin, ListView):
    model = PayChanguTransaction
    template_name = 'pages/compliance/paychangu_transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

    def get_queryset(self):
        qs = PayChanguTransaction.objects.order_by('-created_at')

        status = self.request.GET.get('status', '')
        if status in PayChanguTransaction.Status.values:
            qs = qs.filter(status=status)

        method = self.request.GET.get('method', '')
        if method in PayChanguTransaction.Method.values:
            qs = qs.filter(method=method)

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

        # Today's summary
        today = timezone.now().date()
        today_qs = PayChanguTransaction.objects.filter(
            created_at__date=today,
            status=PayChanguTransaction.Status.SUCCESSFUL,
        )
        ctx['today_total'] = today_qs.aggregate(t=Sum('amount'))['t'] or 0
        ctx['today_count'] = today_qs.count()
        return ctx