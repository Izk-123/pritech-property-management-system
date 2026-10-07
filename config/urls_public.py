# config/urls_public.py
"""
Public-schema URL configuration.

Handles marketing, signup, platform admin, tenant-aware authentication,
allauth (email + Google + MFA), password reset, meta webhooks, and the
comprehensive health check.

Phase 9.2: two_factor.urls is gone. allauth owns /accounts/2fa/.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView
from django.views.generic import RedirectView
from apps.shared.tenants.views_health import health_check
from apps.shared.tenants.views_public import PublicHomeView
from apps.communications import views as comm_views


urlpatterns = [
    # ─── Marketing home ────────────────────────────────────────────
    path('', PublicHomeView.as_view(), name='public_home'),
    path(
        'favicon.ico',
        RedirectView.as_view(url='/static/icons/favicon.svg', permanent=True),
        name='favicon',
    ),
    # ─── PWA manifest and service worker ───────────────────────────
    path('', include('pwa.urls')),

    # ─── i18n — provides `set_language` for the language switcher ──
    path('i18n/', include('django.conf.urls.i18n')),

    # ─── Offline fallback page ─────────────────────────────────────
    path('offline/', TemplateView.as_view(template_name='pages/offline.html'),
         name='offline'),

    # ─── Signup ────────────────────────────────────────────────────
    # Custom views — signup.html / signup_complete.html — so the
    # tenant-provisioning logic runs. allauth handles the Google
    # OAuth handshake and redirects back into our completion view.
    path('signup/', include('apps.shared.tenants.urls_signup')),

    # ─── Platform admin (tenant management) ────────────────────────
    path('platform/', include('apps.shared.tenants.urls_platform')),

    # ─── Billing admin (Phase 10) ──────────────────────────────────
    path('platform/billing/', include('apps.shared.billing.urls_admin')),

    # ─── Auth (Phase 9.1 + 9.2) ────────────────────────────────────
    # allauth owns /accounts/ — login, signup, Google OAuth callback,
    # password reset, account management, MFA under /accounts/2fa/.
    path('accounts/', include('allauth.urls')),

    # Legacy aliases
    path('login/', RedirectView.as_view(
        pattern_name='account_login', permanent=False, query_string=True,
    ), name='login'),
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

    # ─── Health check (Phase 8 — comprehensive) ────────────────────
    path('health/', health_check, name='health'),

    # ─── Meta webhooks (public — Meta posts from an external IP) ───
    path('communications/whatsapp/webhook/',
         comm_views.whatsapp_webhook,
         name='whatsapp_webhook'),
    path('communications/whatsapp/verify/',
         comm_views.whatsapp_verify,
         name='whatsapp_verify'),

    # ─── Admin ─────────────────────────────────────────────────────
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)