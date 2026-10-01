# config/urls_public.py
"""
Public-schema URL configuration.

Handles marketing, signup, platform admin, tenant-aware authentication,
2FA, allauth (email + Google Sign-In), password reset, meta webhooks,
and the comprehensive health check.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import TemplateView

from apps.shared.tenants.views_health import health_check
from apps.shared.users.views import SchemaAwareLoginView
from apps.communications import views as comm_views


urlpatterns = [
    # ─── Marketing home ────────────────────────────────────────────
    path('', TemplateView.as_view(template_name='pages/public_home.html'),
         name='public_home'),

    # ─── PWA manifest and service worker ───────────────────────────
    path('', include('pwa.urls')),

    # ─── i18n — provides `set_language` for the language switcher ──
    path('i18n/', include('django.conf.urls.i18n')),

    # ─── Offline fallback page ─────────────────────────────────────
    path('offline/', TemplateView.as_view(template_name='pages/offline.html'),
         name='offline'),

    # ─── Signup ────────────────────────────────────────────────────
    # The signup app itself is still our custom views — signup.html
    # / signup_complete.html — so the tenant-provisioning logic runs.
    # allauth is used for the Google OAuth handshake (see /accounts/
    # below), which redirects back into our completion view.
    path('signup/', include('apps.shared.tenants.urls_signup')),

    # ─── Platform admin (tenant management) ────────────────────────
    path('platform/', include('apps.shared.tenants.urls_platform')),

    # ─── Auth ──────────────────────────────────────────────────────
    # Phase 9.1 — allauth owns /accounts/ (login, signup, Google
    # callback, password reset, account management). Its own login
    # form posts to allauth's views, and Google Sign-In lands on
    # /accounts/google/login/callback/.
    #
    # Our legacy /login/ view still exists so any bookmarked links
    # or email templates pointing at /login/ keep working. It routes
    # through SchemaAwareLoginView, which enforces tenant membership.
    path('accounts/', include('allauth.urls')),

    # Two-factor URLs live in a thin wrapper module because upstream
    # django-two-factor-auth doesn't declare app_name at module level.
    path('', include('config.urls_two_factor')),

    # Legacy aliases
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