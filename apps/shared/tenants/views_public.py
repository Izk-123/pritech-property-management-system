"""
Views for the public apex (pms.pritechmw.com).

The marketing home page is rendered only for anonymous visitors.
Authenticated users are redirected to the right workspace or admin area.
"""
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView


def _workspace_url(tenant):
    """Return the primary HTTPS URL for a tenant, or None."""
    if tenant is None:
        return None

    domain = tenant.domains.filter(is_primary=True).first()
    if not domain:
        return None
    return f'https://{domain.domain}/'


class PublicHomeView(TemplateView):
    """Apex home page for anonymous visitors; redirects signed-in users."""

    template_name = 'pages/public_home.html'

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            target = self._redirect_target(request)
            if target:
                return redirect(target)
        return super().get(request, *args, **kwargs)

    def _redirect_target(self, request):
        user = request.user

        if user.is_superuser or user.is_platform_admin:
            return reverse('admin:index')

        last = user.last_tenant
        if last and user.has_membership(last):
            url = _workspace_url(last)
            if url:
                return url

        membership = (
            user.tenant_memberships
            .filter(is_active=True)
            .select_related('tenant')
            .first()
        )
        if membership:
            url = _workspace_url(membership.tenant)
            if url:
                return url

        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated:
            memberships = list(
                user.tenant_memberships.filter(is_active=True).select_related('tenant')
            )
            context['needs_workspace'] = len(memberships) == 0
        else:
            context['needs_workspace'] = False
        return context
