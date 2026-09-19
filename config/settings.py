"""
Django settings for config project.

Single-file settings for Phase 0 development.
Split into base.py / development.py / production.py before Phase 5.
"""

from pathlib import Path
from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# config/settings.py -> config/ -> project root
BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Security & environment
# ---------------------------------------------------------------------------

SECRET_KEY = config('SECRET_KEY', default='dev-only-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

SHARED_APPS = [
    # Unfold must come first
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',

    # Django contrib
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Local apps
    'apps.shared.users',

    # Tailwind (the management command lives in the 'tailwind' app;
    # 'theme' is the generated app you create with `tailwind init theme`)
    'tailwind',
    'theme',
    
    'auditlog',
    'django_celery_beat',
    'django_celery_results',
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
]

INSTALLED_APPS = SHARED_APPS + [app for app in TENANT_APPS if app not in SHARED_APPS]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ---------------------------------------------------------------------------
# Database
# SQLite for Phase 0. Swap to PostgreSQL in Phase 5 (django-tenants).
# ---------------------------------------------------------------------------

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 10},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en'
TIME_ZONE = 'Africa/Blantyre'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('en', 'English'),
    ('ny', 'Chichewa'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']


# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ---------------------------------------------------------------------------
# Default primary key
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = 'shared_users.User'


# ---------------------------------------------------------------------------
# Tailwind
# ---------------------------------------------------------------------------

TAILWIND_APP_NAME = 'theme'

# Windows: skip NPM, use the bundled standalone Tailwind CLI binary.
TAILWIND_USE_STANDALONE_BINARY = True

INTERNAL_IPS = ['127.0.0.1']


# ---------------------------------------------------------------------------
# Email (dev: print to console)
# ---------------------------------------------------------------------------

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# ---------------------------------------------------------------------------
# Django Unfold
# ---------------------------------------------------------------------------

UNFOLD = {
    'SITE_TITLE': 'Malawi Property SaaS',
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
                'title': 'Dashboard',
                'items': [
                    {'title': 'Home', 'icon': 'dashboard', 'link': '/admin/'},
                    {'title': 'Front Desk', 'icon': 'front_desk', 'link': '/reservations/front-desk/'},
                ],
            },
            {
                'title': 'Hospitality',
                'items': [
                    {'title': 'Reservations', 'icon': 'event', 'link': '/reservations/'},
                    {'title': 'Housekeeping', 'icon': 'cleaning_services', 'link': '/housekeeping/tasks/'},
                    {'title': 'Rate Plans', 'icon': 'price_change', 'link': '/admin/rates/rateplan/'},
                ],
            },
            {
                'title': 'Core',
                'items': [
                    {'title': 'Properties', 'icon': 'apartment', 'link': '/admin/properties/property/'},
                    {'title': 'Units', 'icon': 'meeting_room', 'link': '/admin/properties/unit/'},
                    {'title': 'Amenities', 'icon': 'star', 'link': '/admin/properties/amenity/'},
                    {'title': 'People', 'icon': 'people', 'link': '/admin/people/person/'},
                    {'title': 'Documents', 'icon': 'description', 'link': '/admin/documents/document/'},
                ],
            },
            {
                'title': 'Administration',
                'items': [
                    {'title': 'Users', 'icon': 'manage_accounts', 'link': '/admin/shared_users/user/'},
                    {'title': 'Audit Log', 'icon': 'history', 'link': '/admin/auditlog/logentry/'},
                    {'title': 'Periodic Tasks', 'icon': 'schedule', 'link': '/admin/django_celery_beat/periodictask/'},
                ],
            },
            {
                'title': 'Property',
                'items': [
                    {
                        'title': 'Dashboard',
                        'icon': 'analytics',
                        'link': '/property/',
                    },
                    {
                        'title': 'Leases',
                        'icon': 'contract',
                        'link': '/property/leases/',
                    },
                    {
                        'title': 'Rent Invoices',
                        'icon': 'receipt_long',
                        'link': '/property/invoices/',
                    },
                    {
                        'title': 'Maintenance',
                        'icon': 'build',
                        'link': '/admin/maintenance/maintenancerequest/',
                    },
                    {
                        'title': 'Sale Listings',
                        'icon': 'sell',
                        'link': '/admin/sales/salelisting/',
                    },
                ],
            },
        ],
    },
}

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'django-cache'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
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
}