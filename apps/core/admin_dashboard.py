"""Custom Unfold dashboard callback.

Unfold 0.107's dashboard template renders whatever keys we put on
`context`. We keep the greeting and tenant breadcrumb, and add
`recent_activity` — the latest 10 audit-log entries scoped to the
current tenant, mapped to the shape templates/admin/index.html
expects: {actor, action, object_repr, timestamp}.

If auditlog isn't installed or has no entries yet, `recent_activity`
is an empty list and the template falls back to its empty-state.
"""
from django.utils import timezone


def dashboard_callback(request, context):
    context.update({
        'greeting':   _greeting(),
        'admin_name': (
            request.user.get_full_name()
            or request.user.email
            or request.user.username
        ),
        'tenant':          getattr(request, 'tenant', None),
        'today':           timezone.now(),
        'recent_activity': _recent_activity(request),
    })
    return context


def _greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return 'Good morning'
    if hour < 17:
        return 'Good afternoon'
    return 'Good evening'


def _recent_activity(request, limit=10):
    """Return up to `limit` recent audit-log entries for this tenant."""
    try:
        from auditlog.models import LogEntry
    except Exception:
        return []

    try:
        qs = (
            LogEntry.objects
            .select_related('actor', 'content_type')
            .order_by('-timestamp')[:limit]
        )
    except Exception:
        return []

    entries = []
    for e in qs:
        entries.append({
            'actor':       (e.actor.get_full_name() or e.actor.email) if e.actor else None,
            'action':      e.get_action_display(),
            'object_repr': e.object_repr or '',
            'timestamp':   e.timestamp,
        })
    return entries