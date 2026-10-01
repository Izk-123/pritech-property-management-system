# config/urls.py
"""
Tenant-schema URL configuration.

Every tenant subdomain resolves here — the business modules, tenant-
aware auth, password reset, and the guest-facing home page.

Phase 9:   `/` routes to TenantHomeView (guest home).
           `/dashboard/` is the staff landing page.
Phase 9.1: `/accounts/` is mounted here too so allauth works on
           tenant subdomains — staff can sign in with Google or
           manage their account without bouncing to the apex.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import TemplateView

from apps.core.properties.views import TenantHomeView
from apps.shared.tenants.views_health import health_check
from apps.shared.users.views import SchemaAwareLoginView


urlpatterns = [
    # ─── Home / Dashboard ──────────────────────────────────────────
    # `/` shows the guest marketing page to anonymous visitors.
    # Authenticated staff are redirected to `/dashboard/` by
    # TenantHomeView.get(). Both live in the tenant URLconf because
    # each tenant has its own home page.
    path('', TenantHomeView.as_view(), name='home'),
    path('dashboard/',
         TemplateView.as_view(template_name='pages/dashboard.html'),
         name='dashboard'),

    # ─── PWA manifest and service worker ───────────────────────────
    path('', include('pwa.urls')),

    # ─── i18n — `set_language` for the header language switcher ────
    path('i18n/', include('django.conf.urls.i18n')),

    # ─── Offline fallback ──────────────────────────────────────────
    path('offline/', TemplateView.as_view(template_name='pages/offline.html'),
         name='offline'),

    # ─── Core ──────────────────────────────────────────────────────
    path('properties/', include('apps.core.properties.urls')),
    path('people/', include('apps.core.people.urls')),
    path('documents/', include('apps.core.documents.urls')),

    # ─── Auth ──────────────────────────────────────────────────────
    # Phase 9.1 — allauth on tenant subdomains. Google Sign-In,
    # account management, and password reset all work under /accounts/.
    # This is where a staff member on a tenant subdomain lands when
    # they click "Sign in with Google".
    path('accounts/', include('allauth.urls')),

    # Two-factor URLs live in a thin wrapper module because upstream
    # django-two-factor-auth doesn't declare app_name at module level.
    path('', include('config.urls_two_factor')),

    # Legacy alias: /login/ routes through SchemaAwareLoginView, which
    # adds tenant-membership checks on top of the 2FA login form.
    path('login/', SchemaAwareLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # ─── Password reset ────────────────────────────────────────────
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

    # ─── Health check ──────────────────────────────────────────────
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