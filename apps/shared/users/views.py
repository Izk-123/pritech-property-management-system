from django.contrib.auth.views import LoginView
from django.urls import reverse, NoReverseMatch


class SchemaAwareLoginView(LoginView):
    """
    Login view that redirects to the right destination for the current schema.

    - Public schema  → public_home
    - Tenant schema  → front desk (if available), else tenant home
    - ?next= is respected when safe
    """
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        # Honour an explicit, safe ?next= first
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to

        tenant = getattr(self.request, 'tenant', None)

        # Public schema → marketing home
        if not tenant or tenant.schema_name == 'public':
            return reverse('public_home')

        # Tenant schema → front desk, falling back to home
        try:
            return reverse('reservations:front_desk')
        except NoReverseMatch:
            return reverse('home')