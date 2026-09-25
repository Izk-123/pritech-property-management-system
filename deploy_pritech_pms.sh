#!/usr/bin/env bash
# ============================================================================
# Pritech PMS — Production deployment script
#   Phase 5: multi-tenant via django-tenants
#   Phase 6: PWA + offline-first
#   Phase 7: Channels + Redis WebSockets + WhatsApp/email + animated admin
#
# Idempotent and self-healing. Auto-detects a free Daphne port, cleans stale
# processes, flattens nested static icons, and verifies both URLconfs import.
#
# Usage:
#   sudo bash deploy_pritech_pms.sh              # deploy / update
#   sudo bash deploy_pritech_pms.sh --fresh      # wipe DB and start clean
#   sudo bash deploy_pritech_pms.sh --skip-ssl   # skip certbot renewal
#   sudo bash deploy_pritech_pms.sh --env-only   # update .env, don't deploy
#   sudo bash deploy_pritech_pms.sh --help
# ============================================================================

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

# Preferred Daphne port. Pre-flight will auto-pick a different one if this
# is held by a foreign process.
DAPHNE_PORT_PREFERRED="8011"
DAPHNE_PORT="${DAPHNE_PORT_PREFERRED}"

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
echo "  Daphne pref : ${DAPHNE_PORT_PREFERRED}"
echo "  Fresh DB    : ${FRESH}"
echo "  Skip SSL    : ${SKIP_SSL}"
echo "  Env only    : ${ENV_ONLY}"
echo ""

# ============================================================================
# .env helpers
# ============================================================================
env_get() {
    local key="$1"
    [[ -f "${ENV_FILE}" ]] || { echo ""; return; }
    local raw
    raw="$(grep -E "^${key}=" "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '\r' || true)"
    raw="${raw%"${raw##*[![:space:]]}"}"
    raw="${raw%\"}"; raw="${raw#\"}"
    raw="${raw%\'}"; raw="${raw#\'}"
    printf '%s' "${raw}"
}

env_has() {
    local key="$1"
    [[ -f "${ENV_FILE}" ]] || return 1
    grep -qE "^${key}=" "${ENV_FILE}"
}

env_set() {
    local key="$1"
    local value="$2"
    local escaped
    escaped=$(printf '%s' "${value}" | sed -e 's/[&|]/\\&/g')
    if env_has "${key}"; then
        sed -i "s|^${key}=.*|${key}=${escaped}|" "${ENV_FILE}"
    else
        printf '\n%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
    fi
}

env_set_if_missing() {
    local key="$1"
    local value="$2"
    env_has "${key}" || env_set "${key}" "${value}"
}

# ============================================================================
# Pre-flight: pick a free Daphne port
#
# If ${DAPHNE_PORT_PREFERRED} is already bound:
#   - If the holder belongs to our systemd unit → fine, restart will handle
#   - Otherwise → scan next 20 ports, use first free one
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
    log "Pre-flight: choosing Daphne port"

    port_is_bound() {
        ss -tln 2>/dev/null | grep -q ":$1 "
    }

    port_owner() {
        # Print the process name of whatever holds the port, or empty
        ss -tlnp 2>/dev/null \
            | grep ":$1 " \
            | grep -oP 'users:\(\("\K[^"]+' \
            | head -1 \
            || true
    }

    if ! port_is_bound "${DAPHNE_PORT}"; then
        ok "Port ${DAPHNE_PORT} is free"
    else
        owner="$(port_owner "${DAPHNE_PORT}")"
        if [[ "${owner}" == "daphne" ]]; then
            # Likely our own daphne from a crashed earlier start.
            # Step 0 below will kill it. Keep the port.
            warn "Port ${DAPHNE_PORT} held by daphne — will be cleaned up in Step 0"
        else
            warn "Port ${DAPHNE_PORT} held by '${owner:-unknown}' — scanning for a free port"
            FOUND_PORT=""
            for p in $(seq $((DAPHNE_PORT + 1)) $((DAPHNE_PORT + 20))); do
                if ! port_is_bound "${p}"; then
                    FOUND_PORT="${p}"
                    break
                fi
            done
            [[ -n "${FOUND_PORT}" ]] || die "No free Daphne port in range $((DAPHNE_PORT + 1))..$((DAPHNE_PORT + 20))"
            DAPHNE_PORT="${FOUND_PORT}"
            ok "Switched Daphne port to ${DAPHNE_PORT}"
        fi
    fi

    # Persist the chosen port to .env so any code reading DAPHNE_PORT stays in sync
    if [[ -f "${ENV_FILE}" ]]; then
        env_set DAPHNE_PORT "${DAPHNE_PORT}"
    fi
fi

# ============================================================================
# Pre-flight: DNS, SSL, Redis
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
    log "Pre-flight: checking wildcard DNS"
    DNS_IP=$(dig +short "test.${DOMAIN}" A | head -1 || true)
    if [[ "${DNS_IP}" != "${SERVER_IP}" ]]; then
        warn "test.${DOMAIN} → '${DNS_IP:-<none>}' (expected ${SERVER_IP})"
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
        fi
    else
        warn "No SSL cert found at ${CERT_PATH}"
    fi

    log "Pre-flight: checking Redis on DB 2 (Channels)"
    if redis-cli -n 2 ping >/dev/null 2>&1; then
        ok "Redis DB 2 responding"
    else
        warn "Redis DB 2 not responding — Channels will fail to broadcast"
    fi
fi

# ============================================================================
# Step 0 — Cleanup stale project processes
#
# Kills any orphaned daphne/gunicorn process that belongs to this project
# but isn't managed by systemd (leftover from a crashed earlier start).
# Runs BEFORE we write/rewrite systemd units.
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
    log "Step 0: Cleanup stale project processes"

    # Stop systemd units cleanly first — else they respawn while we kill
    for svc in "daphne-${PROJECT_NAME}" "gunicorn-${PROJECT_NAME}"; do
        systemctl stop "${svc}" 2>/dev/null || true
    done
    systemctl reset-failed "daphne-${PROJECT_NAME}" 2>/dev/null || true
    systemctl reset-failed "gunicorn-${PROJECT_NAME}" 2>/dev/null || true
    sleep 1

    # Kill any process still bound to the Daphne port
    if ss -tln 2>/dev/null | grep -q ":${DAPHNE_PORT} "; then
        warn "Port ${DAPHNE_PORT} still bound — killing holder"
        fuser -k "${DAPHNE_PORT}/tcp" 2>/dev/null || true
        sleep 1
    fi

    # Kill any orphaned daphne/gunicorn matching this project
    pkill -f "daphne.*${PROJECT_NAME}" 2>/dev/null || true
    pkill -f "gunicorn.*${PROJECT_DIR}" 2>/dev/null || true
    sleep 1

    # Confirm port is now free
    if ss -tln 2>/dev/null | grep -q ":${DAPHNE_PORT} "; then
        # Still bound by something non-killable → fall back further
        warn "Port ${DAPHNE_PORT} still held after cleanup — selecting another"
        FOUND_PORT=""
        for p in $(seq $((DAPHNE_PORT + 1)) $((DAPHNE_PORT + 20))); do
            if ! ss -tln | grep -q ":${p} "; then
                FOUND_PORT="${p}"
                break
            fi
        done
        [[ -n "${FOUND_PORT}" ]] || die "No free Daphne port found"
        DAPHNE_PORT="${FOUND_PORT}"
        [[ -f "${ENV_FILE}" ]] && env_set DAPHNE_PORT "${DAPHNE_PORT}"
        ok "Switched Daphne port to ${DAPHNE_PORT}"
    else
        ok "Port ${DAPHNE_PORT} is free after cleanup"
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

    [[ -s requirements.txt ]] || die "requirements.txt is empty or missing."

    pip install -r requirements.txt
    ok "Dependencies installed"

    for pkg in \
        django_tenants \
        requests \
        celery \
        redis \
        pwa \
        channels \
        channels_redis \
        daphne \
        anymail
    do
        if ! python -c "import ${pkg}" 2>/dev/null; then
            die "Python package '${pkg}' not installed. Check requirements.txt."
        fi
    done
    ok "All required packages importable"

    for pkg in paychangu pyxrate; do
        python -c "import ${pkg}" 2>/dev/null \
            || warn "Python package '${pkg}' not installed — Phase 4 features disabled."
    done

    for app in apps.core.sync apps.realtime apps.communications; do
        if ! python -c "import ${app}" 2>/dev/null; then
            die "App not importable: ${app} — check SHARED_APPS/TENANT_APPS and the app directory."
        fi
        ok "App importable: ${app}"
    done
fi

# ============================================================================
# Step 3 — .env: create if missing, otherwise update in place
# ============================================================================
log "Step 3: Environment file"

EXISTING_SECRET_KEY=""
EXISTING_DB_PASSWORD=""
EXISTING_EMAIL_HOST_PASSWORD=""
if [[ -f "${ENV_FILE}" ]]; then
    EXISTING_SECRET_KEY="$(env_get SECRET_KEY)"
    EXISTING_DB_PASSWORD="$(env_get DB_PASSWORD)"
    EXISTING_EMAIL_HOST_PASSWORD="$(env_get EMAIL_HOST_PASSWORD)"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
    EXISTING_SECRET_KEY="${EXISTING_SECRET_KEY:-$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)}"
    EXISTING_DB_PASSWORD="${EXISTING_DB_PASSWORD:-$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)}"

    cat > "${ENV_FILE}" <<EOF
# ══════════════════════════════════════════════════════════════════════
# Pritech PMS — Production .env
# Managed by deploy_pritech_pms.sh — secrets preserved on re-deploy.
# ══════════════════════════════════════════════════════════════════════

SECRET_KEY=${EXISTING_SECRET_KEY}
DEBUG=False
DJANGO_SETTINGS_MODULE=config.settings

ALLOWED_HOSTS=${DOMAIN},.${DOMAIN},${SERVER_IP},localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://*.${DOMAIN}
SITE_URL=https://${DOMAIN}
TENANT_BASE_DOMAIN=${DOMAIN}

DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${EXISTING_DB_PASSWORD}
DB_HOST=127.0.0.1
DB_PORT=5432

REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CHANNEL_LAYER_REDIS_URL=redis://127.0.0.1:6379/2

DAPHNE_PORT=${DAPHNE_PORT}

SESSION_COOKIE_DOMAIN=
CSRF_COOKIE_DOMAIN=
SHOW_PUBLIC_IF_NO_TENANT_FOUND=False

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=mail.${DOMAIN}
EMAIL_PORT=465
EMAIL_HOST_USER=noreply@${DOMAIN}
EMAIL_HOST_PASSWORD=${EXISTING_EMAIL_HOST_PASSWORD}
EMAIL_USE_TLS=False
EMAIL_USE_SSL=True
DEFAULT_FROM_EMAIL="Pritech PMS <noreply@${DOMAIN}>"
SERVER_EMAIL=noreply@${DOMAIN}

MAILGUN_API_KEY=
MAILGUN_SENDER_DOMAIN=

SENTRY_DSN=
SENTRY_ENV=production

PAYCHANGU_ENABLED=False
PAYCHANGU_BASE_URL=https://api.paychangu.com
PAYCHANGU_SECRET_KEY=
PAYCHANGU_WEBHOOK_SECRET=

EIS_ENABLED=False
EIS_API_BASE_URL=https://dev-eis-api.mra.mw/api/v1
EIS_SANDBOX_MODE=True
EIS_API_KEY=
EIS_TIN=

WHATSAPP_ENABLED=False
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
WHATSAPP_API_VERSION=v21.0
EOF

    chmod 600 "${ENV_FILE}"
    ok "Created .env with generated secrets"
else
    ok ".env exists — updating deployment-critical values"

    EXISTING_SECRET_KEY="${EXISTING_SECRET_KEY:-$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)}"
    EXISTING_DB_PASSWORD="${EXISTING_DB_PASSWORD:-$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)}"

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
    env_set CHANNEL_LAYER_REDIS_URL        "redis://127.0.0.1:6379/2"
    env_set DAPHNE_PORT                    "${DAPHNE_PORT}"
    env_set SHOW_PUBLIC_IF_NO_TENANT_FOUND "False"

    env_set SECRET_KEY     "${EXISTING_SECRET_KEY}"
    env_set DB_PASSWORD    "${EXISTING_DB_PASSWORD}"

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

    env_set_if_missing MAILGUN_API_KEY       ""
    env_set_if_missing MAILGUN_SENDER_DOMAIN ""

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

    env_set_if_missing WHATSAPP_ENABLED              "False"
    env_set_if_missing WHATSAPP_PHONE_NUMBER_ID      ""
    env_set_if_missing WHATSAPP_ACCESS_TOKEN         ""
    env_set_if_missing WHATSAPP_APP_SECRET           ""
    env_set_if_missing WHATSAPP_WEBHOOK_VERIFY_TOKEN ""
    env_set_if_missing WHATSAPP_API_VERSION          "v21.0"

    if grep -qE '^DEFAULT_FROM_EMAIL=.*<.*>' "${ENV_FILE}" \
       && ! grep -qE '^DEFAULT_FROM_EMAIL="' "${ENV_FILE}"; then
        CURRENT_FROM="$(env_get DEFAULT_FROM_EMAIL)"
        env_set DEFAULT_FROM_EMAIL "\"${CURRENT_FROM}\""
        ok "Fixed quoting on DEFAULT_FROM_EMAIL"
    fi

    if ! grep -qE '^DEFAULT_FROM_EMAIL=.' "${ENV_FILE}"; then
        env_set DEFAULT_FROM_EMAIL "\"Pritech PMS <noreply@${DOMAIN}>\""
    fi

    chmod 600 "${ENV_FILE}"
    ok ".env updated"
fi

if grep -q $'\r' "${ENV_FILE}"; then
    sed -i 's/\r$//' "${ENV_FILE}"
    ok "Stripped CRLF from .env"
fi

DB_PASS="$(env_get DB_PASSWORD)"
[[ -n "${DB_PASS}" ]] || die "DB_PASSWORD missing from .env"

if [[ "${ENV_ONLY}" == "true" ]]; then
    banner ".env update complete"
    echo "  File: ${ENV_FILE}"
    echo "  Preview (secrets masked):"
    grep -vE '^(SECRET_KEY|DB_PASSWORD|EMAIL_HOST_PASSWORD|PAYCHANGU_SECRET_KEY|PAYCHANGU_WEBHOOK_SECRET|EIS_API_KEY|WHATSAPP_ACCESS_TOKEN|WHATSAPP_APP_SECRET|MAILGUN_API_KEY)=' "${ENV_FILE}" \
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
# Step 5 — Migrations: verify + generate + sanity-check
# ============================================================================
log "Step 5: Ensure all migrations exist and are current"

# ─── 5a. tenants ───
TENANTS_MIGRATION="${PROJECT_DIR}/apps/shared/tenants/migrations/0001_initial.py"
if [[ ! -f "${TENANTS_MIGRATION}" ]]; then
    warn "tenants/migrations/0001_initial.py missing — generating now"
    python manage.py makemigrations tenants
    if [[ -f "${TENANTS_MIGRATION}" ]]; then
        ok "Generated apps/shared/tenants/migrations/0001_initial.py"
        warn "⚠ Commit this file to git or it regenerates every deploy."
    else
        die "Failed to generate tenants migration."
    fi
else
    ok "tenants migration present"
fi

# ─── 5b. communications ───
COMM_MIGRATION="${PROJECT_DIR}/apps/communications/migrations/0001_initial.py"
if [[ ! -f "${COMM_MIGRATION}" ]]; then
    warn "communications/migrations/0001_initial.py missing — generating now"
    python manage.py makemigrations communications
    if [[ -f "${COMM_MIGRATION}" ]]; then
        ok "Generated apps/communications/migrations/0001_initial.py"
        warn "⚠ Commit this file to git or it regenerates every deploy."
    else
        warn "No migration generated for communications — check that the app has models."
    fi
else
    ok "communications migration present"
fi

# ─── 5c. General check ───
log "Step 5b: Running makemigrations --check --dry-run"
if ! python manage.py makemigrations --check --dry-run 2>&1 | tee /tmp/migrations-check.log | grep -q "No changes detected"; then
    warn "Model changes without migrations detected:"
    cat /tmp/migrations-check.log | sed 's/^/    /'
    warn "Generating them now (they MUST be committed to git afterwards):"
    python manage.py makemigrations
    warn "⚠ Run 'git add */migrations/ && git commit' from your dev machine."
else
    ok "All models have up-to-date migrations"
fi

# ─── 5d. Flatten nested static icons (self-heal) ───
log "Step 5c: Fix nested static icons if present"
if [[ -d "${PROJECT_DIR}/static/icons/icons" ]]; then
    warn "Detected static/icons/icons/ — flattening to static/icons/"
    mkdir -p "${PROJECT_DIR}/static/icons"
    mv "${PROJECT_DIR}/static/icons/icons"/*.png \
       "${PROJECT_DIR}/static/icons/" 2>/dev/null || true
    rm -rf "${PROJECT_DIR}/static/icons/icons"
    ok "Icons flattened"
else
    ok "Icon directory structure is correct"
fi

# ─── 5e. Migration inventory ───
log "Step 5d: Migration files in the repo"
find "${PROJECT_DIR}/apps" -path "*/migrations/*.py" \
    ! -name "__init__.py" -printf "    %P\n" | sort
ok "Migration inventory printed"

# ============================================================================
# Step 6 — Django check
# ============================================================================
log "Step 6: Django configuration check"
python manage.py check
ok "Django check passed"

# ============================================================================
# Step 7 — Migrate shared schema
# ============================================================================
log "Step 7: Apply migrations to shared schema (public)"
python manage.py migrate_schemas --shared --noinput
ok "Shared schema migrated"

# ============================================================================
# Step 8 — Public tenant
# ============================================================================
log "Step 8: Ensure public tenant exists"

python manage.py shell <<'PY'
from apps.shared.tenants.models import Tenant, Domain
from django.conf import settings

base_domain = 'localhost'
for h in settings.ALLOWED_HOSTS:
    if not h or h.startswith('.') or h in ('localhost', '127.0.0.1'):
        continue
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
# Step 9 — Apply migrations to every tenant schema
# ============================================================================
log "Step 9: Apply migrations to all tenant schemas"
python manage.py migrate_schemas --noinput
ok "All tenant schemas migrated"

# ============================================================================
# Step 9b — Post-migration verification
# ============================================================================
log "Step 9b: Verifying all schemas are up to date"
if python manage.py migrate_schemas --check 2>&1 | grep -q "No migrations to apply"; then
    ok "Every schema reports 'No migrations to apply' — all in sync"
else
    warn "Some schemas still have pending migrations — rerunning"
    python manage.py migrate_schemas --noinput
    ok "Second pass complete"
fi

# ============================================================================
# Step 10 — Collect static files + verify assets
# ============================================================================
log "Step 10: Collect static files"
python manage.py collectstatic --noinput --clear 2>&1 | tail -5
ok "Static files collected"

PWA_ASSETS=(
    "staticfiles/js/serviceworker.js"
    "staticfiles/js/offline-store.js"
    "staticfiles/js/offline-forms.js"
    "staticfiles/js/cache-warmup.js"
    "staticfiles/icons/icon-192.png"
    "staticfiles/icons/icon-512.png"
    "staticfiles/icons/apple-touch-icon.png"
)
MISSING=0
for asset in "${PWA_ASSETS[@]}"; do
    [[ -f "${PROJECT_DIR}/${asset}" ]] || { warn "Missing PWA asset: ${asset}"; MISSING=$((MISSING + 1)); }
done
[[ "${MISSING}" -eq 0 ]] && ok "All 7 PWA static assets present"

PHASE7_ASSETS=(
    "staticfiles/css/admin_motion.css"
    "staticfiles/js/admin_motion.js"
    "staticfiles/js/realtime.js"
)
MISSING7=0
for asset in "${PHASE7_ASSETS[@]}"; do
    [[ -f "${PROJECT_DIR}/${asset}" ]] || { warn "Missing Phase 7 asset: ${asset}"; MISSING7=$((MISSING7 + 1)); }
done
[[ "${MISSING7}" -eq 0 ]] && ok "All 3 Phase 7 static assets present"

TEMPLATES_TO_CHECK=(
    "templates/pages/offline.html"
    "templates/partials/_offline_indicator.html"
    "templates/partials/_pwa_install_prompt.html"
    "templates/pages/communications/log_list.html"
    "templates/pages/communications/inbound_list.html"
    "templates/pages/communications/template_list.html"
    "templates/pages/communications/log_detail.html"
    "templates/pages/communications/inbound_reply.html"
    "templates/pages/communications/template_form.html"
)
MISSING_T=0
for tpl in "${TEMPLATES_TO_CHECK[@]}"; do
    [[ -f "${PROJECT_DIR}/${tpl}" ]] || { warn "Missing template: ${tpl}"; MISSING_T=$((MISSING_T + 1)); }
done
[[ "${MISSING_T}" -eq 0 ]] && ok "All Phase 6 + 7 templates present"

# ─── Verify BOTH URLconfs import cleanly ───
log "Step 10b: Verify URL patterns AND both URLconf imports"
python manage.py shell <<'PY'
import importlib
from django.urls import reverse, NoReverseMatch

# 1) Both URLconfs must import — catches missing imports like comm_views
errors = []
for mod in ('config.urls', 'config.urls_public'):
    try:
        importlib.import_module(mod)
        print(f'  ✔ {mod} imports cleanly')
    except Exception as e:
        errors.append(f'{mod}: {type(e).__name__}: {e}')
        print(f'  ✘ {mod} import failed: {type(e).__name__}: {e}')

# 2) Named routes must reverse
checks = [
    ('tenant', 'offline'),
    ('tenant', 'sync:sync'),
    ('tenant', 'communications:log_list'),
    ('tenant', 'communications:inbound_list'),
    ('tenant', 'communications:template_list'),
]
for scope, name in checks:
    try:
        url = reverse(name)
        print(f'  ✔ {scope}:{name} → {url}')
    except NoReverseMatch:
        print(f'  ⚠ {scope}:{name} not reverse-resolvable')

# 3) WebSocket routing
try:
    from apps.realtime.routing import websocket_urlpatterns
    print(f'  ✔ apps.realtime.routing has {len(websocket_urlpatterns)} WebSocket routes')
except Exception as e:
    errors.append(f'apps.realtime.routing: {e}')
    print(f'  ✘ apps.realtime.routing failed to import: {e}')

if errors:
    import sys
    print('\n❌ URLconf errors — fix before restart:')
    for e in errors:
        print(f'   {e}')
    sys.exit(1)
PY
ok "URL verification done"

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
# Step 12 — Systemd services
# ============================================================================
log "Step 12: Systemd services (Daphne port: ${DAPHNE_PORT})"

cat > /etc/systemd/system/gunicorn-${PROJECT_NAME}.service <<EOF
[Unit]
Description=Gunicorn for Pritech PMS (HTTP)
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

cat > /etc/systemd/system/daphne-${PROJECT_NAME}.service <<EOF
[Unit]
Description=Daphne ASGI for Pritech PMS (WebSockets)
After=network.target redis-server.service postgresql.service

[Service]
User=root
Group=root
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="DJANGO_SETTINGS_MODULE=config.settings"
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${VENV_DIR}/bin/daphne \\
    -b 127.0.0.1 \\
    -p ${DAPHNE_PORT} \\
    --access-log - \\
    --proxy-headers \\
    config.asgi:application
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
systemctl enable gunicorn-${PROJECT_NAME}      >/dev/null
systemctl enable daphne-${PROJECT_NAME}        >/dev/null
systemctl enable celery-worker-${PROJECT_NAME} >/dev/null
systemctl enable celery-beat-${PROJECT_NAME}   >/dev/null
ok "Systemd services created and enabled"

# ============================================================================
# Step 15 — Nginx
# ============================================================================
log "Step 15: Nginx configuration (WS on port ${DAPHNE_PORT})"

cat > /etc/nginx/sites-available/${PROJECT_NAME} <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${WILDCARD};
    client_max_body_size 25M;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://\$host\$request_uri; }
}

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

    location = /serviceworker.js {
        alias ${PROJECT_DIR}/staticfiles/js/serviceworker.js;
        add_header Service-Worker-Allowed "/";
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        types { application/javascript js; }
        default_type application/javascript;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:${DAPHNE_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade           \$http_upgrade;
        proxy_set_header Connection        "upgrade";
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_buffering off;
    }

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
    if ! pgrep -f "certbot renew" >/dev/null 2>&1; then
        certbot renew --quiet --no-random-sleep-on-renew 2>&1 | tail -3 || true
    else
        warn "Another certbot process is running — skipping renewal"
    fi
else
    warn "No SSL cert — cannot auto-provision wildcard."
    warn "Run manually:"
    warn "  ~/.acme.sh/acme.sh --issue --dns \\"
    warn "    -d ${DOMAIN} -d '${WILDCARD}' \\"
    warn "    --yes-I-know-dns-manual-mode-enough-go-ahead-please"
fi

# ============================================================================
# Step 17 — Restart services (clean stop → kill stragglers → start)
# ============================================================================
log "Step 17: Restart services"

restart_clean() {
    local svc="$1"
    systemctl stop "${svc}" 2>/dev/null || true
    systemctl reset-failed "${svc}" 2>/dev/null || true
    sleep 1
    systemctl start "${svc}"
}

# Clean restart Daphne — kill any orphan first
pkill -f "daphne.*${PROJECT_NAME}" 2>/dev/null || true
sleep 1
if ss -tln 2>/dev/null | grep -q ":${DAPHNE_PORT} "; then
    warn "Port ${DAPHNE_PORT} still held — killing holder"
    fuser -k "${DAPHNE_PORT}/tcp" 2>/dev/null || true
    sleep 1
fi

restart_clean gunicorn-${PROJECT_NAME}
restart_clean daphne-${PROJECT_NAME}
restart_clean celery-worker-${PROJECT_NAME}
restart_clean celery-beat-${PROJECT_NAME}

sleep 3

FAILED=0
for s in \
    gunicorn-${PROJECT_NAME} \
    daphne-${PROJECT_NAME} \
    celery-worker-${PROJECT_NAME} \
    celery-beat-${PROJECT_NAME} \
    nginx
do
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
    local extra="${3:-}"
    local code
    if [[ -n "${extra}" ]]; then
        code=$(curl -sS -o /dev/null -w "%{http_code}" -k --max-time 10 ${extra} "$url" 2>/dev/null || echo "000")
    else
        code=$(curl -sS -o /dev/null -w "%{http_code}" -k --max-time 10 "$url" 2>/dev/null || echo "000")
    fi
    if [[ "${code}" =~ ^(200|301|302|400|405|426)$ ]]; then
        printf "  \033[1;32m%-26s %s\033[0m\n" "$label" "$code"
    else
        printf "  \033[1;31m%-26s %s\033[0m\n" "$label" "$code"
    fi
    echo "${code}"
}

log "  -- Phase 5: multi-tenant --"
C1=$(check "public"           "https://${DOMAIN}/")
C2=$(check "public-admin"     "https://${DOMAIN}/admin/")
C3=$(check "public-login"     "https://${DOMAIN}/login/")
C4=$(check "public-signup"    "https://${DOMAIN}/signup/")
C5=$(check "tenant-pritech"   "https://pritech.${DOMAIN}/")

log "  -- Phase 6: PWA --"
C6=$(check "manifest"         "https://${DOMAIN}/manifest.json")
C7=$(check "serviceworker"    "https://${DOMAIN}/serviceworker.js")
C8=$(check "offline-page"     "https://${DOMAIN}/offline/")
C9=$(check "icon-192"         "https://${DOMAIN}/static/icons/icon-192.png")
C10=$(check "sync-api"        "https://${DOMAIN}/api/v1/sync/" "-X POST -H 'Content-Type: application/json' -d '{\"operations\":[]}'")

log "  -- Phase 7: admin motion + realtime + WebSocket --"
C11=$(check "admin-motion-css" "https://${DOMAIN}/static/css/admin_motion.css")
C12=$(check "admin-motion-js"  "https://${DOMAIN}/static/js/admin_motion.js")
C13=$(check "realtime-js"      "https://${DOMAIN}/static/js/realtime.js")
C14=$(check "ws-endpoint"      "https://${DOMAIN}/ws/notifications/")
C15=$(check "comm-log"         "https://${DOMAIN}/communications/logs/")

# ============================================================================
# Done
# ============================================================================
chmod +x "${PROJECT_DIR}/deploy_pritech_pms.sh" 2>/dev/null || true

banner "Deploy complete — $(date '+%H:%M:%S')"
echo "  HEAD           : $(git -C ${PROJECT_DIR} rev-parse --short HEAD)"
echo "  Public site    : https://${DOMAIN}/"
echo "  Admin          : https://${DOMAIN}/admin/"
echo "  First tenant   : https://pritech.${DOMAIN}/"
echo "  PWA manifest   : https://${DOMAIN}/manifest.json"
echo "  Daphne port    : ${DAPHNE_PORT}"
echo "  WebSocket      : wss://${DOMAIN}/ws/notifications/"
echo ""

if [[ "${FAILED}" -gt 0 ]]; then
    warn "${FAILED} service(s) not active — see warnings above."
fi

if [[ "${C14}" == "502" || "${C14}" == "504" ]]; then
    warn "WebSocket endpoint returned ${C14} — Daphne not responding on ${DAPHNE_PORT}."
    warn "  Check: sudo systemctl status daphne-${PROJECT_NAME}"
    warn "  Logs:  sudo journalctl -u daphne-${PROJECT_NAME} -n 60 --no-pager"
fi

echo "  Logs:"
echo "    journalctl -u gunicorn-${PROJECT_NAME}      -n 40 --no-pager"
echo "    journalctl -u daphne-${PROJECT_NAME}        -n 40 --no-pager"
echo "    journalctl -u celery-worker-${PROJECT_NAME} -n 30 --no-pager"
echo ""
echo "  Superuser (if newly created): admin@pritechmw.com / ChangeMe123!"
echo "  ⚠ CHANGE THE SUPERUSER PASSWORD IMMEDIATELY"