#!/usr/bin/env bash
# ============================================================================
# Pritech PMS — Production deployment script (Phase 5, multi-tenant)
#
# Idempotent and self-healing. Safe to re-run for updates.
#
# Usage:
#   sudo bash deploy_pritech_pms.sh              # deploy / update
#   sudo bash deploy_pritech_pms.sh --fresh      # wipe DB and start clean
#   sudo bash deploy_pritech_pms.sh --skip-ssl   # skip certbot renewal
#   sudo bash deploy_pritech_pms.sh --env-only   # update .env, don't deploy
#   sudo bash deploy_pritech_pms.sh --help
# ============================================================================

# ─── Self-bootstrap: fix CRLF line endings if present ───────────────────────
if [[ -f "$0" ]] && grep -q $'\r' "$0" 2>/dev/null; then
    echo "⚠ Detected CRLF line endings — converting to LF and restarting…"
    sed -i 's/\r$//' "$0" 2>/dev/null || true
    exec bash "$0" "$@"
fi

set -euo pipefail

# ─── Configuration ──────────────────────────────────────────────────────────
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
CERT_PATH="/etc/letsencrypt/live/${DOMAIN}/cert.pem"

# ─── Parse flags ────────────────────────────────────────────────────────────
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

# ─── Logging helpers ────────────────────────────────────────────────────────
log()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ✔ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ⚠ %s\033[0m\n' "$*"; }
info() { printf '\033[0;37m    %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m  ✘ %s\033[0m\n' "$*" >&2; exit 1; }

banner() {
    printf '\n\033[1;35m══════════════════════════════════════════════════════════\033[0m\n'
    printf '\033[1;35m  %s\033[0m\n' "$*"
    printf '\033[1;35m══════════════════════════════════════════════════════════\033[0m\n'
}

# ─── Sanity checks ──────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root (or via sudo)."
command -v git >/dev/null  || die "git not installed."
command -v psql >/dev/null || die "psql not installed — apt install postgresql-client."
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
# .env helpers — read/write without ever `source`-ing the file
# ============================================================================

# Read a value from .env. Strips surrounding quotes, CRLF, and trailing space.
env_get() {
    local key="$1"
    [[ -f "${ENV_FILE}" ]] || { echo ""; return; }
    local raw
    raw="$(grep -E "^${key}=" "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '\r' || true)"
    raw="${raw%"${raw##*[![:space:]]}"}"   # trim trailing spaces
    raw="${raw%\"}"; raw="${raw#\"}"       # strip double quotes
    raw="${raw%\'}"; raw="${raw#\'}"       # strip single quotes
    printf '%s' "${raw}"
}

# Check whether a key exists at all (even empty).
env_has() {
    local key="$1"
    [[ -f "${ENV_FILE}" ]] || return 1
    grep -qE "^${key}=" "${ENV_FILE}"
}

# Overwrite a key (or append if missing). Value written raw.
env_set() {
    local key="$1"
    local value="$2"

    # Escape sed special chars
    local escaped
    escaped=$(printf '%s' "${value}" | sed -e 's/[&|]/\\&/g')

    if env_has "${key}"; then
        sed -i "s|^${key}=.*|${key}=${escaped}|" "${ENV_FILE}"
    else
        printf '\n%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
    fi
}

# Add a key only if missing.
env_set_if_missing() {
    local key="$1"
    local value="$2"
    env_has "${key}" || env_set "${key}" "${value}"
}

# ============================================================================
# Pre-flight (skipped for --env-only)
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
    log "Pre-flight: checking wildcard DNS"
    DNS_IP=$(dig +short "test.${DOMAIN}" A | head -1 || true)
    if [[ "${DNS_IP}" != "${SERVER_IP}" ]]; then
        warn "test.${DOMAIN} → '${DNS_IP:-<none>}' (expected ${SERVER_IP})"
        warn "Wildcard DNS not configured. Tenant subdomains will 404 until fixed."
        warn "Add at your DNS provider:  A  *.pms  →  ${SERVER_IP}"
    else
        ok "Wildcard DNS resolves to ${SERVER_IP}"
    fi

    log "Pre-flight: checking SSL cert"
    if [[ -f "${CERT_PATH}" ]]; then
        if openssl x509 -in "${CERT_PATH}" -noout -text 2>/dev/null \
            | grep -q "DNS:\*\.${DOMAIN#*.}"; then
            ok "Wildcard SSL cert present"
        else
            warn "SSL cert exists but does NOT cover ${WILDCARD}"
            warn "Get a wildcard cert (needs DNS challenge):"
            warn "  certbot certonly --manual --preferred-challenges dns \\"
            warn "    -d ${DOMAIN} -d '${WILDCARD}' --cert-name ${DOMAIN}"
        fi
    else
        warn "No SSL cert found at ${CERT_PATH}"
    fi
fi

# ============================================================================
# Step 1 — Fetch code
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

    # Re-apply +x after reset (git doesn't preserve it from Windows commits)
    chmod +x "${PROJECT_DIR}/deploy_pritech_pms.sh" 2>/dev/null || true

    echo "  HEAD: $(git log -1 --oneline)"
else
    [[ -d "${PROJECT_DIR}" ]] || die "Project dir missing: ${PROJECT_DIR}"
    cd "${PROJECT_DIR}"
fi

# ============================================================================
# Step 2 — Virtualenv + dependencies
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

    # Fail-loud if requirements.txt has shell-incompatible content
    [[ -s requirements.txt ]] || die "requirements.txt is empty or missing."

    pip install -r requirements.txt
    ok "Dependencies installed"

    # These must be importable — fail fast if not
    for pkg in django_tenants requests celery redis; do
        python -c "import ${pkg}" 2>/dev/null \
            || die "Python package '${pkg}' not installed. Check requirements.txt."
    done

    # Phase 4 compliance packages — soft check (warn only)
    for pkg in paychangu pyxrate; do
        python -c "import ${pkg}" 2>/dev/null \
            || warn "Python package '${pkg}' not installed — Phase 4 features disabled."
    done
fi

# ============================================================================
# Step 3 — .env: create if missing, otherwise update in place
# ============================================================================
log "Step 3: Environment file"

# Snapshot existing secrets (before any modification)
EXISTING_SECRET_KEY=""
EXISTING_DB_PASSWORD=""
EXISTING_EMAIL_HOST_PASSWORD=""
if [[ -f "${ENV_FILE}" ]]; then
    EXISTING_SECRET_KEY="$(env_get SECRET_KEY)"
    EXISTING_DB_PASSWORD="$(env_get DB_PASSWORD)"
    EXISTING_EMAIL_HOST_PASSWORD="$(env_get EMAIL_HOST_PASSWORD)"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    # ─── First-time creation ─────────────────────────────────────────────
    EXISTING_SECRET_KEY="${EXISTING_SECRET_KEY:-$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)}"
    EXISTING_DB_PASSWORD="${EXISTING_DB_PASSWORD:-$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)}"

    cat > "${ENV_FILE}" <<EOF
# ══════════════════════════════════════════════════════════════════════
# Pritech PMS — Production .env
# Managed by deploy_pritech_pms.sh — secrets below are preserved on
# re-deploy, deployment-critical values are overwritten each run.
# ══════════════════════════════════════════════════════════════════════

# ─── Core ────────────────────────────────────────────────────────────
SECRET_KEY=${EXISTING_SECRET_KEY}
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings

# ─── Hosts & URLs ────────────────────────────────────────────────────
ALLOWED_HOSTS=${DOMAIN},.${DOMAIN},${SERVER_IP},localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://*.${DOMAIN}
SITE_URL=https://${DOMAIN}
TENANT_BASE_DOMAIN=${DOMAIN}

# ─── Database ────────────────────────────────────────────────────────
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${EXISTING_DB_PASSWORD}
DB_HOST=127.0.0.1
DB_PORT=5432

# ─── Redis / Celery ──────────────────────────────────────────────────
REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0

# ─── Sessions / tenancy ──────────────────────────────────────────────
SESSION_COOKIE_DOMAIN=
CSRF_COOKIE_DOMAIN=
SHOW_PUBLIC_IF_NO_TENANT_FOUND=False

# ─── Email ───────────────────────────────────────────────────────────
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mail.${DOMAIN}
EMAIL_PORT=465
EMAIL_HOST_USER=noreply@${DOMAIN}
EMAIL_HOST_PASSWORD=${EXISTING_EMAIL_HOST_PASSWORD}
EMAIL_USE_TLS=False
EMAIL_USE_SSL=True
DEFAULT_FROM_EMAIL="Pritech PMS <noreply@${DOMAIN}>"
SERVER_EMAIL=noreply@${DOMAIN}

# ─── Monitoring ──────────────────────────────────────────────────────
SENTRY_DSN=
SENTRY_ENV=production

# ─── Compliance (Phase 4) ────────────────────────────────────────────
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
    # ─── Update existing ─────────────────────────────────────────────────
    ok ".env exists — updating deployment-critical values"

    EXISTING_SECRET_KEY="${EXISTING_SECRET_KEY:-$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)}"
    EXISTING_DB_PASSWORD="${EXISTING_DB_PASSWORD:-$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)}"

    # Deployment-critical: force
    env_set DEBUG                          "False"
    env_set DJANGO_SETTINGS_MODULE         "config.settings"
    env_set ALLOWED_HOSTS                  "${DOMAIN},.${DOMAIN},${SERVER_IP},localhost,127.0.0.1"
    env_set CSRF_TRUSTED_ORIGINS           "https://${DOMAIN},https://*.${DOMAIN}"
    env_set SITE_URL                       "https://${DOMAIN}"
    env_set TENANT_BASE_DOMAIN             "${DOMAIN}"
    env_set DB_NAME                        "${DB_NAME}"
    env_set DB_USER                        "${DB_USER}"
    env_set DB_HOST                        "127.0.0.1"
    env_set DB_PORT                        "5432"
    env_set REDIS_URL                      "redis://127.0.0.1:6379/1"
    env_set CELERY_BROKER_URL              "redis://127.0.0.1:6379/0"
    env_set SHOW_PUBLIC_IF_NO_TENANT_FOUND "False"

    # Secrets: preserve
    env_set SECRET_KEY     "${EXISTING_SECRET_KEY}"
    env_set DB_PASSWORD    "${EXISTING_DB_PASSWORD}"

    # Add-if-missing: optional keys
    env_set_if_missing SESSION_COOKIE_DOMAIN ""
    env_set_if_missing CSRF_COOKIE_DOMAIN    ""

    env_set_if_missing EMAIL_BACKEND       "django.core.mail.backends.smtp.EmailBackend"
    env_set_if_missing EMAIL_HOST          "mail.${DOMAIN}"
    env_set_if_missing EMAIL_PORT          "465"
    env_set_if_missing EMAIL_HOST_USER     "noreply@${DOMAIN}"
    env_set_if_missing EMAIL_HOST_PASSWORD ""
    env_set_if_missing EMAIL_USE_TLS       "False"
    env_set_if_missing EMAIL_USE_SSL       "True"
    env_set_if_missing SERVER_EMAIL        "noreply@${DOMAIN}"

    env_set_if_missing SENTRY_DSN ""
    env_set_if_missing SENTRY_ENV "production"

    env_set_if_missing PAYCHANGU_ENABLED       "False"
    env_set_if_missing PAYCHANGU_BASE_URL      "https://api.paychangu.com"
    env_set_if_missing PAYCHANGU_SECRET_KEY    ""
    env_set_if_missing PAYCHANGU_WEBHOOK_SECRET ""

    env_set_if_missing EIS_ENABLED       "False"
    env_set_if_missing EIS_API_BASE_URL  "https://dev-eis-api.mra.mw/api/v1"
    env_set_if_missing EIS_SANDBOX_MODE  "True"
    env_set_if_missing EIS_API_KEY       ""
    env_set_if_missing EIS_TIN           ""

    # Fix known bug: unquoted DEFAULT_FROM_EMAIL containing angle brackets
    if grep -qE '^DEFAULT_FROM_EMAIL=.*<.*>' "${ENV_FILE}" \
       && ! grep -qE '^DEFAULT_FROM_EMAIL="' "${ENV_FILE}"; then
        CURRENT_FROM="$(env_get DEFAULT_FROM_EMAIL)"
        env_set DEFAULT_FROM_EMAIL "\"${CURRENT_FROM}\""
        ok "Fixed quoting on DEFAULT_FROM_EMAIL"
    fi

    # If the key exists but is empty, set it to the recommended default
    if ! grep -qE '^DEFAULT_FROM_EMAIL=.' "${ENV_FILE}"; then
        env_set DEFAULT_FROM_EMAIL "\"Pritech PMS <noreply@${DOMAIN}>\""
    fi

    chmod 600 "${ENV_FILE}"
    ok ".env updated"
fi

# Sanity check: file must have no CRLF and no unquoted angle brackets
if grep -q $'\r' "${ENV_FILE}"; then
    sed -i 's/\r$//' "${ENV_FILE}"
    ok "Stripped CRLF from .env"
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
# Step 4 — PostgreSQL
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
# Step 5 — Ensure tenants migration exists (regenerate if missing)
# ============================================================================
log "Step 5: Ensure tenants app migration exists"

TENANTS_MIGRATION="${PROJECT_DIR}/apps/shared/tenants/migrations/0001_initial.py"
if [[ ! -f "${TENANTS_MIGRATION}" ]]; then
    warn "tenants/migrations/0001_initial.py missing — generating now"
    python manage.py makemigrations tenants
    if [[ -f "${TENANTS_MIGRATION}" ]]; then
        ok "Generated apps/shared/tenants/migrations/0001_initial.py"
        warn "⚠ This file MUST be committed to git or it will regenerate every deploy."
        warn "  On your dev machine:  git add apps/shared/tenants/migrations/0001_initial.py"
    else
        die "Failed to generate tenants migration."
    fi
else
    ok "tenants migration present"
fi

# ============================================================================
# Step 6 — Django check
# ============================================================================
log "Step 6: Django configuration check"
python manage.py check
ok "Django check passed"

# ============================================================================
# Step 7 — Migrate shared schema
# ============================================================================
log "Step 7: Migrate shared schema (public)"
python manage.py migrate_schemas --shared --noinput
ok "Shared schema migrated"

# ============================================================================
# Step 8 — Public tenant
# ============================================================================
log "Step 8: Ensure public tenant exists"

python manage.py shell <<'PY'
from apps.shared.tenants.models import Tenant, Domain
from django.conf import settings

# Base domain: first ALLOWED_HOSTS entry that isn't localhost or IP-only
base_domain = 'localhost'
for h in settings.ALLOWED_HOSTS:
    if not h or h.startswith('.') or h in ('localhost', '127.0.0.1'):
        continue
    # Skip bare IPs
    if h.replace('.', '').isdigit():
        continue
    base_domain = h
    break

public, created = Tenant.objects.get_or_create(
    schema_name='public',
    defaults={'name': 'Pritech PMS', 'plan': 'ENT', 'on_trial': False},
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
# Step 9 — Migrate tenant schemas
# ============================================================================
log "Step 9: Migrate all tenant schemas"
python manage.py migrate_schemas --noinput
ok "Tenant schemas migrated"

# ============================================================================
# Step 10 — Static files
# ============================================================================
log "Step 10: Collect static files"
python manage.py collectstatic --noinput --clear 2>&1 | tail -5
ok "Static files collected"

# ============================================================================
# Step 11 — Superuser
# ============================================================================
log "Step 11: Ensure superuser exists"

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
ok "Superuser ready"

# ============================================================================
# Step 12 — Systemd: Gunicorn
# ============================================================================
log "Step 12: Systemd — Gunicorn"

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
    --log-level info \\
    config.wsgi:application
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ============================================================================
# Step 13 — Systemd: Celery worker
# ============================================================================
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

# ============================================================================
# Step 14 — Systemd: Celery beat
# ============================================================================
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
systemctl enable gunicorn-${PROJECT_NAME}     >/dev/null
systemctl enable celery-worker-${PROJECT_NAME} >/dev/null
systemctl enable celery-beat-${PROJECT_NAME}   >/dev/null
ok "Systemd services created and enabled"

# ============================================================================
# Step 15 — Nginx (Phase-5 ready, no duplicate headers)
# ============================================================================
log "Step 15: Nginx configuration"

cat > /etc/nginx/sites-available/${PROJECT_NAME} <<EOF
# ─────────────────────────────────────────────────────────────────────
# Pritech PMS — HTTP entry (redirects everything to HTTPS)
# ─────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────
# Pritech PMS — HTTPS (public site + tenant subdomains)
#
# NOTE: We deliberately do NOT include proxy_params here. That file sets
# Host, X-Real-IP, X-Forwarded-For, X-Forwarded-Proto — which we also set
# explicitly below. Duplicate headers cause gunicorn 22+ to reject
# requests with "Invalid HTTP Header: 'HOST'".
# ─────────────────────────────────────────────────────────────────────
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

    # Static files (Whitenoise is the fallback)
    location /static/ {
        alias ${PROJECT_DIR}/staticfiles/;
        expires 30d;
        access_log off;
        try_files \$uri \$uri/ =404;
    }

    # Media (tenant-scoped subdirectories handled by TenantFileStorage)
    location /media/ {
        alias ${PROJECT_DIR}/media/;
        expires 7d;
        try_files \$uri \$uri/ =404;
    }

    # Application
    location / {
        proxy_http_version 1.1;
        proxy_pass http://unix:${PROJECT_DIR}/gunicorn.sock;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host  \$host;
        proxy_read_timeout 90;
        proxy_connect_timeout 10;
    }
}
EOF

ln -sf /etc/nginx/sites-available/${PROJECT_NAME} \
       /etc/nginx/sites-enabled/${PROJECT_NAME}

nginx -t || die "Nginx config test failed"
systemctl reload nginx
ok "Nginx reloaded"

# ============================================================================
# Step 16 — SSL
# ============================================================================
if [[ "${SKIP_SSL}" == "true" ]]; then
    warn "--skip-ssl: not touching certbot"
elif [[ -f "${CERT_PATH}" ]]; then
    ok "SSL cert already present"
    # Only attempt renewal if not already running
    if ! pgrep -f "certbot renew" >/dev/null 2>&1; then
        certbot renew --quiet --no-random-sleep-on-renew 2>&1 | tail -3 || true
    else
        warn "Another certbot process is running — skipping renewal"
    fi
else
    warn "No SSL cert — cannot auto-provision wildcard."
    warn "Run manually:"
    warn "  certbot certonly --manual --preferred-challenges dns \\"
    warn "    -d ${DOMAIN} -d '${WILDCARD}' --cert-name ${DOMAIN}"
    warn "Then re-run this script."
fi

# ============================================================================
# Step 17 — Restart services
# ============================================================================
log "Step 17: Restart services"

systemctl restart gunicorn-${PROJECT_NAME}
systemctl restart celery-worker-${PROJECT_NAME}
systemctl restart celery-beat-${PROJECT_NAME}

sleep 3

FAILED=0
for s in gunicorn-${PROJECT_NAME} celery-worker-${PROJECT_NAME} celery-beat-${PROJECT_NAME} nginx; do
    state="$(systemctl is-active "$s" || true)"
    if [[ "${state}" == "active" ]]; then
        ok "${s} is active"
    else
        warn "${s} is ${state}"
        warn "  → journalctl -u ${s} -n 40 --no-pager"
        FAILED=$((FAILED + 1))
    fi
done

# ============================================================================
# Step 18 — Smoke test
# ============================================================================
log "Step 18: Smoke test"

check() {
    local label="$1"
    local url="$2"
    local code
    code=$(curl -sS -o /dev/null -w "%{http_code}" -k --max-time 10 "$url" 2>/dev/null || echo "000")
    if [[ "${code}" =~ ^(200|301|302)$ ]]; then
        printf "  \033[1;32m%-20s %s\033[0m\n" "$label" "$code"
    else
        printf "  \033[1;31m%-20s %s\033[0m\n" "$label" "$code"
    fi
    echo "${code}"
}

C1=$(check "public"        "https://${DOMAIN}/")
C2=$(check "public-admin"  "https://${DOMAIN}/admin/")
C3=$(check "public-login"  "https://${DOMAIN}/login/")
C4=$(check "public-signup" "https://${DOMAIN}/signup/")
C5=$(check "tenant"        "https://pritech.${DOMAIN}/")

# ============================================================================
# Done
# ============================================================================
# Re-apply +x in case git reset wiped it
chmod +x "${PROJECT_DIR}/deploy_pritech_pms.sh" 2>/dev/null || true

banner "Deploy complete — $(date '+%H:%M:%S')"
echo "  HEAD           : $(git -C ${PROJECT_DIR} rev-parse --short HEAD)"
echo "  Public site    : https://${DOMAIN}/"
echo "  Admin          : https://${DOMAIN}/admin/"
echo "  First tenant   : https://pritech.${DOMAIN}/"
echo ""

if [[ "${FAILED}" -gt 0 ]]; then
    warn "${FAILED} service(s) not active — see warnings above."
fi

if [[ "${C1}" == "400" ]]; then
    warn "Public site returns 400 — likely nginx header issue."
    warn "  Check: sudo nginx -T | grep -A15 'location / {'"
    warn "  Should NOT contain: include proxy_params;"
fi

if [[ "${C5}" == "000" ]]; then
    warn "Tenant subdomain unreachable — wildcard DNS probably not set."
    warn "  Verify: dig +short test.${DOMAIN}"
    warn "  Expected: ${SERVER_IP}"
fi

echo "  Logs:"
echo "    journalctl -u gunicorn-${PROJECT_NAME} -n 40 --no-pager"
echo "    journalctl -u celery-worker-${PROJECT_NAME} -n 30 --no-pager"
echo ""
echo "  Superuser (if newly created): admin@pritechmw.com / ChangeMe123!"
echo "  ⚠ CHANGE THE SUPERUSER PASSWORD IMMEDIATELY"
