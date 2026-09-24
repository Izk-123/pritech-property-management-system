"""
Communications views.

Public webhook endpoints for Meta + staff-facing notification center.
"""
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView, DetailView, UpdateView, FormView

from apps.core.mixins import StaffRequiredMixin
from .forms import InboundReplyForm
from .models import InboundMessage, NotificationLog, NotificationTemplate
from .services import WhatsAppClient


# ─────────────────────────────────────────────────────────────────────
# WhatsApp webhook (public)
# ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_GET
def whatsapp_verify(request):
    """Meta's webhook verification handshake."""
    mode = request.GET.get('hub.mode')
    token = request.GET.get('hub.verify_token')
    challenge = request.GET.get('hub.challenge')

    expected = getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', '')
    if mode == 'subscribe' and token and token == expected:
        return HttpResponse(challenge, content_type='text/plain')
    return HttpResponse('Forbidden', status=403)


@csrf_exempt
@require_POST
def whatsapp_webhook(request):
    """Receive delivery receipts and inbound messages from Meta."""
    signature = request.headers.get('X-Hub-Signature-256', '')
    app_secret = getattr(settings, 'WHATSAPP_APP_SECRET', '')

    if app_secret:
        expected = 'sha256=' + hmac.new(
            app_secret.encode(), request.body, hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning('WhatsApp webhook: invalid signature')
            return HttpResponse(status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            for status in value.get('statuses', []):
                _process_status(status)
            for message in value.get('messages', []):
                _process_inbound(message, value)

    return JsonResponse({'status': 'ok'})


logger = logging.getLogger(__name__)


def _process_status(status):
    """Update NotificationLog from a delivery status event."""
    provider_id = status.get('id')
    new_status = status.get('status')  # sent / delivered / read / failed

    if not provider_id:
        return

    mapping = {
        'sent': NotificationLog.Status.SENT,
        'delivered': NotificationLog.Status.DELIVERED,
        'read': NotificationLog.Status.READ,
        'failed': NotificationLog.Status.FAILED,
    }
    log_status = mapping.get(new_status)
    if not log_status:
        return

    log = NotificationLog.objects.filter(
        provider_message_id=provider_id,
    ).first()
    if not log:
        return

    log.status = log_status
    if log_status == NotificationLog.Status.DELIVERED:
        log.delivered_at = timezone.now()
    log.save(update_fields=['status', 'delivered_at', 'updated_at'])


def _process_inbound(message, value):
    """Store an inbound WhatsApp message and try to link it to a Person."""
    from_number = message.get('from')
    body = message.get('text', {}).get('body', '').strip()
    if not from_number or not body:
        return

    # Best-effort match to a Person
    from apps.communications.services import normalise_mw_phone
    from apps.core.people.models import Person

    normalised = normalise_mw_phone(from_number)
    person = None
    if normalised:
        person = Person.objects.filter(
            phone_primary__icontains=normalised[-9:],
        ).first()

    InboundMessage.objects.create(
        person=person,
        from_number=from_number,
        body=body,
        provider_message_id=message.get('id', ''),
    )


# ─────────────────────────────────────────────────────────────────────
# Staff-facing notification centre
# ─────────────────────────────────────────────────────────────────────

class NotificationLogListView(StaffRequiredMixin, ListView):
    model = NotificationLog
    template_name = 'pages/communications/log_list.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        qs = NotificationLog.objects.select_related('person').order_by(
            '-created_at'
        )

        channel = self.request.GET.get('channel', '')
        if channel in NotificationLog.Channel.values:
            qs = qs.filter(channel=channel)

        status = self.request.GET.get('status', '')
        if status in NotificationLog.Status.values:
            qs = qs.filter(status=status)

        event = self.request.GET.get('event', '')
        if event:
            qs = qs.filter(event=event)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['channels'] = NotificationLog.Channel.choices
        ctx['statuses'] = NotificationLog.Status.choices
        ctx['current_channel'] = self.request.GET.get('channel', '')
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['current_event'] = self.request.GET.get('event', '')
        ctx['failed_count'] = NotificationLog.objects.filter(
            status=NotificationLog.Status.FAILED,
        ).count()
        ctx['pending_count'] = NotificationLog.objects.filter(
            status=NotificationLog.Status.PENDING,
        ).count()
        return ctx


class NotificationLogDetailView(StaffRequiredMixin, DetailView):
    model = NotificationLog
    template_name = 'pages/communications/log_detail.html'
    context_object_name = 'log'


class InboundMessageListView(StaffRequiredMixin, ListView):
    model = InboundMessage
    template_name = 'pages/communications/inbound_list.html'
    context_object_name = 'messages'
    paginate_by = 50

    def get_queryset(self):
        qs = InboundMessage.objects.select_related('person').order_by(
            '-created_at'
        )
        if self.request.GET.get('unread') == '1':
            qs = qs.filter(is_read=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['unread_count'] = InboundMessage.objects.filter(is_read=False).count()
        ctx['show_unread'] = self.request.GET.get('unread') == '1'
        return ctx


class InboundMessageReplyView(StaffRequiredMixin, FormView):
    template_name = 'pages/communications/inbound_reply.html'
    form_class = InboundReplyForm

    def get_message(self):
        return get_object_or_404(InboundMessage, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['message'] = self.get_message()
        return ctx

    def form_valid(self, form):
        inbound = self.get_message()
        client = WhatsAppClient()
        message_id, error = client.send_text(
            to=inbound.from_number,
            body=form.cleaned_data['body'],
        )

        if error:
            messages.error(self.request, f'Send failed: {error}')
            return self.form_invalid(form)

        inbound.replied = True
        inbound.replied_at = timezone.now()
        inbound.is_read = True
        inbound.save(update_fields=['replied', 'replied_at', 'is_read', 'updated_at'])

        messages.success(self.request, 'Reply sent.')
        return redirect('communications:inbound_list')


class NotificationTemplateListView(StaffRequiredMixin, ListView):
    model = NotificationTemplate
    template_name = 'pages/communications/template_list.html'
    context_object_name = 'templates'

    def get_queryset(self):
        return NotificationTemplate.objects.order_by('event', 'channel')


class NotificationTemplateUpdateView(StaffRequiredMixin, UpdateView):
    model = NotificationTemplate
    template_name = 'pages/communications/template_form.html'
    fields = ['name', 'body', 'language', 'is_active']

    def form_valid(self, form):
        messages.success(self.request, 'Template updated.')
        return super().form_valid(form)

    def get_success_url(self):
        from django.urls import reverse_lazy
        return reverse_lazy('communications:template_list')