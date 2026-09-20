#!/usr/bin/env bash
# ============================================================================
# Pritech PMS — Production deployment script (Phase 5, multi-tenant)
#
# Features:
#   - Idempotent: safe to re-run for updates
#   - Handles both fresh install and re-deploy
#   - Uses django-tenants migrate_schemas (NOT migrate)
#   - Creates public tenant if missing
#   - Celery workers + beat with unique node names
#   - Nginx wildcard server_name (*.pms.pritechmw.com)
#   - Reads optional .env overrides from /home/project/pritech-pms/.env
#
# Usage:
#   ./deploy_pritech_pms.sh              # deploy / update
#   ./deploy_pritech_pms.sh --fresh      # wipe DB and start clean (DESTRUCTIVE)
#   ./deploy_pritech_pms.sh --skip-ssl   # skip certbot (already have cert)
# ============================================================================

set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────
PROJECT_NAME="pritech-pms"
PROJECT_DIR="/home/project/pritech-pms"
VENV_DIR="${PROJECT_DIR}/venv"
REPO_URL="https://github.com/Izk-123/pritech-property-management-system.git"
BRANCH="main"

DOMAIN="pms.pritechmw.com"
WILDCARD="*.pms.pritechmw.com"
SERVER_IP="204.168.251.91"

DB_NAME="pritech_pms_db"
DB_USER="pritech_pms_user"

# ─── Parse flags ────────────────────────────────────────────────────
FRESH=false
SKIP_SSL=false
for arg in "$@"; do
    case $arg in
        --fresh)     FRESH=true ;;
        --skip-ssl)  SKIP_SSL=true ;;
        --help|-h)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
    esac
done

# ─── Logging helpers ────────────────────────────────────────────────
log()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ✔ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ⚠ %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m  ✘ %s\033[0m\n' "$*" >&2; exit 1; }

banner() {
    printf '\n\033[1;35m══════════════════════════════════════════════════════════\033[0m\n'
    printf '\033[1;35m  %s\033[0m\n' "$*"
    printf '\033[1;35m══════════════════════════════════════════════════════════\033[0m\n'
}

# ─── Sanity checks ──────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root (or via sudo)."
command -v git >/dev/null || die "git not installed."
command -v psql >/dev/null || die "psql not installed — install postgresql-client."
command -v nginx >/dev/null || die "nginx not installed."

banner "Pritech PMS deploy — $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Domain      : ${DOMAIN}"
echo "  Wildcard    : ${WILDCARD}"
echo "  Server IP   : ${SERVER_IP}"
echo "  Project dir : ${PROJECT_DIR}"
echo "  Database    : ${DB_NAME} / ${DB_USER}"
echo "  Fresh DB    : ${FRESH}"
echo "  Skip SSL    : ${SKIP_SSL}"
echo ""

# ─── Pre-flight: wildcard DNS ───────────────────────────────────────
log "Pre-flight: checking wildcard DNS"
DNS_IP=$(dig +short "test.${DOMAIN}" A | head -1 || true)
if [[ "${DNS_IP}" != "${SERVER_IP}" ]]; then
    warn "test.${DOMAIN} resolves to '${DNS_IP:-<nothing>}' — expected ${SERVER_IP}"
    warn "Wildcard DNS may not be configured. Tenants will 404 until fixed."
    warn "Continuing anyway — site may not serve tenant subdomains."
else
    ok "Wildcard DNS resolves to ${SERVER_IP}"
fi

# ─── Pre-flight: wildcard SSL ───────────────────────────────────────
log "Pre-flight: checking SSL cert"
CERT_PATH="/etc/letsencrypt/live/${DOMAIN}/cert.pem"
if [[ -f "${CERT_PATH}" ]]; then
    if openssl x509 -in "${CERT_PATH}" -noout -text 2>/dev/null \
        | grep -q "DNS:\*\.${DOMAIN#*.}"; then
        ok "Wildcard SSL cert present at ${CERT_PATH}"
    else
        warn "SSL cert exists but does NOT cover ${WILDCARD}"
        warn "Get a wildcard cert with:"
        warn "  certbot certonly --manual --preferred-challenges dns \\"
        warn "    -d ${DOMAIN} -d '${WILDCARD}' --cert-name ${DOMAIN}"
    fi
else
    warn "No cert found at ${CERT_PATH}"
fi

# ─── Step 1: Fetch code ─────────────────────────────────────────────
log "Step 1: Fetch repository"

if [[ ! -d "${PROJECT_DIR}/.git" ]]; then
    git clone --branch "${BRANCH}" "${REPO_URL}" "${PROJECT_DIR}"
    ok "Cloned repo to ${PROJECT_DIR}"
else
    cd "${PROJECT_DIR}"
    git fetch origin
    git reset --hard "origin/${BRANCH}"
    ok "Reset to origin/${BRANCH} ($(git rev-parse --short HEAD))"
fi

cd "${PROJECT_DIR}"
echo "  HEAD: $(git log -1 --oneline)"

# ─── Step 2: Virtualenv + deps ──────────────────────────────────────
log "Step 2: Python venv and dependencies"

if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
    ok "Created venv"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip wheel >/dev/null
pip install -r requirements.txt
ok "Dependencies installed"

# django-tenants must be present — fail loudly if not
python -c 'import django_tenants' 2>/dev/null \
    || die "django-tenants not installed. Check requirements.txt."

# ─── Step 3: .env ───────────────────────────────────────────────────
log "Step 3: Environment file"

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
    DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
    DJANGO_SECRET="$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)"

    cat > "${PROJECT_DIR}/.env" <<EOF
SECRET_KEY=${DJANGO_SECRET}
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings

ALLOWED_HOSTS=${DOMAIN},.${DOMAIN},${SERVER_IP},localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://*.${DOMAIN}
SITE_URL=https://${DOMAIN}
TENANT_BASE_DOMAIN=${DOMAIN}

DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASS}
DB_HOST=127.0.0.1
DB_PORT=5432

REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0

# Leave blank — host-only cookies preserve tenant isolation
SESSION_COOKIE_DOMAIN=
CSRF_COOKIE_DOMAIN=
SHOW_PUBLIC_IF_NO_TENANT_FOUND=False

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@${DOMAIN}

SENTRY_DSN=
SENTRY_ENV=production

PAYCHANGU_ENABLED=False
EIS_ENABLED=False
EIS_SANDBOX_MODE=True
EOF

    chmod 600 "${PROJECT_DIR}/.env"
    ok "Created .env with generated secrets"
    warn "Edit ${PROJECT_DIR}/.env to add EMAIL_* credentials before going live"
else
    ok ".env exists — leaving unchanged"
fi

# shellcheck disable=SC1091
set -a; source "${PROJECT_DIR}/.env"; set +a
DB_PASS="${DB_PASSWORD}"

# ─── Step 4: PostgreSQL ─────────────────────────────────────────────
log "Step 4: PostgreSQL database and user"

sudo -u postgres psql <<SQL >/dev/null
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
    ELSE
        ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASS}';
    END IF;
END
\$\$;
SQL

if [[ "${FRESH}" == "true" ]]; then
    warn "--fresh: dropping database ${DB_NAME}"
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME};" >/dev/null
fi

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" \
    | grep -q 1 || sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" >/dev/null
sudo -u postgres psql -d "${DB_NAME}" -c "GRANT ALL ON SCHEMA public TO ${DB_USER};" >/dev/null
sudo -u postgres psql -d "${DB_NAME}" -c "ALTER SCHEMA public OWNER TO ${DB_USER};" >/dev/null

ok "Database ready"

# ─── Step 5: Django check ───────────────────────────────────────────
log "Step 5: Django configuration check"
python manage.py check
ok "Django check passed"

# ─── Step 6: Migrate shared schema ──────────────────────────────────
log "Step 6: Migrate shared schema (public)"

python manage.py migrate_schemas --shared --noinput
ok "Shared schema migrated"

# ─── Step 7: Create public tenant if missing ────────────────────────
log "Step 7: Ensure public tenant exists"

python manage.py shell <<'PY'
from apps.shared.tenants.models import Tenant, Domain
from django.conf import settings

domain = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'

public, created = Tenant.objects.get_or_create(
    schema_name='public',
    defaults={
        'name': 'Pritech PMS',
        'plan': 'ENT',
        'on_trial': False,
    },
)

Domain.objects.get_or_create(
    domain=domain,
    defaults={'tenant': public, 'is_primary': True},
)

print(f'Public tenant: {"created" if created else "exists"}')
print(f'Public domain: {domain}')
PY
ok "Public tenant ready"

# ─── Step 8: Migrate tenant schemas ─────────────────────────────────
log "Step 8: Migrate all tenant schemas"
python manage.py migrate_schemas --noinput
ok "Tenant schemas migrated"

# ─── Step 9: Static files ───────────────────────────────────────────
log "Step 9: Collect static files"
python manage.py collectstatic --noinput --clear
ok "Static files collected"

# ─── Step 10: Superuser (only if none exists) ───────────────────────
log "Step 10: Ensure superuser exists"

python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
U = get_user_model()
if not U.objects.filter(is_superuser=True).exists():
    U.objects.create_superuser(
        email='admin@pritechmw.com',
        username='admin',
        password='ChangeMe123!',
    )
    print('Created superuser: admin@pritechmw.com / ChangeMe123!')
    print('  ⚠ CHANGE THIS PASSWORD IMMEDIATELY')
else:
    print('Superuser already exists')
PY

# ─── Step 11: Systemd — Gunicorn ────────────────────────────────────
log "Step 11: Systemd services"

cat > /etc/systemd/system/gunicorn-${PROJECT_NAME}.service <<EOF
[Unit]
Description=Gunicorn for Pritech PMS
After=network.target postgresql.service

[Service]
User=root
Group=root
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="DJANGO_SETTINGS_MODULE=config.settings"
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${VENV_DIR}/bin/gunicorn \\
    --workers 3 \\
    --bind unix:${PROJECT_DIR}/gunicorn.sock \\
    --access-logfile - \\
    --error-logfile - \\
    config.wsgi:application
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ─── Step 12: Systemd — Celery worker ───────────────────────────────
cat > /etc/systemd/system/celery-worker-${PROJECT_NAME}.service <<EOF
[Unit]
Description=Celery Worker for Pritech PMS
After=network.target redis-server.service postgresql.service

[Service]
User=root
Group=root
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="DJANGO_SETTINGS_MODULE=config.settings"
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${VENV_DIR}/bin/celery -A config worker -l info -n ${PROJECT_NAME}@%H
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ─── Step 13: Systemd — Celery beat ─────────────────────────────────
cat > /etc/systemd/system/celery-beat-${PROJECT_NAME}.service <<EOF
[Unit]
Description=Celery Beat for Pritech PMS
After=network.target redis-server.service postgresql.service

[Service]
User=root
Group=root
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="DJANGO_SETTINGS_MODULE=config.settings"
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${VENV_DIR}/bin/celery -A config beat -l info \\
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \\
    -s ${PROJECT_DIR}/celerybeat-schedule
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gunicorn-${PROJECT_NAME} >/dev/null
systemctl enable celery-worker-${PROJECT_NAME} >/dev/null
systemctl enable celery-beat-${PROJECT_NAME} >/dev/null
ok "Systemd services created and enabled"

# ─── Step 14: Nginx ─────────────────────────────────────────────────
log "Step 14: Nginx configuration"

cat > /etc/nginx/sites-available/${PROJECT_NAME} <<EOF
# Pritech PMS — HTTP entry (redirects to HTTPS once cert exists)
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${WILDCARD};

    client_max_body_size 25M;

    # Let certbot do its HTTP-01 challenge
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# Pritech PMS — HTTPS (both public and tenant subdomains)
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN} ${WILDCARD};

    client_max_body_size 25M;

    ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Static files (Whitenoise also serves as fallback)
    location /static/ {
        alias ${PROJECT_DIR}/staticfiles/;
        expires 30d;
        access_log off;
        try_files \$uri \$uri/ =404;
    }

    # Media (tenant-scoped subdirectories)
    location /media/ {
        alias ${PROJECT_DIR}/media/;
        expires 7d;
        try_files \$uri \$uri/ =404;
    }

    # Gunicorn
    location / {
        include proxy_params;
        proxy_pass http://unix:${PROJECT_DIR}/gunicorn.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 90;
    }
}
EOF

ln -sf /etc/nginx/sites-available/${PROJECT_NAME} \
       /etc/nginx/sites-enabled/${PROJECT_NAME}

nginx -t || die "Nginx config test failed"
systemctl reload nginx
ok "Nginx reloaded"

# ─── Step 15: SSL (only if not skipped) ─────────────────────────────
if [[ "${SKIP_SSL}" == "true" ]]; then
    warn "--skip-ssl: not touching certbot"
elif [[ -f "${CERT_PATH}" ]]; then
    ok "SSL cert already present — skipping certbot"
    # Try renewal in case cert is close to expiry
    certbot renew --quiet || true
else
    warn "No SSL cert — cannot auto-provision wildcard."
    warn "Run manually:"
    warn "  certbot certonly --manual --preferred-challenges dns \\"
    warn "    -d ${DOMAIN} -d '${WILDCARD}' --cert-name ${DOMAIN}"
    warn "Then re-run this script with --skip-ssl."
fi

# ─── Step 16: Start services ────────────────────────────────────────
log "Step 16: Restart services"
systemctl restart gunicorn-${PROJECT_NAME}
systemctl restart celery-worker-${PROJECT_NAME}
systemctl restart celery-beat-${PROJECT_NAME}

sleep 3

for s in gunicorn-${PROJECT_NAME} celery-worker-${PROJECT_NAME} celery-beat-${PROJECT_NAME} nginx; do
    state="$(systemctl is-active "$s" || true)"
    if [[ "${state}" == "active" ]]; then
        ok "${s} is active"
    else
        warn "${s} is ${state} — check: journalctl -u ${s} -n 50"
    fi
done

# ─── Step 17: Smoke test ────────────────────────────────────────────
log "Step 17: Smoke test"

check() {
    local label="$1"
    local url="$2"
    local code
    code=$(curl -sS -o /dev/null -w "%{http_code}" -k "$url" || echo "000")
    printf "  %-20s %s\n" "$label" "$code"
}

check "public"        "https://${DOMAIN}/"
check "public-admin"  "https://${DOMAIN}/admin/"
check "public-login"  "https://${DOMAIN}/login/"
check "public-signup" "https://${DOMAIN}/signup/"

# Tenant subdomain (may 404 if wildcard DNS not yet propagated)
check "tenant" "https://pritech.${DOMAIN}/"

# ─── Done ───────────────────────────────────────────────────────────
banner "Deploy complete"
echo "  HEAD           : $(git -C ${PROJECT_DIR} rev-parse --short HEAD)"
echo "  Public site    : https://${DOMAIN}/"
echo "  Admin          : https://${DOMAIN}/admin/"
echo "  First tenant   : https://pritech.${DOMAIN}/"
echo ""
echo "  If status codes above are not 200/302, check:"
echo "    journalctl -u gunicorn-${PROJECT_NAME} -n 50 --no-pager"
echo "    journalctl -u celery-worker-${PROJECT_NAME} -n 30 --no-pager"
echo "    nginx -t && systemctl status nginx"
echo ""
echo "  Superuser (if newly created): admin@pritechmw.com / ChangeMe123!"
echo "  ⚠ CHANGE THE SUPERUSER PASSWORD IMMEDIATELY"