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
#   - Manages .env: creates if missing, updates deployment-critical
#     values on every run, preserves user secrets
#
# Usage:
#   ./deploy_pritech_pms.sh              # deploy / update
#   ./deploy_pritech_pms.sh --fresh      # wipe DB and start clean (DESTRUCTIVE)
#   ./deploy_pritech_pms.sh --skip-ssl   # skip certbot (already have cert)
#   ./deploy_pritech_pms.sh --env-only   # only update .env, don't deploy
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

ENV_FILE="${PROJECT_DIR}/.env"

# ─── Parse flags ────────────────────────────────────────────────────
FRESH=false
SKIP_SSL=false
ENV_ONLY=false
for arg in "$@"; do
    case $arg in
        --fresh)     FRESH=true ;;
        --skip-ssl)  SKIP_SSL=true ;;
        --env-only)  ENV_ONLY=true ;;
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
echo "  Env only    : ${ENV_ONLY}"
echo ""

# ============================================================================
# .env helpers — read/write without sourcing the whole file
# ============================================================================

# Read a value from .env (returns empty string if missing).
# Strips optional surrounding quotes.
env_get() {
    local key="$1"
    [[ -f "${ENV_FILE}" ]] || { echo ""; return; }
    local raw
    raw="$(grep -E "^${key}=" "${ENV_FILE}" | head -1 | cut -d= -f2- || true)"
    # Strip matching leading/trailing quotes
    raw="${raw%\"}"; raw="${raw#\"}"
    raw="${raw%\'}"; raw="${raw#\'}"
    printf '%s' "${raw}"
}

# Check if a key exists (any value, including empty).
env_has() {
    local key="$1"
    [[ -f "${ENV_FILE}" ]] || return 1
    grep -qE "^${key}=" "${ENV_FILE}"
}

# Set a key to a specific value. Overwrites existing; adds if missing.
# Values are written raw (no quoting) unless $3 is "quote".
env_set() {
    local key="$1"
    local value="$2"
    local mode="${3:-raw}"

    if [[ "${mode}" == "quote" ]]; then
        value="\"${value}\""
    fi

    if env_has "${key}"; then
        # Escape for sed: use | as delimiter to avoid / issues
        local escaped
        escaped=$(printf '%s' "${value}" | sed -e 's/[&|]/\\&/g')
        sed -i "s|^${key}=.*|${key}=${escaped}|" "${ENV_FILE}"
    else
        printf '\n%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
    fi
}

# Set only if key is missing (never overwrite).
env_set_if_missing() {
    local key="$1"
    local value="$2"
    local mode="${3:-raw}"

    if env_has "${key}"; then
        return 0
    fi
    env_set "${key}" "${value}" "${mode}"
}

# ============================================================================
# Pre-flight (skipped if --env-only)
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
    log "Pre-flight: checking wildcard DNS"
    DNS_IP=$(dig +short "test.${DOMAIN}" A | head -1 || true)
    if [[ "${DNS_IP}" != "${SERVER_IP}" ]]; then
        warn "test.${DOMAIN} resolves to '${DNS_IP:-<nothing>}' — expected ${SERVER_IP}"
        warn "Wildcard DNS may not be configured. Tenants will 404 until fixed."
    else
        ok "Wildcard DNS resolves to ${SERVER_IP}"
    fi

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
fi

# ============================================================================
# Step 1: Fetch code (skipped if --env-only and dir missing)
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
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
else
    [[ -d "${PROJECT_DIR}" ]] || die "Project dir missing: ${PROJECT_DIR}"
    cd "${PROJECT_DIR}"
fi

# ============================================================================
# Step 2: Virtualenv + deps (skipped if --env-only)
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
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
    python -c 'import django_tenants' 2>/dev/null \
        || die "django-tenants not installed. Check requirements.txt."
fi

# ============================================================================
# Step 3: .env — create or update
# ============================================================================
log "Step 3: Environment file"

# Preserve existing secrets before we touch the file
if [[ -f "${ENV_FILE}" ]]; then
    EXISTING_SECRET_KEY="$(env_get SECRET_KEY)"
    EXISTING_DB_PASSWORD="$(env_get DB_PASSWORD)"
    EXISTING_EMAIL_HOST_PASSWORD="$(env_get EMAIL_HOST_PASSWORD)"
    EXISTING_EMAIL_HOST="$(env_get EMAIL_HOST)"
    EXISTING_EMAIL_PORT="$(env_get EMAIL_PORT)"
    EXISTING_EMAIL_HOST_USER="$(env_get EMAIL_HOST_USER)"
    EXISTING_EMAIL_USE_TLS="$(env_get EMAIL_USE_TLS)"
    EXISTING_EMAIL_USE_SSL="$(env_get EMAIL_USE_SSL)"
    EXISTING_DEFAULT_FROM_EMAIL="$(env_get DEFAULT_FROM_EMAIL)"
    EXISTING_SERVER_EMAIL="$(env_get SERVER_EMAIL)"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    # First-time creation
    EXISTING_SECRET_KEY="$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)"
    EXISTING_DB_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"

    cat > "${ENV_FILE}" <<EOF
# ─── Core ────────────────────────────────────────────────
SECRET_KEY=${EXISTING_SECRET_KEY}
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings

# ─── Hosts & URLs ────────────────────────────────────────
ALLOWED_HOSTS=${DOMAIN},.${DOMAIN},${SERVER_IP},localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://*.${DOMAIN}
SITE_URL=https://${DOMAIN}
TENANT_BASE_DOMAIN=${DOMAIN}

# ─── Database ────────────────────────────────────────────
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${EXISTING_DB_PASSWORD}
DB_HOST=127.0.0.1
DB_PORT=5432

# ─── Redis / Celery ──────────────────────────────────────
REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0

# ─── Sessions ────────────────────────────────────────────
SESSION_COOKIE_DOMAIN=
CSRF_COOKIE_DOMAIN=
SHOW_PUBLIC_IF_NO_TENANT_FOUND=False

# ─── Email ───────────────────────────────────────────────
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mail.${DOMAIN}
EMAIL_PORT=465
EMAIL_HOST_USER=noreply@${DOMAIN}
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=False
EMAIL_USE_SSL=True
DEFAULT_FROM_EMAIL="Pritech PMS <noreply@${DOMAIN}>"
SERVER_EMAIL=noreply@${DOMAIN}

# ─── Monitoring ──────────────────────────────────────────
SENTRY_DSN=
SENTRY_ENV=production

# ─── Compliance (Phase 4) ────────────────────────────────
PAYCHANGU_ENABLED=False
PAYCHANGU_BASE_URL=https://api.paychangu.com
PAYCHANGU_SECRET_KEY=
PAYCHANGU_WEBHOOK_SECRET=

EIS_ENABLED=False
EIS_API_BASE_URL=https://dev-eis-api.mra.mw/api/v1
EIS_SANDBOX_MODE=True
EIS_API_KEY=
EIS_TIN=
EOF

    chmod 600 "${ENV_FILE}"
    ok "Created .env with generated secrets"
else
    ok ".env exists — updating deployment-critical values"

    # ─── Preserve secrets (don't overwrite user-provided values) ───
    [[ -n "${EXISTING_SECRET_KEY}" ]]   || EXISTING_SECRET_KEY="$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)"
    [[ -n "${EXISTING_DB_PASSWORD}" ]]  || EXISTING_DB_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"

    # ─── Force deployment-critical values ───
    env_set DEBUG               "False"
    env_set DJANGO_SETTINGS_MODULE "config.settings"

    env_set ALLOWED_HOSTS       "${DOMAIN},.${DOMAIN},${SERVER_IP},localhost,127.0.0.1"
    env_set CSRF_TRUSTED_ORIGINS "https://${DOMAIN},https://*.${DOMAIN}"
    env_set SITE_URL            "https://${DOMAIN}"
    env_set TENANT_BASE_DOMAIN  "${DOMAIN}"

    env_set DB_NAME             "${DB_NAME}"
    env_set DB_USER             "${DB_USER}"
    env_set DB_HOST             "127.0.0.1"
    env_set DB_PORT             "5432"

    env_set REDIS_URL           "redis://127.0.0.1:6379/1"
    env_set CELERY_BROKER_URL   "redis://127.0.0.1:6379/0"

    env_set SHOW_PUBLIC_IF_NO_TENANT_FOUND "False"

    # ─── Preserve secrets — re-write with quotes where needed ───
    env_set SECRET_KEY          "${EXISTING_SECRET_KEY}"
    env_set DB_PASSWORD         "${EXISTING_DB_PASSWORD}"

    # ─── Add new keys only if missing ───
    env_set_if_missing SESSION_COOKIE_DOMAIN ""
    env_set_if_missing CSRF_COOKIE_DOMAIN    ""

    env_set_if_missing EMAIL_BACKEND "django.core.mail.backends.smtp.EmailBackend"
    env_set_if_missing EMAIL_HOST    "mail.${DOMAIN}"
    env_set_if_missing EMAIL_PORT    "465"
    env_set_if_missing EMAIL_HOST_USER "noreply@${DOMAIN}"
    env_set_if_missing EMAIL_HOST_PASSWORD ""
    env_set_if_missing EMAIL_USE_TLS "False"
    env_set_if_missing EMAIL_USE_SSL "True"
    env_set_if_missing DEFAULT_FROM_EMAIL "\"Pritech PMS <noreply@${DOMAIN}>\"" ""
    env_set_if_missing SERVER_EMAIL  "noreply@${DOMAIN}"

    env_set_if_missing SENTRY_DSN ""
    env_set_if_missing SENTRY_ENV "production"

    env_set_if_missing PAYCHANGU_ENABLED    "False"
    env_set_if_missing PAYCHANGU_BASE_URL   "https://api.paychangu.com"
    env_set_if_missing PAYCHANGU_SECRET_KEY ""
    env_set_if_missing PAYCHANGU_WEBHOOK_SECRET ""

    env_set_if_missing EIS_ENABLED       "False"
    env_set_if_missing EIS_API_BASE_URL  "https://dev-eis-api.mra.mw/api/v1"
    env_set_if_missing EIS_SANDBOX_MODE  "True"
    env_set_if_missing EIS_API_KEY       ""
    env_set_if_missing EIS_TIN           ""

    # Fix the specific quoting issue in DEFAULT_FROM_EMAIL
    # (Old value: DEFAULT_FROM_EMAIL=Pritech PMS <noreply@pms.pritechmw.com>)
    if grep -qE '^DEFAULT_FROM_EMAIL=.*<.*>' "${ENV_FILE}"; then
        if ! grep -qE '^DEFAULT_FROM_EMAIL="' "${ENV_FILE}"; then
            CURRENT_VAL="$(env_get DEFAULT_FROM_EMAIL)"
            env_set DEFAULT_FROM_EMAIL "\"${CURRENT_VAL}\"" ""
            ok "Fixed quoting on DEFAULT_FROM_EMAIL"
        fi
    fi

    chmod 600 "${ENV_FILE}"
    ok ".env updated"
fi

# Verify .env sources cleanly
if ! bash -n <(grep -v '^#' "${ENV_FILE}" | grep -v '^$') 2>/dev/null; then
    warn ".env has syntax issues that may break shell parsing"
    warn "Run manually to see: set -a; source ${ENV_FILE}; set +a"
fi

# Read DB_PASSWORD without sourcing
DB_PASS="$(env_get DB_PASSWORD)"
[[ -n "${DB_PASS}" ]] || die "DB_PASSWORD missing from .env"

if [[ "${ENV_ONLY}" == "true" ]]; then
    banner ".env update complete"
    echo "  File: ${ENV_FILE}"
    echo "  Preview (secrets masked):"
    grep -vE '^(SECRET_KEY|DB_PASSWORD|EMAIL_HOST_PASSWORD|PAYCHANGU_SECRET_KEY|PAYCHANGU_WEBHOOK_SECRET|EIS_API_KEY)=' "${ENV_FILE}" \
        | sed 's/^/    /'
    exit 0
fi

# ============================================================================
# Step 4: PostgreSQL
# ============================================================================
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

# ============================================================================
# Step 5: Django check
# ============================================================================
log "Step 5: Django configuration check"
python manage.py check
ok "Django check passed"

# ============================================================================
# Step 6: Migrate shared schema
# ============================================================================
log "Step 6: Migrate shared schema (public)"
python manage.py migrate_schemas --shared --noinput
ok "Shared schema migrated"

# ============================================================================
# Step 7: Public tenant
# ============================================================================
log "Step 7: Ensure public tenant exists"

python manage.py shell <<'PY'
from apps.shared.tenants.models import Tenant, Domain
from django.conf import settings

# Find the base domain (first entry in ALLOWED_HOSTS)
base_domain = 'localhost'
for h in settings.ALLOWED_HOSTS:
    if h and not h.startswith('.') and h not in ('localhost', '127.0.0.1'):
        base_domain = h
        break

public, created = Tenant.objects.get_or_create(
    schema_name='public',
    defaults={
        'name': 'Pritech PMS',
        'plan': 'ENT',
        'on_trial': False,
    },
)

Domain.objects.get_or_create(
    domain=base_domain,
    defaults={'tenant': public, 'is_primary': True},
)

print(f'Public tenant: {"created" if created else "exists"}')
print(f'Public domain: {base_domain}')
PY
ok "Public tenant ready"

# ============================================================================
# Step 8: Migrate tenant schemas
# ============================================================================
log "Step 8: Migrate all tenant schemas"
python manage.py migrate_schemas --noinput
ok "Tenant schemas migrated"

# ============================================================================
# Step 9: Static files
# ============================================================================
log "Step 9: Collect static files"
python manage.py collectstatic --noinput --clear
ok "Static files collected"

# ============================================================================
# Step 10: Superuser
# ============================================================================
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

# ============================================================================
# Step 11-13: Systemd services
# ============================================================================
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

# ============================================================================
# Step 14: Nginx
# ============================================================================
log "Step 14: Nginx configuration"

cat > /etc/nginx/sites-available/${PROJECT_NAME} <<EOF
# Pritech PMS — HTTP entry (redirects to HTTPS)
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${WILDCARD};

    client_max_body_size 25M;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# Pritech PMS — HTTPS (public + tenant subdomains)
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

    location /static/ {
        alias ${PROJECT_DIR}/staticfiles/;
        expires 30d;
        access_log off;
        try_files \$uri \$uri/ =404;
    }

    location /media/ {
        alias ${PROJECT_DIR}/media/;
        expires 7d;
        try_files \$uri \$uri/ =404;
    }

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

# ============================================================================
# Step 15: SSL
# ============================================================================
if [[ "${SKIP_SSL}" == "true" ]]; then
    warn "--skip-ssl: not touching certbot"
elif [[ -f "${CERT_PATH}" ]]; then
    ok "SSL cert already present — skipping certbot"
    certbot renew --quiet || true
else
    warn "No SSL cert — cannot auto-provision wildcard."
    warn "Run manually:"
    warn "  certbot certonly --manual --preferred-challenges dns \\"
    warn "    -d ${DOMAIN} -d '${WILDCARD}' --cert-name ${DOMAIN}"
fi

# ============================================================================
# Step 16: Restart services
# ============================================================================
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

# ============================================================================
# Step 17: Smoke test
# ============================================================================
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
check "tenant"        "https://pritech.${DOMAIN}/"

# ============================================================================
# Done
# ============================================================================
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
