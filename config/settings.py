"""
Django settings for the Pritech Property Management System
(Malawi Property SaaS).

Single-file settings. Environment-driven via python-decouple.

Phase 5: multi-tenant via django-tenants (PostgreSQL schema isolation).
Phase 6: PWA + offline-first (django-pwa, Workbox, IndexedDB sync queue).
Phase 7: real-time (Channels + Redis) + WhatsApp/email communications
         + modernised animated admin theme (Unfold).
Phase 8: auth hardening (Argon2, Axes lockout, rate limiting,
         password reset, JWT), Chichewa localization, security headers
         (CSP), django-redis cache, backups, health checks.
Phase 9: public listings, vacant rentals, tenant home + staff dashboard.
Phase 9.1: Google Sign-In via django-allauth.
Phase 9.2: MFA via allauth.mfa (TOTP + recovery codes).
           Replaces django-two-factor-auth / django-otp.

PostgreSQL is required in BOTH dev and prod — SQLite cannot host tenants.
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config
from django.templatetags.static import static
from celery.schedules import crontab

# ─────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────────────────
SECRET_KEY = config('SECRET_KEY', default='dev-only-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1,.lvh.me',
    cast=Csv(),
)

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default=(
        'http://localhost:8000,http://127.0.0.1:8000,'
        'http://*.lvh.me:8000,http://*.lvh.me:8004'
    ),
    cast=Csv(),
)

SITE_URL = config('SITE_URL', default='http://pms.lvh.me:8000')

TENANT_BASE_DOMAIN = config(
    'TENANT_BASE_DOMAIN',
    default='pms.lvh.me:8004' if DEBUG else 'pms.pritechmw.com',
)


# ─────────────────────────────────────────────────────────────────────
# Multi-tenancy (django-tenants)
# ─────────────────────────────────────────────────────────────────────
TENANT_MODEL = 'tenants.Tenant'
TENANT_DOMAIN_MODEL = 'tenants.Domain'

PUBLIC_SCHEMA_NAME = 'public'
PUBLIC_SCHEMA_URLCONF = 'config.urls_public'
ROOT_URLCONF = 'config.urls'

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)

SHOW_PUBLIC_IF_NO_TENANT_FOUND = config(
    'SHOW_PUBLIC_IF_NO_TENANT_FOUND', default=False, cast=bool,
)

SESSION_COOKIE_DOMAIN = config('SESSION_COOKIE_DOMAIN', default=None)
CSRF_COOKIE_DOMAIN = config('CSRF_COOKIE_DOMAIN', default=None)


# ─────────────────────────────────────────────────────────────────────
# Applications
# SHARED_APPS  → public schema (tenant registry, users, admin, celery,
#                sync, realtime, pwa, channels, anymail, allauth + MFA)
# TENANT_APPS  → per-tenant schema (business data)
# ─────────────────────────────────────────────────────────────────────
SHARED_APPS = [
    'django_tenants',               # must be first
    'apps.shared.tenants',          # Tenant + Domain models

    'unfold',                       # must come before django.contrib.admin
    'unfold.contrib.filters',
    'unfold.contrib.forms',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',         # required by allauth

    'auditlog',
    'django_celery_beat',
    'django_celery_results',

    'apps.shared.users',
    'apps.shared.billing',
    'apps.core.sync',               # Phase 6 — offline sync API
    'apps.realtime',                # Phase 7 — WebSocket infrastructure

    # ─── Phase 8 — API auth ────────────────────────────────────────
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'axes',
    'django_ratelimit',

    # ─── Phase 8 — security headers ────────────────────────────────
    'csp',

    # ─── Phase 9.1 — allauth (email + Google) ──────────────────────
    # ─── Phase 9.2 — built-in MFA (TOTP + recovery codes) ──────────
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.mfa',

    'channels',                     # Phase 7 — ASGI channel layer
    'anymail',                      # Phase 7 — email via Mailgun/SES

    'tailwind',
    'theme',
    'pwa',                          # Phase 6 — PWA manifest + service worker
]

TENANT_APPS = [
    # Core
    'apps.core.properties',
    'apps.core.people',
    'apps.core.documents',

    # Phase 7 — per-tenant notification templates + delivery logs
    'apps.communications',

    # Hospitality
    'apps.hospitality.rates',
    'apps.hospitality.reservations',
    'apps.hospitality.folios',
    'apps.hospitality.housekeeping',

    # Property
    'apps.property.leases',
    'apps.property.rent_invoicing',
    'apps.property.maintenance',
    'apps.property.sales',

    # Compliance (Phase 4)
    'apps.compliance.eis',
    'apps.compliance.paychangu',
    'apps.compliance.tourism_levy',
    'apps.compliance.forex',
    'apps.compliance.fcy',
]

INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]


# ─────────────────────────────────────────────────────────────────────
# Middleware
#
# Order matters:
#   1. TenantMainMiddleware          — must be first, resolves request.tenant
#   2. ClientIPMiddleware            — restores REMOTE_ADDR from X-Real-IP
#   3. Security / CSP / WhiteNoise
#   4. Session, Locale, TenantLanguage
#   5. Common, CSRF, Authentication
#   6. allauth AccountMiddleware     — Phase 9.1, requires request.user
#   7. RequireTenantSetupMiddleware  — after auth, before MFA
#   8. ForceTwoFactorMiddleware      — Phase 9.2, redirects to MFA setup
#   9. Messages, XFrameOptions
#  10. AxesMiddleware                — must be last
# ─────────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',   # must be first
    'apps.shared.users.middleware.ClientIPMiddleware',       # client IP via X-Real-IP
    'django.middleware.security.SecurityMiddleware',
]

MIDDLEWARE.append('csp.middleware.CSPMiddleware')

if not DEBUG:
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')

MIDDLEWARE += [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'apps.shared.tenants.middleware.TenantLanguageMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',

    # Phase 9.1 — allauth requires this class or its AppConfig.ready()
    # raises ImproperlyConfigured. Must sit AFTER AuthenticationMiddleware
    # (it reads request.user) and BEFORE any middleware that consumes
    # allauth's request state.
    'allauth.account.middleware.AccountMiddleware',

    # Phase 9.1 — route fresh Google users to /signup/complete/
    'apps.shared.users.middleware.RequireTenantSetupMiddleware',

    # Phase 9.2 — force platform admins / superusers to enrol in MFA.
    'apps.shared.users.middleware.ForceTwoFactorMiddleware',

    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',                         # must be last
]


WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# django.contrib.sites — required by allauth.
SITE_ID = 1


# ─────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
            ],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': config('DB_NAME', default='pritech_pms_dev' if DEBUG else 'pritech_pms'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default='dev-password'),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=600, cast=int),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

if not DEBUG:
    DATABASES['default']['OPTIONS']['options'] = (
        '-c statement_timeout=30000 '
        '-c jit=off '
        '-c work_mem=16MB'
    )


# ─────────────────────────────────────────────────────────────────────
# Cache & sessions
# ─────────────────────────────────────────────────────────────────────
if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'IGNORE_EXCEPTIONS': True,
                'CONNECTION_POOL_KWARGS': {'max_connections': 50},
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
            },
            'KEY_PREFIX': 'pritech_pms',
            'TIMEOUT': 300,
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'IGNORE_EXCEPTIONS': True,
                'CONNECTION_POOL_KWARGS': {'max_connections': 50},
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
            },
            'KEY_PREFIX': 'pritech_pms',
            'TIMEOUT': 300,
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'

SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG


# ─────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'shared_users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# allauth owns the login flow end-to-end (that's how MFA chains
# without us reimplementing the wizard). The tenant-membership check
# moved to PritechAccountAdapter.login() — see
# apps/shared/users/adapters.py.
LOGIN_URL = 'account_login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'account_login'


# ─────────────────────────────────────────────────────────────────────
# Internationalization
# ─────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en'
TIME_ZONE = 'Africa/Blantyre'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('en', 'English'),
    ('ny', 'Chichewa'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']


# ─────────────────────────────────────────────────────────────────────
# Static & media
# ─────────────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

if (BASE_DIR / 'static').exists():
    STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STORAGES = {
    'default': {
        'BACKEND': 'apps.core.storage.TenantFileStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'whitenoise.storage.CompressedManifestStaticFilesStorage'
            if not DEBUG else
            'django.contrib.staticfiles.storage.StaticFilesStorage'
        ),
    },
}

if not DEBUG:
    WHITENOISE_MAX_AGE = 31536000
    WHITENOISE_USE_FINDERS = False


# ─────────────────────────────────────────────────────────────────────
# Email
# ─────────────────────────────────────────────────────────────────────
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = config(
        'EMAIL_BACKEND',
        default='django.core.mail.backends.smtp.EmailBackend',
    )
    EMAIL_HOST = config('EMAIL_HOST', default='')
    EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
    EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
    EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
    EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
    EMAIL_TIMEOUT = 15

DEFAULT_FROM_EMAIL = config(
    'DEFAULT_FROM_EMAIL',
    default='noreply@pritechmw.com',
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL


# ─────────────────────────────────────────────────────────────────────
# Security (only enforced when DEBUG=False)
# ─────────────────────────────────────────────────────────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_REFERRER_POLICY = 'same-origin'
    SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = False
    CSRF_COOKIE_SAMESITE = 'Lax'

    X_FRAME_OPTIONS = 'DENY'

    CONTENT_SECURITY_POLICY = {
        'DIRECTIVES': {
            'default-src': ["'self'"],
            'script-src': [
                "'self'",
                "'unsafe-inline'",
                'https://cdn.jsdelivr.net',
                'https://unpkg.com',
                'https://cdn.tailwindcss.com',
                'https://storage.googleapis.com',
            ],
            'style-src': [
                "'self'",
                "'unsafe-inline'",
                'https://fonts.googleapis.com',
            ],
            'font-src': ["'self'", 'https://fonts.gstatic.com', 'data:'],
            'img-src': ["'self'", 'data:', 'blob:', 'https:'],
            'connect-src': [
                "'self'",
                'wss://*.pritechmw.com',
                'https://api.paychangu.com',
                'https://graph.facebook.com',
                'https://storage.googleapis.com',
            ],
            'frame-ancestors': ["'none'"],
            'base-uri': ["'self'"],
            'form-action': ["'self'", 'https://accounts.google.com'],
            'manifest-src': ["'self'"],
            'worker-src': ["'self'", 'blob:'],
        },
    }

    PERMISSIONS_POLICY = {
        'geolocation': [],
        'microphone': [],
        'camera': [],
    }


# ─────────────────────────────────────────────────────────────────────
# Celery
# ─────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = config(
    'CELERY_BROKER_URL',
    default='redis://localhost:6379/0',
)
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'django-cache'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

CELERY_BEAT_SCHEDULE = {
    'run-night-audit-all-tenants': {
        'task': 'apps.hospitality.reservations.tasks.run_night_audit_for_all_tenants',
        'schedule': crontab(hour=2, minute=0),
    },
    'generate-monthly-rent-invoices': {
        'task': 'apps.property.rent_invoicing.tasks.generate_monthly_rent_invoices',
        'schedule': crontab(day_of_month=1, hour=6, minute=0),
    },
    'apply-overdue-late-fees': {
        'task': 'apps.property.rent_invoicing.tasks.apply_overdue_late_fees',
        'schedule': crontab(hour=7, minute=0),
    },
    'flag-overdue-invoices': {
        'task': 'apps.property.rent_invoicing.tasks.flag_overdue_invoices',
        'schedule': crontab(hour=7, minute=30),
    },
    'fetch-forex-rates': {
        'task': 'apps.compliance.forex.tasks.fetch_forex_rates',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    'sync-eis-configs': {
        'task': 'apps.compliance.eis.tasks.sync_all_terminal_configs',
        'schedule': crontab(hour=5, minute=0),
    },
    'sync-offline-eis-invoices': {
        'task': 'apps.compliance.eis.tasks.sync_offline_eis_invoices',
        'schedule': crontab(minute='*/15'),
    },
    'generate-monthly-levy-report': {
        'task': 'apps.compliance.tourism_levy.tasks.generate_monthly_levy_report',
        'schedule': crontab(day_of_month=1, hour=6, minute=0),
    },
    'generate-monthly-rbm-returns': {
        'task': 'apps.compliance.fcy.tasks.generate_monthly_rbm_returns',
        'schedule': crontab(day_of_month=1, hour=7, minute=0),
    },
    'scan-checkin-reminders': {
        'task': 'apps.communications.tasks.scan_checkin_reminders',
        'schedule': crontab(hour=9, minute=0),
    },
    'scan-rent-due-reminders': {
        'task': 'apps.communications.tasks.scan_rent_due_reminders',
        'schedule': crontab(hour=8, minute=0),
    },
    # ─── Phase 10 — Subscription billing ───────────────────────────
    'process-expired-trials': {
        'task': 'apps.shared.billing.tasks.process_expired_trials',
        'schedule': crontab(hour=2, minute=0),
    },
    'generate-period-invoices': {
        'task': 'apps.shared.billing.tasks.generate_period_invoices',
        'schedule': crontab(hour=2, minute=15),
    },
    'send-renewal-reminders': {
        'task': 'apps.shared.billing.tasks.send_renewal_reminders',
        'schedule': crontab(hour=6, minute=0),
    },
    'send-payment-reminders': {
        'task': 'apps.shared.billing.tasks.send_payment_reminders',
        'schedule': crontab(hour=9, minute=0),
    },
    'mark-invoices-overdue': {
        'task': 'apps.shared.billing.tasks.mark_invoices_overdue',
        'schedule': crontab(hour=9, minute=30),
    },
    'suspend-delinquent-tenants': {
        'task': 'apps.shared.billing.tasks.suspend_delinquent_tenants',
        'schedule': crontab(hour=10, minute=0),
    },
    'celery-heartbeat': {
        'task': 'apps.shared.tenants.tasks.heartbeat',
        'schedule': crontab(minute='*/15'),
    },
}


# ─────────────────────────────────────────────────────────────────────
# Channels
# ─────────────────────────────────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [
                config(
                    'CHANNEL_LAYER_REDIS_URL',
                    default='redis://127.0.0.1:6379/2',
                ),
            ],
            'expiry': 60,
            'capacity': 1500,
        },
    },
}


# ─────────────────────────────────────────────────────────────────────
# Tailwind
# ─────────────────────────────────────────────────────────────────────
TAILWIND_APP_NAME = 'theme'
TAILWIND_USE_STANDALONE_BINARY = True
INTERNAL_IPS = ['127.0.0.1']


# ─────────────────────────────────────────────────────────────────────
# Django Unfold (admin theme)
#
# Notes
# -----
# * STYLES and SCRIPTS accept either a raw URL string or a callable
#   receiving `request`. A raw string is used verbatim as the href/src
#   attribute — on /admin/ a relative path like 'css/foo.css' resolves
#   to /admin/css/foo.css and 404s. Wrap each entry in a lambda that
#   calls django.templatetags.static.static() so the resolved URL
#   respects STATIC_URL (and ManifestStaticFilesStorage's hash suffix
#   in production).
# * Icon names must come from Unfold's Material Symbols subset. Names
#   it doesn't recognise render as literal text beside the label
#   (e.g. 'front_desk' leaks as 'FRONT_').
# ─────────────────────────────────────────────────────────────────────
UNFOLD = {
    'SITE_TITLE': 'Pritech PMS',
    'SITE_HEADER': 'Pritech PMS',
    'SITE_SUBHEADER': 'Property Management Admin',
    'SITE_URL': '/',
    'SITE_SYMBOL': 'apartment',
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': True,
    'SHOW_LANGUAGES': True,
    'BORDER_RADIUS': '12px',
    'DASHBOARD_CALLBACK': 'apps.core.admin_dashboard.dashboard_callback',

    'ENVIRONMENT': (
        'production' if not DEBUG else 'development'
    ),

    'SITE_DROPDOWN': [
        {'icon': 'public', 'title': 'View public site', 'link': '/'},
        {'icon': 'room_service', 'title': 'Front Desk', 'link': '/reservations/front-desk/'},
        {
            'icon': 'sensors',
            'title': 'WebSocket status',
            'link': '/admin/realtime/',
            'permission': lambda request: request.user.is_superuser,
        },
    ],

    'COLORS': {
        'primary': {
            '50':  '250 245 255',
            '100': '243 232 255',
            '200': '233 213 255',
            '300': '216 180 254',
            '400': '192 132 252',
            '500': '168 85 247',
            '600': '147 51 234',
            '700': '126 34 206',
            '800': '107 33 168',
            '900': '88 28 135',
            '950': '59 7 100',
        },
    },

    # Wrapped in lambda + static() so Unfold resolves the URL through
    # STATIC_URL and (in production) appends ManifestStaticFilesStorage's
    # content-hash suffix. A raw 'css/admin_motion.css' would render as
    # a relative URL from /admin/ and 404.
    'STYLES': [
        lambda request: static('css/admin_motion.css'),
    ],
    'SCRIPTS': [
        lambda request: static('js/admin_motion.js'),
    ],

    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': True,
        'show_section_titles': True,
        'navigation': [
            {
                'title': 'Platform',
                'separator': True,
                'items': [
                    {'title': 'Tenants', 'icon': 'domain',
                     'link': '/platform/tenants/', 'badge': 'Live'},
                    {'title': 'Domains', 'icon': 'link',
                     'link': '/admin/tenants/domain/'},
                    {'title': 'Users', 'icon': 'manage_accounts',
                     'link': '/admin/shared_users/user/'},
                ],
            },
            {
                'title': 'Dashboard',
                'separator': True,
                'items': [
                    {'title': 'Home', 'icon': 'dashboard', 'link': '/admin/'},
                    {'title': 'Front Desk', 'icon': 'room_service',
                     'link': '/reservations/front-desk/', 'badge': 'Live'},
                ],
            },
            {
                'title': 'Hospitality',
                'separator': True,
                'items': [
                    {'title': 'Reservations', 'icon': 'event',
                     'link': '/admin/reservations/reservation/'},
                    {'title': 'Housekeeping', 'icon': 'cleaning_services',
                     'link': '/housekeeping/tasks/'},
                    {'title': 'Rate Plans', 'icon': 'price_change',
                     'link': '/admin/rates/rateplan/'},
                ],
            },
            {
                'title': 'Property',
                'separator': True,
                'items': [
                    {'title': 'Dashboard', 'icon': 'analytics', 'link': '/property/'},
                    {'title': 'Leases', 'icon': 'article', 'link': '/property/leases/'},
                    {'title': 'Rent Invoices', 'icon': 'receipt_long',
                     'link': '/property/invoices/'},
                    {'title': 'Maintenance', 'icon': 'build',
                     'link': '/property/maintenance/'},
                    {'title': 'Sale Listings', 'icon': 'sell',
                     'link': '/property/sales/'},
                ],
            },
            {
                'title': 'Compliance',
                'separator': True,
                'items': [
                    {'title': 'Overview', 'icon': 'verified_user',
                     'link': '/compliance/'},
                    {'title': 'MRA EIS Terminals', 'icon': 'point_of_sale',
                     'link': '/compliance/eis/terminals/'},
                    {'title': 'EIS Invoice Log', 'icon': 'description',
                     'link': '/compliance/eis/invoices/'},
                    {'title': 'EIS Offline Queue', 'icon': 'cloud_off',
                     'link': '/compliance/eis/offline-queue/'},
                    {'title': 'PayChangu', 'icon': 'payments',
                     'link': '/compliance/paychangu/transactions/'},
                    {'title': 'Tourism Levy', 'icon': 'receipt_long',
                     'link': '/compliance/levy/report/'},
                    {'title': 'Forex Rates', 'icon': 'currency_exchange',
                     'link': '/compliance/forex/rates/'},
                    {'title': 'FCY & RBM', 'icon': 'account_balance',
                     'link': '/compliance/fcy/'},
                ],
            },
            {
                'title': 'Communications',
                'separator': True,
                'items': [
                    {'title': 'Message Log', 'icon': 'forum',
                     'link': '/communications/logs/'},
                    {'title': 'Inbound', 'icon': 'inbox',
                     'link': '/communications/inbound/'},
                    {'title': 'Templates', 'icon': 'description',
                     'link': '/communications/templates/'},
                ],
            },
            {
                'title': 'Core',
                'separator': True,
                'items': [
                    {'title': 'Properties', 'icon': 'apartment',
                     'link': '/admin/properties/property/'},
                    {'title': 'Units', 'icon': 'meeting_room',
                     'link': '/admin/properties/unit/'},
                    {'title': 'Amenities', 'icon': 'star',
                     'link': '/admin/properties/amenity/'},
                    {'title': 'People', 'icon': 'people',
                     'link': '/admin/people/person/'},
                    {'title': 'Documents', 'icon': 'description',
                     'link': '/admin/documents/document/'},
                ],
            },
            {
                'title': 'Administration',
                'separator': True,
                'items': [
                    {'title': 'Audit Log', 'icon': 'history',
                     'link': '/admin/auditlog/logentry/'},
                    {'title': 'Periodic Tasks', 'icon': 'schedule',
                     'link': '/admin/django_celery_beat/periodictask/'},
                ],
            },
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────
LOG_DIR = BASE_DIR / 'logs'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {process:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'django.request': {'level': 'WARNING', 'handlers': ['console'], 'propagate': False},
        'django.security': {'level': 'WARNING', 'handlers': ['console'], 'propagate': False},
        'django.db.backends': {'level': 'WARNING', 'handlers': ['console'], 'propagate': False},
        'django_tenants': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'channels': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'apps.realtime': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'apps.communications': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'celery': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'apps': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'allauth': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
    },
}

if not DEBUG:
    LOG_DIR.mkdir(exist_ok=True)

    LOGGING['handlers']['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / 'django.log'),
        'maxBytes': 10 * 1024 * 1024,
        'backupCount': 5,
        'formatter': 'verbose',
    }
    LOGGING['handlers']['celery_file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / 'celery.log'),
        'maxBytes': 10 * 1024 * 1024,
        'backupCount': 5,
        'formatter': 'verbose',
    }
    LOGGING['handlers']['security_file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / 'security.log'),
        'maxBytes': 10 * 1024 * 1024,
        'backupCount': 5,
        'formatter': 'verbose',
    }
    LOGGING['handlers']['channels_file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / 'channels.log'),
        'maxBytes': 10 * 1024 * 1024,
        'backupCount': 5,
        'formatter': 'verbose',
    }

    LOGGING['root']['handlers']                        = ['console', 'file']
    LOGGING['loggers']['django']['handlers']           = ['console', 'file']
    LOGGING['loggers']['django.request']['handlers']   = ['console', 'file']
    LOGGING['loggers']['django.security']['handlers']  = ['console', 'security_file']
    LOGGING['loggers']['channels']['handlers']         = ['console', 'channels_file']
    LOGGING['loggers']['apps.realtime']['handlers']    = ['console', 'channels_file']
    LOGGING['loggers']['celery']['handlers']           = ['console', 'celery_file']
    LOGGING['loggers']['apps']['handlers']             = ['console', 'file']
    LOGGING['loggers']['allauth']['handlers']          = ['console', 'file']


# ─────────────────────────────────────────────────────────────────────
# Sentry (optional)
# ─────────────────────────────────────────────────────────────────────
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN and not DEBUG:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration(), RedisIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=config('SENTRY_ENV', default='production'),
    )


# ─────────────────────────────────────────────────────────────────────
# Phase 4 — Compliance
# ─────────────────────────────────────────────────────────────────────

PAYCHANGU_ENABLED = config('PAYCHANGU_ENABLED', default=False, cast=bool)
PAYCHANGU_BASE_URL = config('PAYCHANGU_BASE_URL', default='https://api.paychangu.com')
PAYCHANGU_SECRET_KEY = config('PAYCHANGU_SECRET_KEY', default='')
PAYCHANGU_WEBHOOK_SECRET = config('PAYCHANGU_WEBHOOK_SECRET', default='')
PAYCHANGU_TIMEOUT = config('PAYCHANGU_TIMEOUT', default=15, cast=int)

EIS_ENABLED = config('EIS_ENABLED', default=False, cast=bool)
EIS_API_BASE_URL = config(
    'EIS_API_BASE_URL',
    default='https://dev-eis-api.mra.mw/api/v1',
)
EIS_SANDBOX_MODE = config('EIS_SANDBOX_MODE', default=True, cast=bool)
EIS_API_KEY = config('EIS_API_KEY', default='')
EIS_TIN = config('EIS_TIN', default='')


# ─────────────────────────────────────────────────────────────────────
# Phase 6 — PWA
# ─────────────────────────────────────────────────────────────────────
PWA_APP_NAME = 'Pritech PMS'
PWA_APP_DESCRIPTION = 'Property management for Malawi hotels, lodges, and rentals.'
PWA_APP_THEME_COLOR = '#9333ea'
PWA_APP_BACKGROUND_COLOR = '#f8fafc'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_ORIENTATION = 'any'
PWA_APP_START_URL = '/'
PWA_APP_STATUS_BAR_COLOR = 'default'
PWA_APP_DIR = 'ltr'
PWA_APP_LANG = 'en'

PWA_APP_ICONS = [
    {'src': '/static/icons/icon-192.png', 'sizes': '192x192',
     'type': 'image/png', 'purpose': 'any maskable'},
    {'src': '/static/icons/icon-512.png', 'sizes': '512x512',
     'type': 'image/png', 'purpose': 'any maskable'},
]

PWA_APP_ICONS_APPLE = [
    {'src': '/static/icons/apple-touch-icon.png', 'sizes': '180x180',
     'type': 'image/png'},
]

PWA_SERVICE_WORKER_PATH = BASE_DIR / 'static' / 'js' / 'serviceworker.js'

PWA_APP_SHORTCUTS = [
    {'name': 'Front Desk', 'url': '/reservations/front-desk/',
     'description': "Today's arrivals and departures"},
    {'name': 'Housekeeping', 'url': '/housekeeping/tasks/',
     'description': 'Room cleaning tasks'},
]

PWA_APP_DEBUG_MODE = DEBUG


# ─────────────────────────────────────────────────────────────────────
# Phase 7 — WhatsApp Cloud API
# ─────────────────────────────────────────────────────────────────────
WHATSAPP_ENABLED = config('WHATSAPP_ENABLED', default=False, cast=bool)
WHATSAPP_PHONE_NUMBER_ID = config('WHATSAPP_PHONE_NUMBER_ID', default='')
WHATSAPP_ACCESS_TOKEN = config('WHATSAPP_ACCESS_TOKEN', default='')
WHATSAPP_APP_SECRET = config('WHATSAPP_APP_SECRET', default='')
WHATSAPP_WEBHOOK_VERIFY_TOKEN = config(
    'WHATSAPP_WEBHOOK_VERIFY_TOKEN', default='',
)
WHATSAPP_API_VERSION = config('WHATSAPP_API_VERSION', default='v21.0')


# ─────────────────────────────────────────────────────────────────────
# Phase 7 — Email via Anymail (Mailgun / SES / Postmark)
# ─────────────────────────────────────────────────────────────────────
ANYMAIL = {
    'MAILGUN_API_KEY': config('MAILGUN_API_KEY', default=''),
    'MAILGUN_SENDER_DOMAIN': config('MAILGUN_SENDER_DOMAIN', default=''),
}

if not DEBUG and ANYMAIL['MAILGUN_API_KEY']:
    EMAIL_BACKEND = 'anymail.backends.mailgun.EmailBackend'


# ─────────────────────────────────────────────────────────────────────
# Phase 8 — Authentication hardening (non-MFA)
# ─────────────────────────────────────────────────────────────────────

# ─── Password hashing — Argon2 (AU-07) ──────────────────────────────
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# ─── Account lockout — django-axes (AU-09) ──────────────────────────
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.5                # 30 minutes
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
AXES_RESET_ON_SUCCESS = True
AXES_ENABLE_ACCESS_FAILURE_LOG = True
AXES_LOCKOUT_CALLABLE = None
AXES_VERBOSE = False
AXES_IPWARE_PROXY_COUNT = 1             # behind Nginx
AXES_IPWARE_META_PRECEDENCE_ORDER = [
    'HTTP_X_REAL_IP',                   # set by Nginx to $remote_addr
    'HTTP_X_FORWARDED_FOR',
    'REMOTE_ADDR',
]

# ─── Rate limiting — django-ratelimit (AU-15) ──────────────────────
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_VIEW = 'apps.shared.users.middleware.ratelimited_view'
RATELIMIT_ENABLE = True
RATELIMIT_IP_META_KEY = 'HTTP_X_REAL_IP'

# ─── JWT for API clients (AU-04) ───────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',
        'user': '1000/day',
        'login': '5/minute',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# ─────────────────────────────────────────────────────────────────────
# Phase 9.1 — allauth (email + Google) + Phase 9.2 — MFA
#
# Design decisions:
#   • Email/password login runs through allauth's login view. The
#     tenant-membership check moved to PritechAccountAdapter.login()
#     (see apps/shared/users/adapters.py).
#   • Google Sign-In unchanged — allauth creates the User; our social
#     adapter splits the `name` claim and routes to /signup/complete/.
#   • ACCOUNT_EMAIL_VERIFICATION is 'optional'. Google verifies the
#     email; email-signup users receive a soft-confirm link.
#   • Phone verification remains format-only at signup.
#   • Phase 9.2: MFA via allauth.mfa — TOTP + recovery codes.
# ─────────────────────────────────────────────────────────────────────

# ─── Allauth core ──────────────────────────────────────────────────
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_EMAIL_CONFIRMATION_HMAC = True
ACCOUNT_CONFIRM_EMAIL_ON_GET = False
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_SESSION_REMEMBER = True

ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGOUT_REDIRECT_URL = '/'

# Custom account adapter enforces tenant-membership on login.
ACCOUNT_ADAPTER = 'apps.shared.users.adapters.PritechAccountAdapter'

# ─── Social account (Google) ──────────────────────────────────────
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_STORE_TOKENS = False

SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {
            'access_type': 'online',
            'prompt': 'select_account',
        },
        'OAUTH_PKCE_ENABLED': True,
        'APP': {
            'client_id': config('GOOGLE_CLIENT_ID', default=''),
            'secret': config('GOOGLE_CLIENT_SECRET', default=''),
            'key': '',
        },
    },
}

SOCIALACCOUNT_ADAPTER = 'apps.shared.users.adapters.PritechSocialAccountAdapter'


# ─── Phase 9.2 — MFA via allauth.mfa ───────────────────────────────
# Supported second factors: TOTP apps and single-use recovery codes.
# WebAuthn / passkeys are opt-in later (add 'webauthn' to the list and
# the `fido2` extra in requirements.txt).
MFA_SUPPORTED_TYPES = ['totp', 'recovery_codes']

# TOTP issuer shown in the authenticator app.
MFA_TOTP_ISSUER = 'Pritech PMS'
MFA_TOTP_PERIOD = 30
MFA_TOTP_DIGITS = 6
MFA_TOTP_TOLERANCE = 1

# Recovery codes.
MFA_RECOVERY_CODE_COUNT = 10
MFA_RECOVERY_CODE_DIGITS = 8

# Allauth template pack — 'allauth' → templates/allauth/account/*.html
TEMPLATE_PACK = 'allauth'


# ─────────────────────────────────────────────────────────────────────
# Phase 9.1 — Optional Veriphone lookup for phone validation
# ─────────────────────────────────────────────────────────────────────
VERIPHONE_API_KEY = config('VERIPHONE_API_KEY', default='')