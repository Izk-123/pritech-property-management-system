# config/urls.py
"""
Tenant-schema URL configuration.

Every tenant subdomain resolves here. Includes the business modules
plus tenant-aware auth, password reset, and a health check.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import TemplateView

from apps.shared.tenants.views_health import health_check
from apps.shared.users.views import SchemaAwareLoginView


urlpatterns = [
    path('', TemplateView.as_view(template_name='pages/home.html'), name='home'),

    # ─── PWA manifest and service worker ───────────────────────────
    path('', include('pwa.urls')),

    # ─── i18n — provides `set_language` for the language switcher ──
    path('i18n/', include('django.conf.urls.i18n')),

    # ─── Offline fallback page ─────────────────────────────────────
    path('offline/', TemplateView.as_view(template_name='pages/offline.html'),
         name='offline'),

    # ─── Core ──────────────────────────────────────────────────────
    path('properties/', include('apps.core.properties.urls')),
    path('people/', include('apps.core.people.urls')),
    path('documents/', include('apps.core.documents.urls')),

    # ─── Auth ──────────────────────────────────────────────────────
    # Phase 8 — django-two-factor-auth owns /account/login/ and all 2FA
    # setup/recovery paths. We include a thin wrapper module
    # (config/urls_two_factor.py) that declares app_name = 'two_factor'
    # so the namespace resolves. The upstream two_factor.urls module
    # doesn't declare app_name, which is why a plain include() of that
    # module fails, and why the 2-tuple form misbehaves (Django expects
    # a pattern list, not a module path, in the first tuple element).
    path('', include('config.urls_two_factor')),

    # Legacy alias: /login/ still routes through the tenant-membership-
    # aware SchemaAwareLoginView.
    path('login/', SchemaAwareLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # ─── Password reset (Phase 8 — AU-08) ──────────────────────────
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.txt',
            subject_template_name='registration/password_reset_subject.txt',
            success_url='/password-reset/done/',
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            success_url='/password-reset/complete/',
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),

    # ─── Health check (Phase 8 — per-tenant) ───────────────────────
    path('health/', health_check, name='health'),

    # ─── Hospitality ───────────────────────────────────────────────
    path('reservations/', include('apps.hospitality.reservations.urls')),
    path('folios/', include('apps.hospitality.folios.urls')),
    path('housekeeping/', include('apps.hospitality.housekeeping.urls')),

    # ─── Property ──────────────────────────────────────────────────
    path('property/', include('apps.property.urls')),

    # ─── Compliance ────────────────────────────────────────────────
    path('compliance/', include('apps.compliance.urls')),

    # ─── Offline sync API (Phase 6) ────────────────────────────────
    path('api/v1/sync/', include('apps.core.sync.urls')),

    # ─── Communications (staff-facing) ─────────────────────────────
    path('communications/', include('apps.communications.urls')),

    # ─── Admin ─────────────────────────────────────────────────────
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)