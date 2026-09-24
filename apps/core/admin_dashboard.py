"""Custom Unfold dashboard callback.

Returns the context dict that Unfold's dashboard template renders.
We use it to greet the admin by name and show the tenant context
so a staff member always knows which workspace they're in.
"""
from django.utils import timezone


def dashboard_callback(request, context):
    context.update({
        'greeting': _greeting(),
        'admin_name': (
            request.user.get_full_name()
            or request.user.email
            or request.user.username
        ),
        'tenant': getattr(request, 'tenant', None),
        'today': timezone.now(),
    })
    return context


def _greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return 'Good morning'
    if hour < 17:
        return 'Good afternoon'
    return 'Good evening'