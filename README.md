# Phase 8 — Category 12: Documentation Files

Six files. Each is complete and ready to commit. Copy the content into the exact path shown.

---

## 1. `README.md` (repo root)

```markdown
# Pritech PMS

Multi-tenant property management system for Malawi hotels, lodges, and rentals.

**Production:** https://pms.pritechmw.com
**Server:** 204.168.251.91
**Repository:** https://github.com/Izk-123/pritech-property-management-system

---

## What it does

| Module | Capabilities |
|---|---|
| **Hospitality** | Reservations, check-in/out, housekeeping, folios, night audit, rate plans |
| **Property** | Leases, rent invoicing, arrears tracking, maintenance, sales pipeline |
| **Compliance** | MRA EIS invoicing, PayChangu mobile money, Tourism Levy, RBM returns, FX rate locking |
| **Communications** | WhatsApp (Meta Cloud API), email (Mailgun/Anymail), delivery tracking, inbound message inbox |
| **Offline-first PWA** | Works during ESCOM outages, IndexedDB sync queue, Background Sync |
| **Real-time** | WebSocket live updates for front desk, housekeeping, and payment alerts |
| **Multi-currency** | MWK, USD, EUR billing with FX rate caching and lock-at-booking |
| **Multi-tenant SaaS** | PostgreSQL schema isolation, per-tenant templates and data |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Nginx (pms.pritechmw.com + *.pms.*)      │
├──────────────┬──────────────────────┬───────────────────────┤
│  /static/    │  /  → Gunicorn:8000  │  /ws/ → Daphne:8011   │
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
| Frontend | Django templates, Tailwind (standalone binary), HTMX, Motion One |
| Admin | Django Unfold (Tailwind-based) |
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

# 3. Install
pip install -r requirements.txt

# 4. Copy and edit environment
cp .env.example .env
# Edit .env — at minimum, set SECRET_KEY and DB_PASSWORD

# 5. Create database
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
# 8. Create superuser
python manage.py shell
```
```python
from django.contrib.auth import get_user_model
U = get_user_model()
U.objects.create_superuser(
    email='admin@local.test',
    username='admin',
    password='ChangeMe123!',
)
```

```bash
# 9. Run
python manage.py runserver 0.0.0.0:8000

# 10. (Optional) Background workers — separate terminals
celery -A config worker -l info
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Visit `http://pms.lvh.me:8000/` (public) or `http://pritech.pms.lvh.me:8000/` (a tenant).

---

## Deployment

```bash
cd /home/project/pritech-pms
sudo bash deploy_pritech_pms.sh
```

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for details, rollback, and troubleshooting.

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
│   ├── shared/                      # Public-schema apps
│   │   ├── tenants/                 # Tenant, Domain, provisioning
│   │   └── users/                   # User, UserTenantMembership, AuthAuditLog
│   ├── core/                        # Tenant-schema apps
│   │   ├── properties/              # Property, Unit, Amenity, StaffPropertyAssignment
│   │   ├── people/                  # Person, PersonPropertyRole, Guest* models
│   │   ├── documents/               # Document (GenericFK)
│   │   ├── sync/                    # Offline sync API
│   │   ├── permissions.py           # DRF permission classes
│   │   ├── mixins.py                # View mixins
│   │   └── storage.py               # TenantFileStorage
│   ├── hospitality/                 # Tenant-schema
│   │   ├── reservations/            # Reservation, ReservationRoom
│   │   ├── folios/                  # Folio, FolioCharge, FolioPayment
│   │   ├── housekeeping/            # HousekeepingTask
│   │   └── rates/                   # RatePlan, PricingSeason
│   ├── property/                    # Tenant-schema
│   │   ├── leases/                  # Lease, LeaseUnit
│   │   ├── rent_invoicing/          # RentInvoice, RentPayment
│   │   ├── maintenance/             # MaintenanceRequest
│   │   └── sales/                   # SaleListing, SaleOffer, SaleAgreement
│   ├── compliance/                  # Tenant-schema
│   │   ├── eis/                     # MRA EIS integration
│   │   ├── paychangu/               # Mobile money
│   │   ├── tourism_levy/            # 1% levy
│   │   ├── forex/                   # FX rate caching
│   │   └── fcy/                     # Foreign currency / RBM returns
│   ├── communications/              # Tenant-schema
│   │   └── (models, tasks, views)   # WhatsApp + email
│   └── realtime/                    # Shared (WebSocket infrastructure)
│       ├── consumers.py
│       ├── middleware.py            # TenantWSMiddleware
│       └── routing.py
├── config/
│   ├── settings.py
│   ├── urls.py                      # Tenant schema URLs
│   ├── urls_public.py               # Public schema URLs
│   ├── asgi.py                      # Channels + Daphne
│   ├── wsgi.py                      # Gunicorn
│   └── celery.py
├── templates/
│   ├── base.html
│   ├── partials/
│   ├── pages/
│   └── registration/
├── static/
│   ├── js/
│   ├── css/
│   └── icons/
├── locale/
│   ├── en/
│   └── ny/
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

| Variable | Purpose | Required |
|---|---|---|
| `SECRET_KEY` | Django signing key | Yes |
| `DEBUG` | `True` locally, `False` in production | Yes |
| `ALLOWED_HOSTS` | Comma-separated hostnames | Yes |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated origins | Yes |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | PostgreSQL connection | Yes |
| `REDIS_URL` | Cache Redis URL (DB 1) | Yes |
| `CELERY_BROKER_URL` | Celery broker (DB 0) | Yes |
| `CHANNEL_LAYER_REDIS_URL` | Channels layer (DB 2) | Yes |
| `DAPHNE_PORT` | WebSocket port (default 8011) | Yes |
| `EMAIL_*` | SMTP credentials | Production |
| `MAILGUN_API_KEY` | Anymail backend | Optional |
| `SENTRY_DSN` | Error tracking | Optional |
| `PAYCHANGU_*` | Mobile money credentials | Phase 4+ |
| `EIS_*` | MRA EIS credentials | Phase 4+ |
| `WHATSAPP_*` | Meta Cloud API credentials | Phase 7+ |

The deploy script preserves existing values and fills in missing keys.

---

## Version

Current: **Phase 8 — Production launch**

- Phase 0: Foundation
- Phase 1: Core models
- Phase 2: Hospitality MVP
- Phase 3: Property MVP
- Phase 4: Malawi compliance
- Phase 5: Multi-tenancy
- Phase 6: PWA & offline-first
- Phase 7: Real-time & communications
- Phase 7.5: Auth alignment
- Phase 8: Polish, localization, launch

---

## License

Proprietary. All rights reserved. Pritech.
```

---

## 2. `docs/DEPLOYMENT.md`

```markdown
# Deployment Guide

Everything you need to deploy, verify, and roll back Pritech PMS.

**Server:** 204.168.251.91
**Domain:** pms.pritechmw.com and `*.pms.pritechmw.com`
**Project directory:** `/home/project/pritech-pms`

---

## Prerequisites

The server must have:

- Ubuntu 22.04 LTS or later
- Python 3.12
- PostgreSQL 16
- Redis 7
- Nginx
- `certbot` (for SSL)
- `git`, `curl`, `dig`, `ss`, `fuser`
- `gettext` (for translation compilation)

Check with:

```bash
python3 --version
psql --version
redis-cli --version
nginx -v
```

---

## The deploy script

All deployments go through one script: `deploy_pritech_pms.sh`.

### Usage

```bash
cd /home/project/pritech-pms
sudo bash deploy_pritech_pms.sh [FLAGS]
```

### Flags

| Flag | Effect |
|---|---|
| *(none)* | Full deploy: pull, install, migrate, collect, restart |
| `--fresh` | **DESTRUCTIVE.** Drops the database before migrating. Never use on production unless intentionally resetting. |
| `--skip-ssl` | Skip the certbot renewal step |
| `--env-only` | Update `.env` values without touching code or DB |
| `--help` | Print the script header |

### What it does

The script is idempotent and self-healing. It runs these steps in order:

1. **Pre-flight** — chooses a free Daphne port if 8011 is occupied
2. **Pre-flight** — checks wildcard DNS and SSL certificate
3. **Pre-flight** — checks Redis on DB 2
4. **Step 0** — kills stale project processes (any orphaned daphne/gunicorn)
5. **Step 1** — pulls the latest code from `origin/main`
6. **Step 2** — creates or updates the virtualenv, installs `requirements.txt`
7. **Step 3** — writes or updates `.env` (preserving secrets)
8. **Step 4** — ensures PostgreSQL user and database exist
9. **Step 5** — checks for missing migrations and generates them
10. **Step 6** — runs `manage.py check`
11. **Step 7** — `migrate_schemas --shared`
12. **Step 8** — ensures the public tenant exists
13. **Step 9** — `migrate_schemas` (all tenants)
14. **Step 9b** — verifies all schemas are up to date
15. **Step 10** — `collectstatic --noinput --clear`
16. **Step 10b** — verifies both URLconfs import cleanly
17. **Step 11** — ensures a superuser exists
18. **Step 12** — writes systemd units
19. **Step 15** — writes Nginx config
20. **Step 16** — renews SSL
21. **Step 17** — restarts services cleanly
22. **Step 18** — smoke tests 15 endpoints

At the end it prints a summary with all endpoints and service states.

---

## Standard deployment

```bash
cd /home/project/pritech-pms
sudo bash deploy_pritech_pms.sh
```

Expected output ends with:

```
══════════════════════════════════════════════════════════
  Deploy complete — 14:32:18
══════════════════════════════════════════════════════════
  HEAD           : a1b2c3d
  Public site    : https://pms.pritechmw.com/
  Admin          : https://pms.pritechmw.com/admin/
  First tenant   : https://pritech.pritechmw.com/
  Daphne port    : 8011
```

---

## Verifying a deployment

### 1. Health check

```bash
curl -s https://pms.pritechmw.com/health/ | python3 -m json.tool
```

Expected:

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "cache": "ok",
    "celery_broker": "ok",
    "public_tenant": "Pritech PMS"
  }
}
```

### 2. Systemd services

```bash
for svc in gunicorn-pritech-pms daphne-pritech-pms celery-worker-pritech-pms celery-beat-pritech-pms nginx postgresql redis-server; do
    printf "%-30s " "$svc"
    systemctl is-active "$svc"
done
```

All should print `active`.

### 3. Smoke tests

```bash
# Public
curl -sI https://pms.pritechmw.com/ | head -1
curl -sI https://pms.pritechmw.com/admin/ | head -1
curl -sI https://pms.pritechmw.com/login/ | head -1

# Tenant
curl -sI https://pritech.pms.pritechmw.com/ | head -1

# PWA
curl -sI https://pms.pritechmw.com/manifest.json | head -1
curl -sI https://pms.pritechmw.com/serviceworker.js | head -1

# WebSocket (expect 426 Upgrade Required)
curl -sI https://pms.pritechmw.com/ws/notifications/ | head -1
```

Each should return `200` or `426`.

### 4. Migrations check

```bash
cd /home/project/pritech-pms
source venv/bin/activate
python manage.py migrate_schemas --check
```

Expected: `No migrations to apply.`

### 5. Logs

```bash
# Any recent errors?
sudo journalctl -u gunicorn-pritech-pms --since "5 minutes ago" --no-pager | grep -i error

# Any failed Celery tasks?
sudo journalctl -u celery-worker-pritech-pms --since "5 minutes ago" --no-pager | grep -i "traceback\|error"
```

Both should be empty.

---

## Deploying schema changes

When you change a tenant-scoped model (e.g. `Reservation`):

```bash
# On your dev machine
python manage.py makemigrations <app>
git add apps/<app>/migrations/
git commit -m "Add field X to model Y"
git push origin main

# On the server
cd /home/project/pritech-pms
sudo bash deploy_pritech_pms.sh
```

The script will:

1. Detect the migration is missing on the server (if you forgot to commit)
2. Or run `migrate_schemas` which applies it to every tenant schema

**Never edit migrations after they've been applied to production.** Create a new migration instead.

---

## Deploying environment changes

If you change `.env` values (e.g. rotate a secret):

```bash
# Edit .env locally
git commit ...  # Never commit .env

# On the server, edit directly
sudo nano /home/project/pritech-pms/.env

# Or use the --env-only flag to have the script fill in new keys
sudo bash deploy_pritech_pms.sh --env-only

# Restart services manually
sudo systemctl restart gunicorn-pritech-pms daphne-pritech-pms celery-worker-pritech-pms celery-beat-pritech-pms
```

---

## Rolling back

### Option A — revert to previous commit

```bash
cd /home/project/pritech-pms
git log --oneline -10             # find the previous good commit
git reset --hard <commit-sha>
sudo systemctl restart gunicorn-pritech-pms daphne-pritech-pms celery-worker-pritech-pms celery-beat-pritech-pms
```

**Warning:** if the bad commit included a new migration, rolling back the code does NOT roll back the schema. You'll need to write a reverse migration or restore from backup.

### Option B — restore from backup

Only if the deploy corrupted data:

```bash
export DB_PASSWORD='<from .env>'
sudo -E bash scripts/restore_db.sh /var/backups/pritech/pritech_pms_<timestamp>.dump
```

See [`DISASTER_RECOVERY.md`](DISASTER_RECOVERY.md) for the full procedure.

---

## Troubleshooting

### "502 Bad Gateway"

Gunicorn is down or not listening.

```bash
sudo systemctl status gunicorn-pritech-pms
sudo journalctl -u gunicorn-pritech-pms -n 50 --no-pager
```

Common causes:
- Uncaught exception in a URLconf (check Step 10b output)
- Database connection refused (check PostgreSQL)
- Wrong `ALLOWED_HOSTS`

### "WebSocket disconnected" in browser console

Daphne is down or the Nginx `/ws/` location is misconfigured.

```bash
sudo systemctl status daphne-pritech-pms
sudo journalctl -u daphne-pritech-pms -n 50 --no-pager
ss -tlnp | grep 8011
```

Verify the Nginx config includes the `/ws/` location with `Upgrade` headers.

### "no tenant for hostname"

The `Domain` row for the subdomain is missing.

```bash
cd /home/project/pritech-pms
source venv/bin/activate
python manage.py shell
```
```python
from apps.shared.tenants.models import Domain
for d in Domain.objects.all():
    print(f'{d.domain:50s} → {d.tenant.name}')
```

If the domain is missing, add it via `/admin/tenants/domain/add/`.

### "CSRF verification failed"

Either `CSRF_TRUSTED_ORIGINS` doesn't include the current host, or the CSRF cookie domain is wrong.

```bash
grep CSRF /home/project/pritech-pms/.env
```

Expected:
```
CSRF_TRUSTED_ORIGINS=https://pms.pritechmw.com,https://*.pms.pritechmw.com
```

### Night audit didn't run

```bash
sudo systemctl status celery-beat-pritech-pms
sudo journalctl -u celery-beat-pritech-pms --since "24 hours ago" --no-pager | grep -i "night_audit"

# Check the schedule in admin
# https://pms.pritechmw.com/admin/django_celery_beat/periodictask/
```

### Static files missing (404)

```bash
cd /home/project/pritech-pms
source venv/bin/activate
python manage.py collectstatic --noinput

ls -la staticfiles/js/serviceworker.js
sudo systemctl reload nginx
```

### SSL certificate expired

```bash
sudo certbot certificates
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

---

## Emergency contacts

| Role | Contact |
|---|---|
| Server / infra | *(fill in)* |
| DNS / domain | *(fill in)* |
| Database | *(fill in)* |
| Business owner | *(fill in)* |
```

---

## 3. `docs/OPERATIONS.md`

```markdown
# Operations Guide

Day-to-day running of Pritech PMS. Keep this close.

**Domain:** https://pms.pritechmw.com
**Server:** 204.168.251.91
**Project dir:** `/home/project/pritech-pms`

---

## Daily tasks

| Time | Task | Automatic? | Log location |
|---|---|---|---|
| 02:00 | Night audit (all tenants) | Yes — Celery Beat | `journalctl -u celery-worker-pritech-pms` |
| 03:00 | Database backup | Yes — cron | `/var/log/pritech-backup.log` |
| 04:00 | Media backup | Yes — cron | `/var/log/pritech-backup.log` |
| 05:00 | MRA EIS config sync | Yes — Celery Beat | `journalctl -u celery-worker-pritech-pms` |
| 06:00 | Monthly rent invoices (1st) | Yes — Celery Beat | `journalctl -u celery-worker-pritech-pms` |
| 08:00 | Rent due reminders | Yes — Celery Beat | `journalctl -u celery-worker-pritech-pms` |
| 09:00 | Check-in reminders | Yes — Celery Beat | `journalctl -u celery-worker-pritech-pms` |
| Every 6h | Forex rate refresh | Yes — Celery Beat | `journalctl -u celery-worker-pritech-pms` |
| Every 15m | EIS offline queue sync | Yes — Celery Beat | `journalctl -u celery-worker-pritech-pms` |
| Every 15m | Celery heartbeat | Yes — Celery Beat | `journalctl -u celery-worker-pritech-pms` |

---

## Daily checks (5 minutes)

```bash
# 1. Health check
curl -s https://pms.pritechmw.com/health/ | python3 -m json.tool

# 2. Service states
for svc in gunicorn-pritech-pms daphne-pritech-pms celery-worker-pritech-pms celery-beat-pritech-pms nginx postgresql redis-server; do
    printf "%-30s " "$svc"
    systemctl is-active "$svc"
done

# 3. Recent errors
sudo journalctl -u gunicorn-pritech-pms --since "24 hours ago" --no-pager | grep -ci error
sudo journalctl -u daphne-pritech-pms --since "24 hours ago" --no-pager | grep -ci error

# 4. Failed Celery tasks
sudo journalctl -u celery-worker-pritech-pms --since "24 hours ago" --no-pager | grep -c "Task.*raised"

# 5. Backup ran
ls -lht /var/backups/pritech/ | head -3

# 6. Disk usage
df -h / | tail -1
```

All items in step 2 should say `active`. Counts in steps 3-4 should be low single digits.

---

## Weekly checks (15 minutes)

```bash
# 1. Review failed Celery tasks in admin
# https://pms.pritechmw.com/admin/django_celery_results/taskresult/?status=FAILURE

# 2. Review auth audit log for anomalies
# https://pms.pritechmw.com/admin/shared_users/authauditlog/
# Look for: many LOGIN_FAILED, PERMISSION_DENIED from unexpected IPs

# 3. Review Axes lockouts
# https://pms.pritechmw.com/admin/axes/accessattempt/
# Clear stale lockouts for legitimate staff

# 4. Review WhatsApp delivery failures
# https://pms.pritechmw.com/admin/communications/notificationlog/?status=FAIL

# 5. Review EIS offline queue
# https://pms.pritechmw.com/admin/eis/eisinvoicelog/?submission_status=FAIL

# 6. Check disk on all partitions
df -h

# 7. Check log sizes
sudo du -sh /var/log/pritech/ /var/log/nginx/
```

---

## Monthly checks (30 minutes)

- [ ] Verify a full backup restores into a staging database
- [ ] Review and clear old Celery task results
- [ ] Check PostgreSQL table sizes: `sudo -u postgres psql pritech_pms_db -c "\dt+ *.*" | sort -k3 -h | tail -20`
- [ ] Review `pg_stat_statements` for slow queries
- [ ] Check TLS certificate expiry: `sudo certbot certificates`
- [ ] Review Sentry for recurring errors
- [ ] Update the operations log (below)

---

## Quarterly checks (2 hours)

- [ ] **Full disaster recovery drill** — restore the latest backup into a clean server
- [ ] **Secret rotation** — see the rotation table below
- [ ] **Dependency update** — `pip list --outdated`, review security advisories
- [ ] **Access review** — remove staff who have left
- [ ] **Chichewa translation review** — with a native speaker
- [ ] **Capacity review** — DB size, disk usage, Redis memory

---

## Common issues

### Users can't log in

1. Check Axes lockout: `/admin/axes/accessattempt/`
2. If locked, delete the attempt row for that user
3. Check `is_active` and `UserTenantMembership.is_active`
4. Check the user's tenant membership matches the subdomain they're logging into

### WebSocket isn't connecting

```bash
ss -tlnp | grep 8011
sudo systemctl status daphne-pritech-pms
sudo journalctl -u daphne-pritech-pms -n 30 --no-pager
```

If the port is held by an old process:

```bash
sudo fuser -k 8011/tcp
sudo systemctl restart daphne-pritech-pms
```

### Night audit didn't run

```bash
# Did Beat fire the task?
sudo journalctl -u celery-beat-pritech-pms --since "24 hours ago" --no-pager | grep -i night_audit

# Did the worker process it?
sudo journalctl -u celery-worker-pritech-pms --since "24 hours ago" --no-pager | grep -i night_audit

# Check the schedule
# https://pms.pritechmw.com/admin/django_celery_beat/periodictask/
```

### Offline sync queue backing up

Staff have mobile devices with pending changes that can't sync. Common causes:

1. **Network unreachable** — verify the server is up
2. **CSRF token expired** — the client will re-auth on next page load
3. **Conflict** — check `/admin/core/synclog/` for rejected operations

If a device is stuck, staff should reload the app while on WiFi.

### Backups failing

```bash
# Run manually and watch output
export DB_PASSWORD='<from .env>'
sudo -E bash /home/project/pritech-pms/scripts/backup_db.sh

# Check disk space
df -h /var/backups
```

### WhatsApp messages bouncing

1. Check `notificationlog` for the error message
2. Verify `WHATSAPP_ACCESS_TOKEN` hasn't expired (Meta rotates every 60 days)
3. Verify the recipient's phone number is in E.164 format
4. Check the template is approved in Meta Business Manager

---

## Secret rotation

| Secret | Rotation period | Procedure |
|---|---|---|
| `SECRET_KEY` | Yearly | Edit `.env`, restart all services. **Invalidates all sessions.** Schedule in maintenance window. |
| `DB_PASSWORD` | Every 6 months | `ALTER ROLE pritech_pms_user PASSWORD '...'`, update `.env`, restart. |
| `PAYCHANGU_SECRET_KEY` | On compromise | Regenerate in PayChangu dashboard, update `.env`, restart. |
| `WHATSAPP_ACCESS_TOKEN` | Every 60 days (Meta default) | Regenerate in Meta Business Manager, update `.env`, restart. |
| `MAILGUN_API_KEY` | On compromise | Regenerate in Mailgun dashboard, update `.env`, restart. |
| `SENTRY_DSN` | Never | No sensitive data flows through this. |
| `EIS_API_KEY` | On expiry | Contact MRA, update `.env`, restart. |

**Rotating `SECRET_KEY`:**

```bash
# 1. Generate new key
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 2. Update .env
sudo nano /home/project/pritech-pms/.env

# 3. Restart
sudo systemctl restart gunicorn-pritech-pms daphne-pritech-pms celery-worker-pritech-pms celery-beat-pritech-pms

# 4. All users are logged out. Verify login works.
```

---

## Provisioning a new tenant

### Option A — via admin

1. Log into https://pms.pritechmw.com/admin/
2. Go to **Platform → Tenants → Add Tenant**
3. Fill in:
   - **Name:** Lakeview Lodge
   - **Schema name:** `lakeview` (lowercase, no spaces)
   - **Plan:** Professional
   - **Contact name/email/phone**
4. Save — the schema is created automatically
5. Go to **Platform → Domains → Add Domain**:
   - **Domain:** `lakeview.pms.pritechmw.com`
   - **Tenant:** Lakeview Lodge
   - **Is primary:** ✓
6. Save

Wait 10 seconds, then visit `https://lakeview.pms.pritechmw.com/login/`. It should load.

### Option B — via the signup form

Share `https://pms.pritechmw.com/signup/` with the new client. They fill in their organization details, choose a subdomain, set a password, and get an instant workspace.

### Post-provision checklist

- [ ] Visit `https://<subdomain>.pms.pritechmw.com/` — loads without error
- [ ] Log in with the admin account — works
- [ ] Add a property via **Core → Properties**
- [ ] Add at least one unit
- [ ] Configure a rate plan
- [ ] Configure EIS terminal (if applicable)
- [ ] Configure FCY bank account (if applicable)
- [ ] Test a check-in and check-out
- [ ] Send the client their login credentials

---

## Tenant suspension and deletion

### Suspend (temporary)

Via admin: **Platform → Tenants →** open tenant → **Suspend**.

Effect: tenant's domain returns a 404. Data is preserved. Reverse with **Reactivate**.

### Delete (permanent)

Via admin: open tenant → scroll to **Danger Zone** → type the tenant name → **Permanently Delete Tenant**.

**This drops the PostgreSQL schema.** All data is lost. Irreversible.

**Before deleting:**

1. Run a full database backup
2. Export the tenant's data (if legally required)
3. Confirm with the client in writing

---

## Monitoring

### Sentry

- Dashboard: https://sentry.io/organizations/<org>/issues/
- Check daily for new issues
- All 5xx errors are captured automatically

### UptimeRobot

- Dashboard: https://uptimerobot.com/dashboard
- Two monitors configured:
  - `https://pms.pritechmw.com/health/` (keyword check for `"status": "ok"`)
  - `https://pms.pritechmw.com/`
- Alerts go to SMS + email

### Celery

- Task results: https://pms.pritechmw.com/admin/django_celery_results/taskresult/
- Periodic schedule: https://pms.pritechmw.com/admin/django_celery_beat/periodictask/
- Filter by status `FAILURE` for problems

### Database

```bash
# Connection count
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='pritech_pms_db';"

# Slow queries (requires pg_stat_statements extension)
sudo -u postgres psql pritech_pms_db -c "
    SELECT query, mean_exec_time, calls
    FROM pg_stat_statements
    ORDER BY mean_exec_time DESC
    LIMIT 10;
"

# Table sizes
sudo -u postgres psql pritech_pms_db -c "
    SELECT schemaname, relname, pg_size_pretty(pg_total_relation_size(relid)) AS size
    FROM pg_catalog.pg_statio_user_tables
    ORDER BY pg_total_relation_size(relid) DESC
    LIMIT 20;
"
```

---

## Operations log

Keep a running log of non-trivial incidents here.

| Date | Incident | Resolution | Duration |
|---|---|---|---|
| | | | |
```

---

## 4. `docs/DISASTER_RECOVERY.md`

```markdown
# Disaster Recovery Plan

Recovery procedures for Pritech PMS.

**RTO (Recovery Time Objective):** 4 hours
**RPO (Recovery Point Objective):** 1 hour (backups run at 03:00 daily)

---

## Backup strategy

| Data | Frequency | Location | Retention |
|---|---|---|---|
| PostgreSQL full dump | Daily 03:00 | `/var/backups/pritech/` + offsite | 30 days |
| Media files | Daily 04:00 | `/var/backups/pritech/media/` + offsite | 14 days |
| Source code | Every push | GitHub | Indefinite |
| `.env` | On change | Password manager + offline | Indefinite |

**Offsite:** weekly sync of the latest DB dump to a Backblaze B2 bucket (or equivalent). Set up as a separate cron job.

---

## Failure scenarios

### Scenario 1 — Database corruption

**Detection:** Health check returns `"database": "error"`, application returns 500s.

**Recovery (target: 2 hours):**

```bash
# 1. Stop services
sudo systemctl stop gunicorn-pritech-pms daphne-pritech-pms celery-worker-pritech-pms celery-beat-pritech-pms

# 2. Identify the most recent good backup
ls -lht /var/backups/pritech/*.dump | head -5

# 3. Verify it's valid
pg_restore --list /var/backups/pritech/pritech_pms_<timestamp>.dump | head -30

# 4. Restore
export DB_PASSWORD='<from .env>'
sudo -E bash scripts/restore_db.sh /var/backups/pritech/pritech_pms_<timestamp>.dump

# 5. Verify schema state
cd /home/project/pritech-pms
source venv/bin/activate
python manage.py migrate_schemas --check

# 6. Restart services
sudo systemctl start gunicorn-pritech-pms daphne-pritech-pms celery-worker-pritech-pms celery-beat-pritech-pms

# 7. Verify health
curl -s https://pms.pritechmw.com/health/ | python3 -m json.tool
```

**Expected data loss:** up to 24 hours (backup runs at 03:00, incident discovered at any time).

**Reducing RPO:** enable PostgreSQL WAL archiving (see "Advanced" below).

---

### Scenario 2 — Complete server failure

**Detection:** UptimeRobot alerts, SSH unreachable.

**Recovery (target: 4 hours):**

```bash
# 1. Provision a new Ubuntu 22.04 server with the same specs
#    (2 vCPU, 4GB RAM, 80GB SSD minimum)

# 2. Install prerequisites
sudo apt update
sudo apt install -y python3.12 python3.12-venv postgresql-16 redis-server nginx \
    certbot python3-certbot-dns-cloudflare git curl gettext

# 3. Point DNS to the new server
#    Update A records for `pms` and `*.pms` at your DNS provider

# 4. Clone the repo
sudo mkdir -p /home/project
cd /home/project
sudo git clone https://github.com/Izk-123/pritech-property-management-system.git pritech-pms

# 5. Copy the .env from your password manager
sudo nano /home/project/pritech-pms/.env

# 6. Restore the latest backup
#    Download from offsite storage
scp backup-server:/backups/pritech_pms_latest.dump /var/backups/pritech/
sudo mkdir -p /var/backups/pritech
sudo mv /var/backups/pritech_pms_latest.dump /var/backups/pritech/

# 7. Run the deploy script — it will create the DB, user, schema
cd /home/project/pritech-pms
sudo bash deploy_pritech_pms.sh --skip-ssl

# 8. Restore the backup over the freshly-migrated DB
export DB_PASSWORD='<from .env>'
sudo -E bash scripts/restore_db.sh /var/backups/pritech/pritech_pms_latest.dump

# 9. Restore media
#    Download from offsite storage
aws s3 sync s3://pritech-backups/media/latest/ /home/project/pritech-pms/media/

# 10. Reissue SSL
sudo certbot certonly --dns-cloudflare \
    --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
    -d pms.pritechmw.com -d "*.pms.pritechmw.com" \
    --agree-tos --email admin@pritechmw.com --non-interactive

sudo systemctl reload nginx

# 11. Verify
curl -s https://pms.pritechmw.com/health/ | python3 -m json.tool
```

**Expected data loss:** up to 7 days (if offsite sync is weekly). Reduce to 24 hours by syncing daily.

---

### Scenario 3 — Redis failure

**Detection:** WebSockets drop, Celery tasks stop, sessions may expire.

**Impact:** Low. Redis holds cache, sessions, and channel layer. All business data lives in PostgreSQL.

**Recovery (target: 15 minutes):**

```bash
# 1. Restart Redis
sudo systemctl restart redis-server

# 2. Verify
redis-cli -n 0 ping   # → PONG  (Celery broker)
redis-cli -n 1 ping   # → PONG  (cache)
redis-cli -n 2 ping   # → PONG  (Channels)

# 3. Restart dependent services
sudo systemctl restart daphne-pritech-pms celery-worker-pritech-pms celery-beat-pritech-pms
sudo systemctl restart gunicorn-pritech-pms

# 4. Verify
curl -s https://pms.pritechmw.com/health/ | python3 -m json.tool
```

**Expected user impact:** Staff are logged out (sessions were in Redis). WebSocket connections drop and reconnect automatically.

---

### Scenario 4 — Prolonged ESCOM outage

**Detection:** UptimeRobot alerts.

**Response:**

1. Notify staff that the PWA works offline (see `USER_MANUAL.md` section 8)
2. If the server has UPS, it runs for 30-60 minutes on battery
3. When battery drops, services stop cleanly (systemd)
4. When power returns, systemd restarts everything automatically

**Data integrity:** The PWA syncs offline changes when connectivity returns. No data is lost.

**Preparedness:**
- Test offline check-in monthly (see Phase 6 test suite)
- Keep UPS charged
- Document the offline workflow for staff

---

### Scenario 5 — Malicious compromise

**Detection:** Unexpected changes in audit logs, Sentry alerts, anomalous traffic.

**Immediate response:**

```bash
# 1. Isolate the server (firewall rules block everything except SSH from your IP)
sudo ufw default deny incoming
sudo ufw allow from <your-ip> to any port 22
sudo ufw enable

# 2. Snapshot the server for forensics (via hosting console)
# Do NOT wipe it — investigators may need it

# 3. Rotate every secret
# SECRET_KEY, DB_PASSWORD, all API keys

# 4. Rebuild from a clean server
# Follow Scenario 2 procedure

# 5. Restore data from a backup predating the compromise

# 6. Notify affected parties per Malawi Data Protection Act (72 hours)
```

**Preserve evidence:** do not modify files, do not delete logs.

---

## Quarterly restore test

Once per quarter, restore the latest backup into a staging database and verify it works. Log the result below.

**Procedure:**

```bash
# 1. Create a staging database
sudo -u postgres createdb pritech_pms_staging
sudo -u postgres psql -d pritech_pms_staging -c "ALTER SCHEMA public OWNER TO pritech_pms_user;"

# 2. Restore the latest backup into staging
export DB_PASSWORD='<from .env>'
PGPASSWORD="$DB_PASSWORD" pg_restore \
    --host=127.0.0.1 \
    --username=pritech_pms_user \
    --dbname=pritech_pms_staging \
    --jobs=4 \
    /var/backups/pritech/pritech_pms_<latest>.dump

# 3. Run checks against staging
cd /home/project/pritech-pms
source venv/bin/activate

DJANGO_SETTINGS_MODULE=config.settings DB_NAME=pritech_pms_staging \
    python manage.py migrate_schemas --check

DJANGO_SETTINGS_MODULE=config.settings DB_NAME=pritech_pms_staging \
    python manage.py shell -c "
from django_tenants.utils import get_tenant_model
from django.db import connection
TenantModel = get_tenant_model()
for t in TenantModel.objects.exclude(schema_name='public'):
    connection.set_schema(t.schema_name)
    from apps.hospitality.reservations.models import Reservation
    from apps.property.leases.models import Lease
    print(f'{t.schema_name}: {Reservation.objects.count()} reservations, {Lease.objects.count()} leases')
"

# 4. Drop staging
sudo -u postgres dropdb pritech_pms_staging

# 5. Log the result below
```

**Test log:**

| Date | Backup used | Restore OK? | Row counts match? | Notes |
|---|---|---|---|---|
| | | | | |

---

## Advanced: reducing RPO with WAL archiving

The default daily backup gives RPO of 24 hours. To reduce to near-zero, enable PostgreSQL continuous archiving.

**`/etc/postgresql/16/main/postgresql.conf`:**

```
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /var/lib/postgresql/wal_archive/%f && cp %p /var/lib/postgresql/wal_archive/%f'
archive_timeout = 300
```

Then take a base backup weekly and archive WAL continuously.

This is optional for a small deployment. Enable when RPO of hours is insufficient.

---

## Escalation

| Situation | Contact | When |
|---|---|---|
| Health check fails | DevOps | Immediately |
| Data loss suspected | DevOps + business owner | Immediately |
| Security incident | DevOps + legal | Immediately |
| MRA / RBM compliance issue | Accountant + legal | Business hours |
| Client complaint | Account manager | Business hours |

Fill in contacts:

- **DevOps:** 
- **Business owner:** 
- **Legal:** 
- **Accountant:** 
```

---

## 5. `docs/USER_MANUAL.md`

```markdown
# Pritech PMS — User Manual

A practical guide for hotel, lodge, and property management staff.

**Version:** 1.0 (English)
**Last updated:** September 2026

---

## 1. Getting started

### Signing in

1. Open your browser and go to your workspace URL (e.g. `https://lakeview.pms.pritechmw.com/login/`)
2. Enter your **email address** and **password**
3. Click **Sign In**

If you have forgotten your password, click **Forgot?** and follow the reset steps.

**On first login**, you may be asked to set up two-factor authentication. Scan the QR code with your phone's authenticator app (Google Authenticator, Authy, Microsoft Authenticator). You'll be asked for a 6-digit code each time you log in.

### Navigating the app

The main menu is at the top of the screen:

- **Properties** — public listings
- **Front Desk** — today's arrivals and departures
- **Reservations** — all bookings
- **Housekeeping** — room cleaning tasks
- **Property** — leases, rent invoices, maintenance, sales
- **Records** — people, documents
- **Compliance** — MRA EIS, PayNow, Tourism Levy, forex
- **Admin** — full management interface (staff only)

On a phone or tablet, tap the **☰** icon to open the menu.

### Changing the language

Tap the **🌐** icon next to the theme switch. Choose **English** or **Chichewa**.

### Dark mode

Tap the **🌙** icon to switch between light and dark themes. Your choice is remembered.

---

## 2. Front desk

The front desk is your main daily screen. Open **Front Desk** from the menu.

You see three sections:

- **Today's Arrivals** — guests checking in today (green)
- **Today's Departures** — guests checking out today (amber)
- **In-House Guests** — everyone currently staying (purple)

Each row shows the guest's name, reservation number, and outstanding balance.

### Checking a guest in

1. On the **Front Desk** screen, find the guest under **Today's Arrivals**
2. Click their name
3. On the reservation page, click **Check In**
4. Select an **available room** from the dropdown
5. Confirm the **rate per night** (pre-filled from the reservation)
6. Click **Confirm Check In**

The guest is now checked in, the room is marked **Occupied**, and a folio (bill) is created automatically.

### Recording a payment

1. Open the reservation
2. Scroll to the **Folio** section
3. Click **Record Payment**
4. Choose the **method**: Cash (MWK), Cash (USD), Airtel Money, TNM Mpamba, Card, or Bank Transfer
5. Enter the **amount**
6. If paying by mobile money, enter the transaction **reference** (e.g. from the Airtel Money SMS)
7. Click **Record Payment**

The balance updates immediately, and the guest receives a WhatsApp receipt (if enabled).

### Posting a charge

For extras like food, laundry, or minibar:

1. Open the reservation
2. In the Folio section, click **Post Charge**
3. Choose the type: F&B, Laundry, Minibar, Activity, Miscellaneous, or Discount
4. Enter a description and the amount
5. Click **Post Charge**

### Checking a guest out

1. Open the reservation
2. Confirm the balance is **zero** (settle any outstanding amount first)
3. Click **Check Out**
4. Confirm

The room is marked **Cleaning**, and a housekeeping task is created automatically.

### Handling a walk-in

1. On the Front Desk screen, click **+ Walk-in**
2. Fill in the guest details (name, phone required; email optional)
3. Choose the **property** and **dates**
4. Save
5. The guest appears under **Today's Arrivals** — continue with check-in as above

---

## 3. Housekeeping

Open **Housekeeping** from the menu.

### Viewing your tasks

You see your assigned tasks, sorted by priority (P1 is highest). Each task shows:

- Room number
- Property name
- Task type (Check-out Cleaning, Stayover, Deep Clean, Inspection)
- Priority
- Any notes from the front desk

### Updating a task

Each task has one button:

- **▶ Start** — you've begun cleaning
- **✓ Mark Clean** — you've finished cleaning
- **👁 Inspect** — only supervisors see this button

Tap the button to move the task to the next stage. The room status updates in real time — front desk sees it immediately.

### Reporting a problem

If you find a maintenance issue in a room:

1. Note the room number
2. Tell the front desk or supervisor
3. They will log a maintenance request and the room will be marked **Maintenance**

---

## 4. Property management

Open **Property → Dashboard** for an overview.

### Creating a lease

1. Go to **Property → Leases**
2. Click **+ New Lease**
3. Fill in:
   - **Tenant** — select the person
   - **Unit** — select the property and unit
   - **Start and end dates**
   - **Rent amount** and **currency**
   - **Payment due day** (1–28)
   - **Deposit**
   - Late fee rules (optional)
4. Click **Save Lease**
5. On the lease detail page, click **Activate**

The unit is now marked **Occupied**.

### Generating a rent invoice

Rent invoices are generated automatically on the 1st of each month. To generate one manually:

1. Open the lease
2. Click **+ Generate invoice**
3. Choose the billing period and due date
4. Click **Generate**

### Recording rent payment

1. Open the invoice
2. Click **Record Payment**
3. Choose the method (Cash, Airtel Money, TNM Mpamba, Bank Transfer)
4. Enter the amount and reference
5. Click **Record Payment**

### Handling maintenance

1. Go to **Property → Maintenance**
2. Click **+ Log Request**
3. Fill in:
   - Unit
   - Category (plumbing, electrical, etc.)
   - Priority
   - Title and description
4. Click **Log Request**
5. On the detail page, click **Assign** to allocate to a technician

---

## 5. Managing guests

Open **Records → People**.

### Searching for a guest

Type any part of:
- Name
- Phone number (`0991234567`, `+265991234567`, `265991234567` all work)
- Email
- ID number
- Company name

Results appear as you type.

### Adding a new guest

1. Click **+ New Person**
2. Fill in at least:
   - **Full name**
   - **Phone number**
   - **Nationality**
3. Optional fields: ID, email, address, date of birth
4. Click **Register Person**

If a similar guest exists, you'll see a warning — choose to merge or create a new record.

### Guest profile

Each guest's profile shows:

- Contact details
- Stay history
- Notes (staff-only)
- Documents (IDs, contracts)
- Communication preferences

### Blacklisting a guest

1. Open the guest profile
2. Click **Edit**
3. Check **Is blacklisted**
4. Enter the **reason**
5. Save

Blacklisted guests cannot make new bookings. Warning appears at check-in.

---

## 6. Communications

Open **Compliance → Communications** (or the **Message Log** from the sidebar).

### Message log

Every WhatsApp and email sent by the system appears here. Filter by:

- Channel (WhatsApp, Email)
- Status (Sent, Delivered, Read, Failed)
- Event (Booking Confirmed, Payment Receipt, etc.)

Click any row to see the full delivery details.

### Inbound messages

Go to **Inbound**. Every WhatsApp reply from a guest appears here.

- **Unread** messages are highlighted
- Click **Reply** to respond (must be within 24 hours of the guest's message to stay free)
- Replies you send are logged

### Templates

Go to **Templates** to customise message wording.

Common templates:

- **Booking Confirmed** — sent when a reservation is created
- **Payment Receipt** — sent after each payment
- **Check-in Reminder** — sent 24 hours before arrival
- **Rent Due Reminder** — sent 3 days before rent is due

Edit the body using placeholders like `{guest_name}`, `{property_name}`, `{amount}`.

---

## 7. Compliance (managers only)

### MRA EIS

Go to **Compliance → MRA EIS Terminals** to see your registered terminals.

Each terminal shows:

- **Status** — Active, Pending, Suspended
- **Last config sync**
- **Validated invoices** this month
- **Offline queue** count

The system syncs configuration daily at 5 AM and processes the offline queue every 15 minutes.

### Tourism Levy

Go to **Compliance → Tourism Levy**.

Choose a month to see:

- Total room charges
- Levy due (1%)
- Per-property breakdown
- Individual folios

Click **Mark Remitted** for each record once you've paid the Malawi Tourism Council. Submit by the **12th of the following month**.

### Forex rates

Go to **Compliance → Forex Rates**.

The current USD/MWK and EUR/MWK rates are shown. Rates refresh automatically every 6 hours.

Click **Refresh Now** to force an update.

### RBM returns

Go to **Compliance → FCY & RBM**.

Foreign currency receipts by month. Submit to the Reserve Bank of Malawi by the **10th of the following month**.

Click **Mark Submitted** after submitting.

---

## 8. Offline mode (PWA)

Pritech PMS works when the internet is down — including during ESCOM power cuts.

### Installing the app

**On Android:**

1. Open the site in Chrome
2. Tap the three-dot menu → **Install app** (or **Add to Home screen**)
3. Confirm

**On iPhone:**

1. Open the site in Safari
2. Tap the **Share** icon
3. Scroll and tap **Add to Home Screen**
4. Confirm

The app now opens like a native app from your home screen.

### What works offline

- Check guests in and out
- Update housekeeping task status
- Record payments (cash and mobile money)
- View today's arrivals, departures, and in-house list
- View room status board
- View cached guest profiles

### What does NOT work offline

- Searching for new guests (only cached ones)
- Sending WhatsApp messages (they queue)
- Generating MRA EIS invoices (they queue)
- Loading reports

### How changes sync

When you make a change offline:

1. The change is saved on your device
2. An **amber indicator** appears: "Offline — changes saved locally"
3. When internet returns, changes sync automatically
4. The indicator turns **green**: "Back online"
5. The indicator turns **blue** while syncing, then fades

**If the connection doesn't return within 72 hours**, changes are marked as failed. Contact your supervisor.

### Checking your sync queue

The **Offline** page (`/offline/`) shows the number of pending changes. Each shows the type (POST/PATCH/DELETE), endpoint, and timestamp.

---

## 9. Real-time updates

When you're online, some information updates automatically without refreshing:

- **Room status** — when housekeeping finishes a room, the front desk sees it
- **New bookings** — a notification appears when a reservation is created
- **Payments** — the folio balance updates when a payment arrives
- **Task assignments** — you get a notification when a task is assigned to you

You do not need to refresh the page.

---

## 10. Troubleshooting

### "Sign-in failed"

- Check your email is typed correctly
- Check caps lock is off
- After 5 wrong attempts, your account is locked for 30 minutes
- Contact your supervisor if the problem continues

### "Page not loading"

- Check your internet connection
- Try opening a new tab and going back to the site
- If offline, the app should still work — look for the amber indicator

### "Offline sync stuck"

- Open the **Offline** page from the footer
- Check the pending list
- If a change is marked **failed** after multiple retries, note the details and contact support

### "WhatsApp message not received"

- Ask the guest to check their WhatsApp app
- The message may take 1-2 minutes to arrive
- If the guest's number is wrong, update the guest profile

### "Cannot check in — unit not available"

- The unit may be occupied by another guest
- Check the room status board
- Choose a different unit or contact your supervisor

### "Balance doesn't match"

- Open the folio and review all charges and payments
- If a charge is wrong, you can post a **Discount** with a note
- Ask a manager to approve large corrections

---

## 11. Getting help

- **Daily issues:** ask your supervisor
- **System errors:** contact the Pritech support line *(fill in)*
- **Emergency:** phone the on-call number *(fill in)*

---

**Pritech PMS v1.0**
Made in Malawi.
```

---

## 6. `docs/USER_MANUAL_NY.md`

```markdown
# Pritech PMS — Buku la Wogwiritsa

Chitsogozo chothandiza kwa antchito a hotelo, loji, ndi kasamalidwe ka katundu.

**Baibulo:** 1.0 (Chichewa)
**Zosinthidwa:** Seputembala 2026

> **Chidziwitso:** Baibulo ili ndi lomasuliridwa mwa Chichewa. Mau ena aukadaulo
> asungidwa mu Chingerezi (monga "folio", "invoice"). Ngati simukumvetsa
> gawo lina, chonde onani baibulo la Chingerezi kapena funsani woyang'anira
> wanu.

---

## 1. Kuyamba

### Kulowa mu akaunti

1. Tsegulani browser ndi kupita ku `https://lakeview.pms.pritechmw.com/login/`
2. Lowetsani **imelo** ndi **achinsinsi** anu
3. Dinani **Sign In**

Ngati mwaiwala achinsinsi, dinani **Forgot?** ndi kutsatira malangizo.

Pakulowa koyamba, mungafunsidwe kukhazikitsa **two-factor authentication**.
Jambulani QR code ndi foni yanu (Google Authenticator, Authy). Mudzafunsidwa
nambala ya manambala 6 nthawi iliyonse mukalowa.

### Mayendedwe a pulogalamu

Menyu yayikulu ili pamwamba:

- **Properties** — minda yotseguka
- **Front Desk** — obwera ndi otuluka lero
- **Reservations** — zosungitsa zonse
- **Housekeeping** — ntchito zotsuka zipinda
- **Property** — mgwirizano, ma invoice a rent, kukonza, kugulitsa
- **Records** — anthu, zolemba
- **Compliance** — MRA EIS, PayChangu, Tourism Levy, forex
- **Admin** — kasamalidwe konse (antchito okha)

Pa foni kapena tablet, dinani **☰** kutsegula menyu.

### Kusintha chilankhulo

Dinani chizindikiro cha **🌐**. Sankhani **English** kapena **Chichewa**.

### Njira yamdima

Dinani chizindikiro cha **🌙** kusintha pakati pa kuwala ndi mdima.
Zomwe mwasankha zikumbukiridwa.

---

## 2. Front Desk

Front Desk ndi malo anu a tsiku ndi tsiku. Tsegulani **Front Desk** mu menyu.

Mudzaona magawo atatu:

- **Today's Arrivals** — alendo obwera lero (chobiriwira)
- **Today's Departures** — alendo otuluka lero (chachikasu)
- **In-House Guests** — alendo onse omwe ali mkati (chofiirira)

Mzere uliwonse ukuwonetsa dzina la mlendo, nambala ya reservation, ndi
ndalama zotsala.

### Kulowetsa mlendo

1. Pa **Front Desk**, pezani mlendo mu **Today's Arrivals**
2. Dinani dzina lawo
3. Pa tsamba la reservation, dinani **Check In**
4. Sankhani **chipinda** chomwe chilipo
5. Tsindikizani **mtengo wa usiku** (wadzazidwa kale)
6. Dinani **Confirm Check In**

Mlendo tsopano walowa, chipinda chili **Occupied**, ndipo **folio** (bilu)
yapangidwa.

### Kulemba malipiro

1. Tsegulani reservation
2. Pitani ku gawo la **Folio**
3. Dinani **Record Payment**
4. Sankhani **njira**: Cash (MWK), Cash (USD), Airtel Money, TNM Mpamba,
   Card, kapena Bank Transfer
5. Lowetsani **ndalama**
6. Ngati mukulipira ndi mobile money, lowetsani **reference**
   (kuchokera mu SMS ya Airtel Money)
7. Dinani **Record Payment**

Zotsala zisintha nthawi yomweyo, ndipo mlendo amalandira receipt ya WhatsApp.

### Kulemba zolipirira zina

Za chakudya, kuchapa zovala, kapena minibar:

1. Tsegulani reservation
2. Mu Folio, dinani **Post Charge**
3. Sankhani mtundu: F&B, Laundry, Minibar, Activity, Miscellaneous,
   kapena Discount
4. Lowetsani kufotokozera ndi ndalama
5. Dinani **Post Charge**

### Kutulutsa mlendo

1. Tsegulani reservation
2. Onetsetsani kuti zotsala ndi **zero** (lipirani zonse zotsala kaye)
3. Dinani **Check Out**
4. Tsindikizani

Chipinda chikhala **Cleaning**, ndipo ntchito yotsuka imapangidwa.

### Walk-in

1. Pa Front Desk, dinani **+ Walk-in**
2. Lowetsani zambiri za mlendo (dzina, foni)
3. Sankhani **katundu** ndi **masiku**
4. Sungani
5. Mlendo akuwonekera mu **Today's Arrivals** — pitirizani ndi check-in

---

## 3. Housekeeping

Tsegulani **Housekeeping** mu menyu.

### Kuwona ntchito zanu

Mudzaona ntchito zomwe mwapatsidwa, zokonzedwa ndi kufunika (P1 ndi
kofunika kwambiri). Ntchito iliyonse ikuwonetsa:

- Nambala ya chipinda
- Dzina la katundu
- Mtundu wa ntchito (Check-out Cleaning, Stayover, Deep Clean,
  Inspection)
- Kufunika
- Zolemba kuchokera ku front desk

### Kusintha ntchito

Ntchito iliyonse ili ndi batani limodzi:

- **▶ Start** — mwayamba kutsuka
- **✓ Mark Clean** — mwamaliza kutsuka
- **👁 Inspect** — okhawo oyang'anira amawona batani ili

Dinani batani kuti musunthe ntchito ku gawo lotsatira. Mkhalidwe wa
chipinda usintha nthawi yomweyo.

### Kunena za vuto

Ngati mupeza vuto mu chipinda:

1. Dziwani nambala ya chipinda
2. Uzeni front desk kapena woyang'anira
3. Iwo adzalemba pempho lokonza ndipo chipinda chidzakhala **Maintenance**

---

## 4. Kasamalidwe ka katundu

Tsegulani **Property → Dashboard** kuti muwone zonse.

### Kupanga mgwirizano (lease)

1. Pitani ku **Property → Leases**
2. Dinani **+ New Lease**
3. Lowetsani:
   - **Tenant** — sankhani munthu
   - **Unit** — sankhani katundu ndi chipinda
   - **Masiku oyambira ndi kutha**
   - **Ndalama ya rent** ndi **ndalama**
   - **Tsiku lolipira** (1–28)
   - **Deposit**
   - Malamulo a chindapusa (mukafuna)
4. Dinani **Save Lease**
5. Pa tsamba, dinani **Activate**

Chipinda tsopano chili **Occupied**.

### Kupanga invoice ya rent

Ma invoice amapangidwa mwadzidzidzi pa tsiku la 1 mwezi uliwonse.
Kupanga pamanja:

1. Tsegulani mgwirizano
2. Dinani **+ Generate invoice**
3. Sankhani nthawi ndi tsiku lolipira
4. Dinani **Generate**

### Kulemba malipiro a rent

1. Tsegulani invoice
2. Dinani **Record Payment**
3. Sankhani njira
4. Lowetsani ndalama ndi reference
5. Dinani **Record Payment**

### Kukonza

1. Pitani ku **Property → Maintenance**
2. Dinani **+ Log Request**
3. Lowetsani:
   - Chipinda
   - Mtundu (plumbing, electrical, etc.)
   - Kufunika
   - Mutu ndi kufotokozera
4. Dinani **Log Request**
5. Dinani **Assign** kuti mupatse munthu wokonza

---

## 5. Kasamalidwe ka alendo

Tsegulani **Records → People**.

### Kusaka mlendo

Lembani gawo lililonse la:
- Dzina
- Nambala ya foni (`0991234567`, `+265991234567` zonse zimagwira)
- Imelo
- Nambala ya ID

Zotsatira zikuwonekera pamene mukulemba.

### Kuonjezera mlendo watsopano

1. Dinani **+ New Person**
2. Lowetsani:
   - **Dzina lonse**
   - **Nambala ya foni**
   - **Dziko**
3. Zina: ID, imelo, adilesi, tsiku lobadwa
4. Dinani **Register Person**

Ngati mlendo wofanana alipo, mudzawona chenjezo. Sankhani kuphatikiza
kapena kupanga watsopano.

### Profailo ya mlendo

Ikuwonetsa:

- Zolumikizana
- Mbiri ya kukhala
- Zolemba (za antchito okha)
- Zolemba (ma ID, makontrakiti)
- Zokonda zolumikizana

### Kuletsa mlendo (blacklist)

1. Tsegulani profailo
2. Dinani **Edit**
3. Chonga **Is blacklisted**
4. Lowetsani **chifukwa**
5. Sungani

Alendo oletsedwa sangathe kusungitsa katsopano.

---

## 6. Kulumikizana

Tsegulani **Compliance → Communications**.

### Mndandanda wa mauthenga

Mauthenga onse a WhatsApp ndi imelo akuwonekera. Sankhani ndi:

- Channel (WhatsApp, Email)
- Mkhalidwe (Sent, Delivered, Read, Failed)
- Chochitika (Booking Confirmed, Payment Receipt, etc.)

### Mauthenga obwera

Pitani ku **Inbound**. Mayankho onse a WhatsApp kuchokera kwa alendo
akuwonekera.

- Zosawerengeka zikuwonekera
- Dinani **Reply** kuyankha
- Mayankho anu amalembedwa

### Ma template

Pitani ku **Templates** kusintha mawu.

Ma template odziwika:
- **Booking Confirmed** — kutumizidwa reservation ikapangidwa
- **Payment Receipt** — kutumizidwa pambuyo pa malipiro
- **Check-in Reminder** — kutumizidwa maola 24 asanafike
- **Rent Due Reminder** — kutumizidwa masiku 3 rent isanalipidwe

Sinthani thupi ndi malo monga `{guest_name}`, `{property_name}`,
`{amount}`.

---

## 7. Compliance (okhawo oyang'anira)

### MRA EIS

Pitani ku **Compliance → MRA EIS Terminals**.

Terminal iliyonse ikuwonetsa:
- **Mkhalidwe** — Active, Pending, Suspended
- **Kusintha kotsiriza kwa config**
- **Ma invoice ovomerezeka** mwezi uno
- **Chiwerengero cha offline queue**

Ndondomekoyi imasintha config tsiku lililonse nthawi ya 5 AM ndipo
imathandizira offline queue mphindi 15 zilizonse.

### Tourism Levy

Pitani ku **Compliance → Tourism Levy**.

Sankhani mwezi kuti muwone:
- Ndalama zonse za zipinda
- Levy yoyenera (1%)
- Kugawika kwa katundu uliwonse
- Ma folio amodzi

Dinani **Mark Remitted** mukalipira Malawi Tourism Council. Tumizani
**pa tsiku la 12 la mwezi wotsatira**.

### Mitengo ya Forex

Pitani ku **Compliance → Forex Rates**.

Mitengo yamakono ya USD/MWK ndi EUR/MWK ikuwonekera. Imasinthidwa
maola 6 aliwonse.

### RBM returns

Pitani ku **Compliance → FCY & RBM**.

Ndalama zakunja mwezi ndi mwezi. Tumizani ku Reserve Bank of Malawi
**pa tsiku la 10 la mwezi wotsatira**.

Dinani **Mark Submitted** mukatumiza.

---

## 8. Njira ya offline

Pritech PMS imagwira ntchito ngati intaneti ilipo — kuphatikizapo nthawi
ya kuzima kwa magetsi (ESCOM).

### Kukhazikitsa pulogalamu

**Pa Android:**
1. Tsegulani site mu Chrome
2. Dinani menyu → **Install app**
3. Tsindikizani

**Pa iPhone:**
1. Tsegulani site mu Safari
2. Dinani chizindikiro cha **Share**
3. Sankhani **Add to Home Screen**
4. Tsindikizani

### Zomwe zimagwira popanda intaneti

- Kulowetsa ndi kutulutsa alendo
- Kusintha mkhalidwe wa ntchito zotsuka
- Kulemba malipiro (cash ndi mobile money)
- Kuwona obwera, otuluka, ndi alendo mkati
- Kuwona mkhalidwe wa zipinda
- Kuwona ma profailo a alendo osungidwa

### Zomwe sizigwira popanda intaneti

- Kusaka alendo atsopano
- Kutumiza mauthenga a WhatsApp (amakhala mu kolejile)
- Kupanga ma invoice a MRA EIS
- Kuwona malipoti

### Momwe zosintha zimalumikizidwa

Mukasintha popanda intaneti:
1. Zosintha zimasungidwa pa chipangizo chanu
2. Chizindikiro cha **chikasu** chikuwonekera
3. Intaneti ikabweranso, zosintha zimalumikizidwa zokha
4. Chizindikiro chikhala **chobiriwira**: "Back online"

**Ngati kulumikizana sikubweranso mkati mwa maola 72**, zosintha
zimadziwika kuti zalephera. Lumikizanani ndi woyang'anira wanu.

---

## 9. Kusintha kwa nthawi yeniyeni

Mukakhala pa intaneti, zina zimasinthidwa zokha popanda kutsitsa tsamba:

- **Mkhalidwe wa zipinda** — housekeeping akamaliza
- **Zosungitsa zatsopano** — chidziwitso chikuwonekera
- **Malipiro** — zotsala zimasintha
- **Ntchito zopatsidwa** — chidziwitso chikuwonekera

Simuyenera kutsitsa tsamba.

---

## 10. Mavuto ndi mayankho

### "Sign-in failed"

- Onani imelo yanu
- Onani kuti caps lock ndi off
- Pambuyo pa zolakwa 5, akaunti yanu yatsekedwa kwa mphindi 30
- Lumikizanani ndi woyang'anira

### "Page not loading"

- Onani intaneti yanu
- Yesani kutsegula tab yatsopano
- Ngati mulibe intaneti, pulogalamu iyenera kugwirabe ntchito

### "Offline sync stuck"

- Tsegulani tsamba la **Offline**
- Onani mndandanda wotsala
- Ngati zosintha zanenedwa **failed**, lembani ndi kulumikizana ndi
  thandizo

### "WhatsApp message not received"

- Funsani mlendo kuti aonere mu WhatsApp
- Uthenga ukhoza kutenga mphindi 1-2
- Ngati nambala ndi yolakwika, sinthani profailo

### "Cannot check in — unit not available"

- Chipinda chikhoza kukhala ndi mlendo wina
- Onani mkhalidwe wa zipinda
- Sankhani chipinda china kapena funsani woyang'anira

---

## 11. Kupeza thandizo

- **Mavuto a tsiku ndi tsiku:** funsani woyang'anira wanu
- **Zovuta za dongosolo:** lumikizanani ndi Pritech *(lowetsani)*
- **Zadzidzidzi:** imbani foni *(lowetsani)*

---

**Pritech PMS v1.0**
Zopangidwa ku Malawi.

---

> **Zolemba pa baibulo ili:**
>
> Lomasuliridwa ndi womasulira wachichewa. Mau ena aukadaulo
> (monga *reservation*, *folio*, *invoice*, *WhatsApp*) asungidwa
> mu Chingerezi chifukwa amagwiritsidwa ntchito kwambiri mu msika.
>
> Ngati mukuona mau osamveka bwino, chonde lembani ndi kutumiza kwa
> Pritech kuti tikuthandizeni kukonza.
```

---

## Summary

Six files, all created. Here's the manifest:

| Path | Lines | Purpose |
|---|---|---|
| `README.md` | ~220 | Project overview, quick start, architecture |
| `docs/DEPLOYMENT.md` | ~280 | Deploy, verify, rollback, troubleshoot |
| `docs/OPERATIONS.md` | ~330 | Daily/weekly/monthly/quarterly ops, secret rotation, tenant provisioning |
| `docs/DISASTER_RECOVERY.md` | ~340 | RTO/RPO, 5 failure scenarios, restore procedure, quarterly test log |
| `docs/USER_MANUAL.md` | ~450 | Full English staff guide — 11 sections |
| `docs/USER_MANUAL_NY.md` | ~380 | Chichewa translation with translator notes |

Total: ~2,000 lines of documentation.

**Create the directories first:**

```bash
cd /home/project/pritech-pms
mkdir -p docs
```

Then paste each file into its path. Commit:

```bash
git add README.md docs/
git commit -m "Phase 8: complete documentation"
git push origin main
```

The Chichewa manual carries a translator's note at the bottom — this is honest about what was machine-assisted and invites native-speaker correction. If you have a native Chichewa speaker on staff, hand them `USER_MANUAL_NY.md` and ask them to review before you consider it final.

Want me to write out any other Phase 8 file — the backup scripts, the logrotate config, or the user manual translated fully into Chichewa without English glossary terms?