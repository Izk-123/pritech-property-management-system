"""
Django settings for the Pritech Property Management System
(Malawi Property SaaS).

Single-file settings. Environment-driven via python-decouple.

Phase 5: multi-tenant via django-tenants (PostgreSQL schema isolation).
Phase 6: PWA + offline-first (django-pwa, Workbox, IndexedDB sync queue).
PostgreSQL is required in BOTH dev and prod — SQLite cannot host tenants.
"""

from pathlib import Path

from decouple import Csv, config
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
# SHARED_APPS  → public schema (tenant registry, users, admin, celery, sync, pwa)
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

    'auditlog',
    'django_celery_beat',
    'django_celery_results',

    'apps.shared.users',
    'apps.core.sync',               # Phase 6 — offline sync API
    'tailwind',
    'theme',
    'pwa',                          # Phase 6 — PWA manifest + service worker
]

TENANT_APPS = [
    # Core
    'apps.core.properties',
    'apps.core.people',
    'apps.core.documents',

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
# TenantMainMiddleware MUST be first.
# ─────────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',   # must be first
    'django.middleware.security.SecurityMiddleware',
]

if not DEBUG:
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')

MIDDLEWARE += [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


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
# Database — PostgreSQL in BOTH dev and prod (django-tenants requirement)
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
    DATABASES['default']['OPTIONS']['options'] = '-c statement_timeout=30000'


# ─────────────────────────────────────────────────────────────────────
# Cache & sessions
# ─────────────────────────────────────────────────────────────────────
if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'pritech-pms-dev',
        }
    }
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
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

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'login'


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
    # ─── Phase 5 — Multi-tenant night audit ────────────────────────────
    'run-night-audit-all-tenants': {
        'task': 'apps.hospitality.reservations.tasks.run_night_audit_for_all_tenants',
        'schedule': crontab(hour=2, minute=0),
    },

    # ─── Phase 3 — Property module ─────────────────────────────────────
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

    # ─── Phase 4 — Compliance ──────────────────────────────────────────
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
}


# ─────────────────────────────────────────────────────────────────────
# Tailwind
# ─────────────────────────────────────────────────────────────────────
TAILWIND_APP_NAME = 'theme'
TAILWIND_USE_STANDALONE_BINARY = True
INTERNAL_IPS = ['127.0.0.1']


# ─────────────────────────────────────────────────────────────────────
# Django Unfold (admin theme)
# ─────────────────────────────────────────────────────────────────────
UNFOLD = {
    'SITE_TITLE': 'Pritech PMS',
    'SITE_HEADER': 'Admin',
    'SITE_SUBHEADER': 'Hotel, Lodge & Property Management',
    'SITE_URL': '/',
    'SITE_SYMBOL': 'apartment',
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': False,
    'COLORS': {
        'primary': {
            '50': '250 245 255',
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
    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': True,
        'navigation': [
            {
                'title': 'Platform',
                'items': [
                    {
                        'title': 'Tenants',
                        'icon': 'domain',
                        'link': '/platform/tenants/',
                    },
                    {
                        'title': 'Domains',
                        'icon': 'link',
                        'link': '/admin/tenants/domain/',
                    },
                    {
                        'title': 'Users',
                        'icon': 'manage_accounts',
                        'link': '/admin/shared_users/user/',
                    },
                ],
            },
            {
                'title': 'Dashboard',
                'items': [
                    {'title': 'Home', 'icon': 'dashboard', 'link': '/admin/'},
                    {'title': 'Front Desk', 'icon': 'front_desk',
                     'link': '/reservations/front-desk/'},
                ],
            },
            {
                'title': 'Hospitality',
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
                'items': [
                    {'title': 'Dashboard', 'icon': 'analytics', 'link': '/property/'},
                    {'title': 'Leases', 'icon': 'contract', 'link': '/property/leases/'},
                    {'title': 'Rent Invoices', 'icon': 'receipt_long',
                     'link': '/property/invoices/'},
                    {'title': 'Maintenance', 'icon': 'build',
                     'link': '/property/maintenance/'},
                    {'title': 'Sale Listings', 'icon': 'sell', 'link': '/property/sales/'},
                ],
            },
            {
                'title': 'Compliance',
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
                'title': 'Core',
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
        'django': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
        'django.request': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False,
        },
        'django.security': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False,
        },
        'django.db.backends': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False,
        },
        'django_tenants': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
        'apps': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False,
        },
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

    LOGGING['root']['handlers']                        = ['console', 'file']
    LOGGING['loggers']['django']['handlers']           = ['console', 'file']
    LOGGING['loggers']['django.request']['handlers']   = ['console', 'file']
    LOGGING['loggers']['django.security']['handlers']  = ['console', 'security_file']
    LOGGING['loggers']['celery']['handlers']           = ['console', 'celery_file']
    LOGGING['loggers']['apps']['handlers']             = ['console', 'file']


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
# Phase 6 — PWA (Progressive Web App)
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
    {
        'src': '/static/icons/icon-192.png',
        'sizes': '192x192',
        'type': 'image/png',
        'purpose': 'any maskable',
    },
    {
        'src': '/static/icons/icon-512.png',
        'sizes': '512x512',
        'type': 'image/png',
        'purpose': 'any maskable',
    },
]

PWA_APP_ICONS_APPLE = [
    {
        'src': '/static/icons/apple-touch-icon.png',
        'sizes': '180x180',
        'type': 'image/png',
    },
]

PWA_SERVICE_WORKER_PATH = BASE_DIR / 'static' / 'js' / 'serviceworker.js'

PWA_APP_SHORTCUTS = [
    {
        'name': 'Front Desk',
        'url': '/reservations/front-desk/',
        'description': "Today's arrivals and departures",
    },
    {
        'name': 'Housekeeping',
        'url': '/housekeeping/tasks/',
        'description': 'Room cleaning tasks',
    },
]

PWA_APP_DEBUG_MODE = DEBUG