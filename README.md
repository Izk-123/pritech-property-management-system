# Pritech PMS

Multi-tenant property management system for Malawi hotels, lodges, and rentals.

**Production:** https://pms.pritechmw.com
**Repository:** https://github.com/Izk-123/pritech-property-management-system

---

## What it does

| Module | Capabilities |
|---|---|
| **Hospitality** | Reservations, check-in/out, housekeeping, folios, night audit, rate plans |
| **Property** | Leases, rent invoicing, arrears tracking, maintenance, sales pipeline |
| **Compliance** | MRA EIS invoicing, PayChangu mobile money, Tourism Levy, RBM returns, FX rate locking |
| **Billing** | Subscription plans, trials, invoices, PayChangu checkout, dunning, auto-suspend |
| **Communications** | WhatsApp (Meta Cloud API), email (Mailgun/Anymail), delivery tracking, inbound inbox |
| **Documents** | PDF folio invoices, receipts, lease agreements, rent invoices, MRA tax invoices |
| **Offline-first PWA** | Works during ESCOM outages, IndexedDB sync queue, Background Sync |
| **Real-time** | WebSocket live updates for front desk, housekeeping, and payment alerts |
| **Multi-currency** | MWK, USD, EUR billing with FX rate caching and lock-at-booking |
| **Multi-tenant SaaS** | PostgreSQL schema isolation, per-tenant templates and data |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Nginx (apex + *.apex)                    │
├──────────────┬──────────────────────┬───────────────────────┤
│  /static/    │  /  → Gunicorn       │  /ws/ → Daphne        │
│  /media/     │  (HTTP + templates)  │  (WebSockets)         │
└──────────────┴──────────┬───────────┴───────────┬───────────┘
                          │                        │
                ┌─────────▼─────────┐   ┌──────────▼──────────┐
                │  Django + DRF      │   │  Channels consumers │
                │  django-tenants    │   │  TenantWSMiddleware │
                └─────────┬──────────┘   └──────────┬──────────┘
                          │                        │
        ┌─────────────────┼────────────────────────┘
        │                 │
   ┌────▼────┐      ┌─────▼─────┐      ┌─────────────┐
   │Postgres │      │  Redis    │      │   Celery    │
   │ (tenant │      │  DB 0/1/2 │      │  Worker+Beat│
   │ schemas)│      │  Broker   │      │             │
   └─────────┘      └───────────┘      └─────────────┘
```

### Technology

| Layer | Technology |
|---|---|
| Backend | Django 5.2, Python 3.12 |
| Database | PostgreSQL 16 |
| Multi-tenancy | `django-tenants` (schema isolation) |
| API | Django REST Framework, SimpleJWT |
| Real-time | Django Channels, Daphne, Redis channel layer |
| Background | Celery, django-celery-beat, django-celery-results |
| Auth | `django-allauth` (email + Google + built-in MFA) |
| Frontend | Django templates, Tailwind (standalone binary), HTMX, Motion One |
| Admin | Django Unfold (Tailwind-based) |
| PDF generation | ReportLab (folio invoices, receipts, leases) |
| PWA | Workbox 7, Dexie (IndexedDB) |
| Email | AnyMail (Mailgun backend) |
| WhatsApp | Meta WhatsApp Cloud API v21 |
| Payments | PayChangu (Airtel Money, TNM Mpamba, cards) |

---

## Quick start (development)

```bash
# 1. Clone
git clone https://github.com/Izk-123/pritech-property-management-system.git
cd pritech-property-management-system

# 2. Create virtualenv
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create the local environment file
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and DB_PASSWORD.
# Everything else has a development-friendly default.

# 5. Create the database and role
sudo -u postgres createdb pritech_pms_dev
sudo -u postgres psql -c "CREATE ROLE pritech_pms_user LOGIN PASSWORD 'dev-password';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE pritech_pms_dev TO pritech_pms_user;"
sudo -u postgres psql -d pritech_pms_dev -c "ALTER SCHEMA public OWNER TO pritech_pms_user;"

# 6. Run migrations
python manage.py migrate_schemas --shared
python manage.py migrate_schemas

# 7. Create the public tenant
python manage.py shell
```
```python
from apps.shared.tenants.models import Tenant, Domain
public, _ = Tenant.objects.get_or_create(
    schema_name='public',
    defaults={'name': 'Pritech PMS', 'plan': 'ENT', 'on_trial': False},
)
Domain.objects.get_or_create(
    domain='pms.lvh.me',
    defaults={'tenant': public, 'is_primary': True},
)
```
```bash
# 8. Create a superuser
python manage.py createsuperuser

# 9. Run
python manage.py runserver 0.0.0.0:8000

# 10. (Optional) Background workers — separate terminals
celery -A config worker -l info
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Visit `http://pms.lvh.me:8000/` (public apex) or `http://pritech.pms.lvh.me:8000/` (a tenant).

To seed a full demo environment with two tenants, properties, reservations,
folios, leases, and every other module populated:

```bash
python manage.py seed_demo
```

Credentials are printed at the end of the command.

---

## Deployment

```bash
cd /home/project/pritech-pms
sudo bash deploy_pritech_pms.sh
```

The deploy script is idempotent and self-healing. It pulls the latest
code, installs dependencies, runs migrations across every tenant schema,
collects static files, compiles translations, and restarts the systemd
services. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for flags,
rollback procedures, and troubleshooting.

---

## Documentation index

| Document | Purpose |
|---|---|
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deploy, rollback, verify a release |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Daily operations, monitoring, common issues |
| [`docs/DISASTER_RECOVERY.md`](docs/DISASTER_RECOVERY.md) | RTO/RPO, failure scenarios, restore procedures |
| [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) | Staff user guide (English) |
| [`docs/USER_MANUAL_NY.md`](docs/USER_MANUAL_NY.md) | Staff user guide (Chichewa) |

---

## Project layout

```
pritech-pms/
├── apps/
│   ├── shared/                       # Public-schema apps
│   │   ├── tenants/                  # Tenant, Domain, provisioning, seed_demo
│   │   ├── users/                    # User, UserTenantMembership, AuthAuditLog
│   │   └── billing/                  # SubscriptionPlan, Subscription,
│   │                                 # SubscriptionInvoice, SubscriptionPayment
│   ├── core/                         # Tenant-schema apps
│   │   ├── properties/               # Property, Unit, Amenity, StaffPropertyAssignment
│   │   ├── people/                   # Person, PersonPropertyRole, Guest* models
│   │   ├── documents/                # Document (GenericFK)
│   │   │   └── pdf/                  # ReportLab pipeline: base, folio, receipt, lease
│   │   ├── sync/                     # Offline sync API + handlers
│   │   ├── permissions.py            # DRF permission classes
│   │   ├── mixins.py                 # View mixins
│   │   ├── admin_mixins.py           # Tenant/platform admin isolation
│   │   └── storage.py                # TenantFileStorage
│   ├── hospitality/                  # Tenant-schema
│   │   ├── reservations/             # Reservation, ReservationRoom
│   │   ├── folios/                   # Folio, FolioCharge, FolioPayment
│   │   ├── housekeeping/             # HousekeepingTask
│   │   └── rates/                    # RatePlan, PricingSeason
│   ├── property/                     # Tenant-schema
│   │   ├── leases/                   # Lease, LeaseUnit
│   │   ├── rent_invoicing/           # RentInvoice, RentPayment
│   │   ├── maintenance/              # MaintenanceRequest
│   │   └── sales/                    # SaleListing, SaleOffer, SaleAgreement
│   ├── compliance/                   # Tenant-schema
│   │   ├── eis/                      # MRA EIS integration
│   │   ├── paychangu/                # Mobile money + reconciliation ledger
│   │   ├── tourism_levy/             # 1% levy
│   │   ├── forex/                    # FX rate caching
│   │   └── fcy/                      # Foreign currency / RBM returns
│   ├── communications/               # Tenant-schema — WhatsApp + email
│   └── realtime/                     # Shared — WebSocket infrastructure
│       ├── consumers.py
│       ├── middleware.py             # TenantWSAuthMiddlewareStack
│       └── routing.py
├── config/
│   ├── settings.py
│   ├── urls.py                       # Tenant schema URLs
│   ├── urls_public.py                # Public schema URLs
│   ├── urls_two_factor.py            # 2FA URL wrapper (legacy compat)
│   ├── asgi.py                       # Channels + Daphne
│   ├── wsgi.py                       # Gunicorn
│   └── celery.py
├── templates/
│   ├── base.html
│   ├── allauth/                      # allauth overrides (login, signup, MFA)
│   ├── account/                      # allauth account templates
│   ├── mfa/                          # allauth MFA templates
│   ├── partials/                     # Headers, banners, indicators
│   └── pages/                        # Marketing, dashboard, billing, modules
├── static/
│   ├── js/                           # Service worker, offline, realtime
│   ├── css/                          # Admin motion
│   └── icons/                        # PWA icons
├── locale/
│   ├── en/
│   └── ny/                           # Chichewa
├── scripts/
│   ├── backup_db.sh
│   ├── backup_media.sh
│   └── restore_db.sh
├── docs/
├── requirements.txt
├── manage.py
└── deploy_pritech_pms.sh
```

---

## Environment variables

All configuration comes from `.env` at the project root. Never commit this file.

Copy `.env.example` to `.env` and fill in the values below.

| Variable | Purpose | Required |
|---|---|---|
| `SECRET_KEY` | Django signing key. Must not be the dev placeholder in production. | Yes |
| `DEBUG` | `True` locally, `False` in production. Defaults to `False`. | Yes |
| `ALLOWED_HOSTS` | Comma-separated hostnames | Yes |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated origins | Yes |
| `TENANT_BASE_DOMAIN` | Base domain for tenant subdomains | Yes |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | PostgreSQL connection | Yes |
| `REDIS_URL` | Cache Redis URL (DB 1) | Yes |
| `CELERY_BROKER_URL` | Celery broker (DB 0) | Yes |
| `CHANNEL_LAYER_REDIS_URL` | Channels layer (DB 2) | Yes |
| `DAPHNE_PORT` | WebSocket port (default 8011) | Yes |
| `EMAIL_*` | SMTP credentials | Production |
| `MAILGUN_API_KEY` | Anymail backend | Optional |
| `SENTRY_DSN` | Error tracking | Optional |
| `PAYCHANGU_ENABLED` | Enable mobile-money checkout | Phase 4+ |
| `PAYCHANGU_SECRET_KEY` / `PAYCHANGU_WEBHOOK_SECRET` | Required when `PAYCHANGU_ENABLED=True` | Conditional |
| `EIS_ENABLED` / `EIS_SANDBOX_MODE` / `EIS_API_KEY` / `EIS_TIN` | MRA EIS integration | Phase 4+ |
| `WHATSAPP_ENABLED` / `WHATSAPP_APP_SECRET` / `WHATSAPP_ACCESS_TOKEN` | Meta Cloud API | Phase 7+ |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Sign-In via allauth | Phase 9.1+ |
| `VERIPHONE_API_KEY` | Optional phone-number validation | Optional |

**Settings guards.** `config/settings.py` refuses to import with an
obviously unsafe configuration. It will raise `ImproperlyConfigured` if:

- `DEBUG=False` and `SECRET_KEY` is still the dev placeholder
- `PAYCHANGU_ENABLED=True` without a webhook secret (that combination
  is equivalent to an open webhook endpoint)
- `EIS_ENABLED=True` with a sandbox/production URL mismatch

The error message names the key to fix. Check `.env` on the server before
deploying a new release.

The deploy script preserves existing values and fills in missing keys,
so a fresh deploy won't overwrite a real secret with an empty one.

---

## Version

Current: **Phase 10 — Subscription billing**

- Phase 0: Foundation
- Phase 1: Core models
- Phase 2: Hospitality MVP
- Phase 3: Property MVP
- Phase 4: Malawi compliance (MRA EIS, PayChangu, Tourism Levy, FX)
- Phase 5: Multi-tenancy via `django-tenants`
- Phase 6: PWA & offline-first
- Phase 7: Real-time (Channels) & communications (WhatsApp, email)
- Phase 7.5: Auth alignment
- Phase 8: Polish, localization, launch (Argon2, 2FA, CSP, backups)
- Phase 9: Public listings, tenant home, staff dashboard
- Phase 9.1: Google Sign-In via `django-allauth`
- Phase 9.2: MFA via `allauth.mfa` (TOTP + recovery codes)
- Phase 9.3: Admin tenant/platform isolation
- Phase 10: Subscription billing (plans, trials, PayChangu, dunning,
  auto-suspend)
- Documents: ReportLab PDF pipeline (folio, receipt, lease)

---

## License

Proprietary. All rights reserved. Pritech.
```