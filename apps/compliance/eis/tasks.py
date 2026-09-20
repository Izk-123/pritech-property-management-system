from celery import shared_task
from django.utils import timezone
from .models import EISTerminal, EISInvoiceLog
from .services import EISClient
import logging

logger = logging.getLogger(__name__)


@shared_task
def sync_all_terminal_configs():
    """Sync configuration for all active terminals. Runs daily."""
    terminals = EISTerminal.objects.filter(status=EISTerminal.Status.ACTIVE)
    synced = 0
    for terminal in terminals:
        client = EISClient(terminal)
        if client.sync_configuration():
            synced += 1
    return f'Synced {synced}/{terminals.count()} terminal configurations'


@shared_task(bind=True, max_retries=5, default_retry_delay=300)
def sync_offline_eis_invoices(self):
    """
    Push queued offline invoices to MRA EIS when connectivity is restored.
    Retries with exponential backoff on failure.
    """
    pending = EISInvoiceLog.objects.filter(
        submission_status=EISInvoiceLog.SubmissionStatus.OFFLINE_QUEUED,
    ).select_related('terminal')[:50]

    synced = 0
    failed = 0

    for log in pending:
        client = EISClient(log.terminal)
        invoice_data = log.mra_response_data.get('payload', {})

        success, response = client.submit_invoice(invoice_data)

        if success:
            log.submission_status = EISInvoiceLog.SubmissionStatus.VALIDATED
            log.mra_invoice_number = response.get('data', {}).get('invoiceNumber', '')
            log.mra_validation_url = response.get('data', {}).get('validationUrl', '')
            log.mra_qr_signature = response.get('data', {}).get('qrCode', '')
            log.mra_response_data = response
            log.synced_at = timezone.now()
            log.save()
            synced += 1
        else:
            log.retry_count += 1
            log.error_message = response.get('error', '')
            if log.retry_count >= 5:
                log.submission_status = EISInvoiceLog.SubmissionStatus.FAILED
            log.save()
            failed += 1

    if failed and self.request.retries < self.max_retries:
        raise self.retry()

    return f'Synced {synced} offline invoices, {failed} failed'