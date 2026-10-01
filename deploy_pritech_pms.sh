#!/usr/bin/env bash
# ============================================================================
# Pritech PMS — Production deployment script
#   Phase 5: multi-tenant via django-tenants
#   Phase 6: PWA + offline-first
#   Phase 7: Channels + Redis WebSockets + WhatsApp/email + animated admin
#   Phase 8: auth hardening (Argon2, 2FA, Axes, rate limits, JWT), CSP,
#            Chichewa localization, django-redis cache, health checks,
#            backups, DR docs
#   Phase 9: public listings + vacant rentals + tenant home + staff dashboard
#   Phase 9.1: Google Sign-In via allauth + phone validation
#
# Idempotent and self-healing. Fails fast on URLconf/middleware errors
# BEFORE attempting migrations. Auto-detects a free Daphne port, cleans
# stale processes, flattens nested static icons, reconciles public-schema
# drift, compiles translations, and verifies the auth stack.
#
# Phase 9.1 additions:
#   • Step 2b verifies allauth wiring in settings (AccountMiddleware,
#     INSTALLED_APPS, AUTHENTICATION_BACKENDS, SITE_ID, adapter class)
#     WITHOUT calling django.setup(), so a missing-middleware error is
#     reported as a clean one-line fix rather than a raw traceback.
#   • Step 2c bootstraps Django via django.setup() and then imports the
#     social adapter — because allauth's adapter module transitively
#     imports Django models and cannot be imported without app loading.
#   • Step 5 recognises allauth-specific failures and prints the exact
#     line of settings.py to change.
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
command -v msgfmt >/dev/null 2>&1 || \
    warn "msgfmt (gettext) not installed — Chichewa translations will not compile. Run: apt install gettext"

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
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
    log "Pre-flight: choosing Daphne port"

    port_is_bound() { ss -tln 2>/dev/null | grep -q ":$1 "; }
    port_owner() {
        ss -tlnp 2>/dev/null | grep ":$1 " \
            | grep -oP 'users:\(\("\K[^"]+' | head -1 || true
    }

    if ! port_is_bound "${DAPHNE_PORT}"; then
        ok "Port ${DAPHNE_PORT} is free"
    else
        owner="$(port_owner "${DAPHNE_PORT}")"
        if [[ "${owner}" == "daphne" ]]; then
            warn "Port ${DAPHNE_PORT} held by daphne — will be cleaned up in Step 0"
        else
            warn "Port ${DAPHNE_PORT} held by '${owner:-unknown}' — scanning for a free port"
            FOUND_PORT=""
            for p in $(seq $((DAPHNE_PORT + 1)) $((DAPHNE_PORT + 20))); do
                if ! port_is_bound "${p}"; then FOUND_PORT="${p}"; break; fi
            done
            [[ -n "${FOUND_PORT}" ]] || die "No free Daphne port in range"
            DAPHNE_PORT="${FOUND_PORT}"
            ok "Switched Daphne port to ${DAPHNE_PORT}"
        fi
    fi

    if [[ -f "${ENV_FILE}" ]]; then env_set DAPHNE_PORT "${DAPHNE_PORT}"; fi
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

    log "Pre-flight: checking Redis on DB 1 (cache)"
    if redis-cli -n 1 ping >/dev/null 2>&1; then
        ok "Redis DB 1 responding"
    else
        warn "Redis DB 1 not responding — django-redis cache will fall back to DB"
    fi

    log "Pre-flight: checking gettext"
    if command -v msgfmt >/dev/null 2>&1; then
        ok "msgfmt present ($(msgfmt --version | head -1))"
    else
        warn "msgfmt missing — install with: apt-get install -y gettext"
    fi
fi

# ============================================================================
# Step 0 — Cleanup stale project processes
# ============================================================================
if [[ "${ENV_ONLY}" != "true" ]]; then
    log "Step 0: Cleanup stale project processes"

    for svc in "daphne-${PROJECT_NAME}" "gunicorn-${PROJECT_NAME}"; do
        systemctl stop "${svc}" 2>/dev/null || true
    done
    systemctl reset-failed "daphne-${PROJECT_NAME}" 2>/dev/null || true
    systemctl reset-failed "gunicorn-${PROJECT_NAME}" 2>/dev/null || true
    sleep 1

    if ss -tln 2>/dev/null | grep -q ":${DAPHNE_PORT} "; then
        warn "Port ${DAPHNE_PORT} still bound — killing holder"
        fuser -k "${DAPHNE_PORT}/tcp" 2>/dev/null || true
        sleep 1
    fi

    pkill -f "daphne.*${PROJECT_NAME}" 2>/dev/null || true
    pkill -f "gunicorn.*${PROJECT_DIR}" 2>/dev/null || true
    sleep 1

    if ss -tln 2>/dev/null | grep -q ":${DAPHNE_PORT} "; then
        warn "Port ${DAPHNE_PORT} still held — selecting another"
        FOUND_PORT=""
        for p in $(seq $((DAPHNE_PORT + 1)) $((DAPHNE_PORT + 20))); do
            if ! ss -tln | grep -q ":${p} "; then FOUND_PORT="${p}"; break; fi
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

    # ── Core packages that must import ──────────────────────────────────
    for pkg in \
        django_tenants requests celery redis pwa \
        channels channels_redis daphne anymail
    do
        if ! python -c "import ${pkg}" 2>/dev/null; then
            die "Python package '${pkg}' not installed. Check requirements.txt."
        fi
    done
    ok "All core packages importable"

    # ── Phase 8 auth hardening ──────────────────────────────────────────
    for pkg in \
        django_otp two_factor axes django_ratelimit csp \
        django_redis rest_framework rest_framework_simplejwt argon2
    do
        if ! python -c "import ${pkg}" 2>/dev/null; then
            die "Phase 8 package '${pkg}' not installed. Check requirements.txt."
        fi
    done
    ok "All Phase 8 auth/CSP/cache packages importable"

    # ── Phase 9.1 — allauth ─────────────────────────────────────────────
    for pkg in allauth; do
        if ! python -c "import ${pkg}" 2>/dev/null; then
            die "Phase 9.1 package '${pkg}' not installed. Check requirements.txt."
        fi
    done
    python -c "import allauth.socialaccount.providers.google" 2>/dev/null \
        || die "allauth Google provider not installed. Check requirements.txt."
    ok "Phase 9.1 allauth packages importable"

    # ── Compliance packages — optional, warn only ───────────────────────
    for pkg in paychangu; do
        python -c "import ${pkg}" 2>/dev/null \
            || warn "Python package '${pkg}' not installed — Phase 4 features disabled."
    done
    python -c "import xrate" 2>/dev/null \
        || python -c "import pyxrate" 2>/dev/null \
        || warn "Python package for forex rates not importable — Phase 4 features disabled."

    # ── Project apps ────────────────────────────────────────────────────
    for app in apps.core.sync apps.realtime apps.communications \
               apps.shared.users apps.shared.tenants; do
        if ! python -c "import ${app}" 2>/dev/null; then
            die "App not importable: ${app}"
        fi
        ok "App importable: ${app}"
    done

    # ── Phase 8 modules — warn only (soft dependencies) ─────────────────
    for app in apps.shared.tenants.views_health apps.shared.tenants.tasks \
               apps.shared.users.middleware; do
        if ! python -c "import ${app}" 2>/dev/null; then
            warn "Module not importable: ${app} — some features disabled."
        fi
    done

    # ── Phase 9.1 — verify allauth wiring BEFORE any django.setup() ─────
    # django-allauth 65.x raises ImproperlyConfigured at AppConfig.ready()
    # if AccountMiddleware is missing. We check the settings here — WITHOUT
    # calling django.setup() — so the operator gets a one-line fix instead
    # of a raw traceback from inside Django's app registry.
    #
    # IMPORTANT: This reads settings via django.conf.settings (lazy, no
    # app loading) — it does NOT call setup().
    log "Step 2b: Verify Phase 9.1 allauth settings wiring"
    python - <<'PY' || die "Phase 9.1 settings wiring check failed — see above."
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Accessing django.conf.settings is lazy — it does NOT call django.setup().
from django.conf import settings

errors = []

# ── 1. allauth AccountMiddleware must be registered ─────────────────
if 'allauth.account.middleware.AccountMiddleware' not in settings.MIDDLEWARE:
    errors.append(
        "MIDDLEWARE is missing 'allauth.account.middleware.AccountMiddleware'.\n"
        "       Add it immediately AFTER "
        "'django.contrib.auth.middleware.AuthenticationMiddleware' in config/settings.py."
    )

# ── 2. allauth apps must be in INSTALLED_APPS ───────────────────────
required_apps = {
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
}
missing = required_apps - set(settings.INSTALLED_APPS)
if missing:
    errors.append(f"INSTALLED_APPS missing: {sorted(missing)}")

# ── 3. allauth auth backend must be registered ──────────────────────
if not any('allauth' in b for b in settings.AUTHENTICATION_BACKENDS):
    errors.append(
        "AUTHENTICATION_BACKENDS has no allauth backend — add "
        "'allauth.account.auth_backends.AuthenticationBackend'."
    )

# ── 4. SITE_ID must be set (django.contrib.sites) ───────────────────
if not getattr(settings, 'SITE_ID', None):
    errors.append(
        "SITE_ID is not set. Add 'django.contrib.sites' to SHARED_APPS "
        "and set SITE_ID = 1."
    )

# ── 5. SOCIALACCOUNT_ADAPTER must resolve to a real class ───────────
adapter_path = getattr(settings, 'SOCIALACCOUNT_ADAPTER', '')
if not adapter_path:
    errors.append("SOCIALACCOUNT_ADAPTER is not configured.")
else:
    try:
        module_path, _, class_name = adapter_path.rpartition('.')
        mod = __import__(module_path, fromlist=[class_name])
        if not hasattr(mod, class_name):
            errors.append(f"{adapter_path} exists but has no attribute {class_name!r}.")
    except Exception as exc:
        errors.append(f"Cannot import SOCIALACCOUNT_ADAPTER ({adapter_path}): {exc}")

if errors:
    print('', file=sys.stderr)
    print('  Phase 9.1 wiring problems:', file=sys.stderr)
    for e in errors:
        print(f'     ✘ {e}', file=sys.stderr)
    print('', file=sys.stderr)
    sys.exit(1)

print('    Phase 9.1 wiring OK')
PY
    ok "Phase 9.1 allauth wiring verified"

    # ── Phase 9.1 — REQUIRED modules (fail hard) ────────────────────────
    # apps.shared.users.adapters imports allauth's socialaccount adapter,
    # which transitively imports Django models. That import will raise
    # ImproperlyConfigured unless DJANGO_SETTINGS_MODULE is set and
    # django.setup() has been called — so we bootstrap Django here rather
    # than relying on a bare `python -c "import …"`.
    #
    # This runs AFTER Step 2b so that any missing-middleware error is
    # reported with a clean message rather than a raw traceback from
    # inside django.setup().
    log "Step 2c: Verify Phase 9.1 social adapter imports"
    if ! python - <<'PY' 2>&1
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    import django
    django.setup()
except Exception as exc:
    print(f"django.setup() failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(2)

try:
    from apps.shared.users.adapters import PritechSocialAccountAdapter  # noqa: F401
except Exception as exc:
    print(
        f"Cannot import PritechSocialAccountAdapter "
        f"({type(exc).__name__}: {exc})",
        file=sys.stderr,
    )
    sys.exit(3)

print("Adapter OK")
PY
    then
        die "Phase 9.1 module 'apps.shared.users.adapters' not importable — see error above."
    fi
    ok "Phase 9.1 social adapter importable"
fi

# ============================================================================
# Step 3 — .env
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

# ─── Phase 8 — auth hardening ─────────────────────────────────────────
AXES_ENABLED=True
TWO_FACTOR_ENABLED=True

# ─── Phase 8 — backups ────────────────────────────────────────────────
BACKUP_DIR=/var/backups/pritech
BACKUP_RETENTION_DAYS=30

# ─── Phase 9.1 — Google Sign-In ───────────────────────────────────────
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# ─── Phase 9.1 — Optional phone verification ──────────────────────────
VERIPHONE_API_KEY=
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
    env_set SECRET_KEY                     "${EXISTING_SECRET_KEY}"
    env_set DB_PASSWORD                    "${EXISTING_DB_PASSWORD}"

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
    env_set_if_missing AXES_ENABLED       "True"
    env_set_if_missing TWO_FACTOR_ENABLED "True"
    env_set_if_missing BACKUP_DIR            "/var/backups/pritech"
    env_set_if_missing BACKUP_RETENTION_DAYS "30"

    # ── Phase 9.1 — Google + Veriphone ──────────────────────────────────
    env_set_if_missing GOOGLE_CLIENT_ID     ""
    env_set_if_missing GOOGLE_CLIENT_SECRET ""
    env_set_if_missing VERIPHONE_API_KEY    ""

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
    grep -vE '^(SECRET_KEY|DB_PASSWORD|EMAIL_HOST_PASSWORD|PAYCHANGU_SECRET_KEY|PAYCHANGU_WEBHOOK_SECRET|EIS_API_KEY|WHATSAPP_ACCESS_TOKEN|WHATSAPP_APP_SECRET|MAILGUN_API_KEY|GOOGLE_CLIENT_SECRET|VERIPHONE_API_KEY)=' "${ENV_FILE}" \
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
# Step 5 — Django configuration check (fail fast BEFORE migrations)
# ============================================================================
log "Step 5: Verify Django configuration loads"

if ! python manage.py check > /tmp/django-check.log 2>&1; then
    warn "Django check FAILED — see traceback below."
    warn ""
    tail -30 /tmp/django-check.log | sed 's/^/    /'
    warn ""

    # ── Phase 9.1 — specific allauth failure modes ──────────────────────
    if grep -q "allauth.account.middleware.AccountMiddleware must be added to settings.MIDDLEWARE" \
            /tmp/django-check.log; then
        warn "Detected: django-allauth requires AccountMiddleware."
        warn ""
        warn "FIX: open config/settings.py, find the MIDDLEWARE list, and add"
        warn "this line immediately AFTER django.contrib.auth.middleware.AuthenticationMiddleware:"
        warn ""
        warn "    'allauth.account.middleware.AccountMiddleware',"
        warn ""
        warn "Then re-run this deploy script."

    elif grep -q "SOCIALACCOUNT_ADAPTER" /tmp/django-check.log \
         || grep -q "apps\.shared\.users\.adapters" /tmp/django-check.log; then
        warn "Detected: SOCIALACCOUNT_ADAPTER could not be resolved."
        warn ""
        warn "FIX: ensure apps/shared/users/adapters.py exists and exports the class"
        warn "named in settings.SOCIALACCOUNT_ADAPTER (PritechSocialAccountAdapter)."

    elif grep -q "No module named 'allauth.socialaccount.providers.google'" \
            /tmp/django-check.log; then
        warn "Detected: allauth Google provider not installed."
        warn ""
        warn "FIX: activate the venv and run:"
        warn "    pip install 'django-allauth[socialaccount]'"

    elif grep -q "No module named 'allauth'" /tmp/django-check.log; then
        warn "Detected: django-allauth itself is not installed."
        warn ""
        warn "FIX: activate the venv and run:"
        warn "    pip install -r requirements.txt"

    # ── Pre-existing Phase 8 checks ─────────────────────────────────────
    elif grep -q "Your URL pattern 'two_factor'" /tmp/django-check.log; then
        warn "Detected: two_factor URL include is broken."
        warn "config/urls_two_factor.py should unwrap the 2-tuple that"
        warn "django-two-factor-auth exposes. See the wrapper pattern."

    else
        warn "Common causes:"
        warn "  • A required package is missing — pip install -r requirements.txt"
        warn "  • An app is missing from SHARED_APPS"
        warn "  • A middleware class name is wrong"
        warn "  • A required middleware is missing (e.g. allauth AccountMiddleware)"
    fi

    warn "Full log: /tmp/django-check.log"
    die "Fix the error above and re-run the deploy script."
fi
ok "Django configuration is valid"

# ============================================================================
# Step 5a — Migrations: verify + generate + sanity-check
# ============================================================================
log "Step 5a: Ensure all migrations exist and are current"

MIGRATION_TS="$(date +%Y%m%d_%H%M%S)"

# ─── 5a.1 tenants ───
TENANTS_MIGRATION="${PROJECT_DIR}/apps/shared/tenants/migrations/0001_initial.py"
if [[ ! -f "${TENANTS_MIGRATION}" ]]; then
    warn "tenants/migrations/0001_initial.py missing — generating now"
    python manage.py makemigrations tenants --name "auto_${MIGRATION_TS}"
    [[ -f "${TENANTS_MIGRATION}" ]] && ok "Generated tenants migration" \
        || die "Failed to generate tenants migration."
else
    ok "tenants migration present"
fi

# ─── 5a.2 shared_users ───
SHARED_USERS_MIG_DIR="${PROJECT_DIR}/apps/shared/users/migrations"
if [[ -d "${SHARED_USERS_MIG_DIR}" ]] \
   && compgen -G "${SHARED_USERS_MIG_DIR}/[0-9]*.py" > /dev/null; then
    ok "shared_users migrations present"
else
    warn "shared_users has no migrations — generating now"
    mkdir -p "${SHARED_USERS_MIG_DIR}"
    touch "${SHARED_USERS_MIG_DIR}/__init__.py"
    python manage.py makemigrations shared_users --name "auto_${MIGRATION_TS}" || true
fi

# ─── 5a.3 communications ───
COMM_MIGRATION="${PROJECT_DIR}/apps/communications/migrations/0001_initial.py"
if [[ ! -f "${COMM_MIGRATION}" ]]; then
    warn "communications/migrations/0001_initial.py missing — generating now"
    python manage.py makemigrations communications --name "auto_${MIGRATION_TS}" || true
else
    ok "communications migration present"
fi

# ─── 5a.4 General check ───
log "Step 5a.4: Running makemigrations --check --dry-run"
set +e
MAKEMIGRATIONS_OUT=$(python manage.py makemigrations --check --dry-run 2>&1)
MAKEMIGRATIONS_RC=$?
set -e

if [[ ${MAKEMIGRATIONS_RC} -eq 0 ]] && echo "${MAKEMIGRATIONS_OUT}" | grep -q "No changes detected"; then
    ok "All models have up-to-date migrations"
else
    warn "Model changes without migrations detected:"
    echo "${MAKEMIGRATIONS_OUT}" | sed 's/^/    /'
    warn ""
    warn "Generating them now — COMMIT THEM TO GIT after this deploy:"
    python manage.py makemigrations --name "auto_${MIGRATION_TS}" || true
    warn ""
    warn "⚠⚠⚠  These files must be committed or they regenerate on every deploy."
fi

# ─── 5a.5 Flatten nested static icons ───
log "Step 5a.5: Fix nested static icons if present"
if [[ -d "${PROJECT_DIR}/static/icons/icons" ]]; then
    warn "Flattening static/icons/icons/ → static/icons/"
    mkdir -p "${PROJECT_DIR}/static/icons"
    mv "${PROJECT_DIR}/static/icons/icons"/*.png \
       "${PROJECT_DIR}/static/icons/" 2>/dev/null || true
    rm -rf "${PROJECT_DIR}/static/icons/icons"
    ok "Icons flattened"
else
    ok "Icon directory structure is correct"
fi

# ─── 5a.6 Migration inventory ───
log "Step 5a.6: Migration files in the repo"
find "${PROJECT_DIR}/apps" -path "*/migrations/*.py" \
    ! -name "__init__.py" -printf "    %P\n" | sort
ok "Migration inventory printed"

# ============================================================================
# Step 6 — Django check (second pass)
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
# Step 7b — Schema reconciliation (SHARED_APPS only)
# ============================================================================
log "Step 7b: Verify public schema matches shared-app models"

rm -f /tmp/drift-check.log /tmp/drift-check-status

set +e
python manage.py shell > /tmp/drift-check.log 2>&1 <<'PY'
import json
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.db import connection


def _shared_model(model):
    return model._meta.app_config.name in settings.SHARED_APPS


def _default_sql(field):
    if field.auto_now or field.auto_now_add:
        return "'1970-01-01 00:00:00+00'"
    if not field.has_default():
        return None
    try:
        val = field.get_default()
    except Exception:
        return None
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float, Decimal)):
        return str(val)
    if isinstance(val, (list, dict)):
        return "'" + json.dumps(val).replace("'", "''") + "'"
    return "'" + str(val).replace("'", "''") + "'"


fixed, unfixable = [], []
checked_models = checked_tables = 0

with connection.cursor() as cur:
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema()
    """)
    existing_tables = {r[0] for r in cur.fetchall()}

    for model in apps.get_models():
        if not _shared_model(model):
            continue
        checked_models += 1
        table = model._meta.db_table
        label = model._meta.label

        if table not in existing_tables:
            unfixable.append((label, table, '<TABLE_MISSING>'))
            print(f"UNFIXABLE|TABLE_MISSING|{label}|{table}", flush=True)
            continue

        checked_tables += 1
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
        """, [table])
        actual = {r[0] for r in cur.fetchall()}

        for field in model._meta.local_fields:
            if not field.column or field.column in actual:
                continue
            try:
                col_type = field.db_type(connection)
            except Exception as e:
                unfixable.append((label, table, field.column))
                print(f"UNFIXABLE|NO_DB_TYPE|{label}|{table}.{field.column}|{e}",
                      flush=True)
                continue
            if field.null:
                sql = (f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS '
                       f'"{field.column}" {col_type} NULL')
                kind = 'NULLABLE_COLUMN'
            else:
                default_sql = _default_sql(field)
                if default_sql is None:
                    unfixable.append((label, table, field.column))
                    print(f"UNFIXABLE|REQUIRED_COLUMN|{label}|{table}.{field.column}",
                          flush=True)
                    continue
                sql = (f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS '
                       f'"{field.column}" {col_type} NOT NULL DEFAULT {default_sql}')
                kind = 'REQUIRED_COLUMN_WITH_DEFAULT'
            try:
                cur.execute(sql)
                fixed.append((label, table, field.column))
                print(f"FIXED|{kind}|{label}|{table}.{field.column}", flush=True)
            except Exception as e:
                unfixable.append((label, table, field.column))
                print(f"FAILED|{label}|{table}.{field.column}|{e}", flush=True)

print(f"SUMMARY|shared_models={checked_models}|"
      f"tables_present={checked_tables}|"
      f"fixed={len(fixed)}|unfixable={len(unfixable)}", flush=True)

with open('/tmp/drift-check-status', 'w') as f:
    f.write('OK' if not unfixable else 'UNFIXABLE')
PY
set -e

STATUS="$(cat /tmp/drift-check-status 2>/dev/null || echo 'MISSING')"

case "${STATUS}" in
    OK)
        FIXED_N="$(grep -c '^FIXED|' /tmp/drift-check.log 2>/dev/null || true)"
        FIXED_N="${FIXED_N:-0}"
        SUMMARY="$(grep '^SUMMARY|' /tmp/drift-check.log | tail -1 || true)"
        if [[ "${FIXED_N}" -gt 0 ]]; then
            ok "Schema drift auto-repaired (${FIXED_N} column(s) added)"
            while IFS='|' read -r _ kind label col; do
                info "  + ${col}  (${kind})"
            done < <(grep '^FIXED|' /tmp/drift-check.log)
        else
            ok "Public schema matches shared-app models — no drift"
        fi
        [[ -n "${SUMMARY}" ]] && info "  ${SUMMARY}"
        ;;
    UNFIXABLE)
        warn "Schema drift detected that the script cannot safely repair:"
        while IFS='|' read -r _ kind label col rest; do
            warn "  ! ${col}  (${kind} in ${label})"
        done < <(grep '^UNFIXABLE|' /tmp/drift-check.log)
        die "Cannot continue with schema drift unresolved."
        ;;
    *)
        warn "Drift check did not complete cleanly (status='${STATUS}')"
        tail -40 /tmp/drift-check.log 2>/dev/null | sed 's/^/    /'
        die "Drift check failed."
        ;;
esac

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
# Step 8b — Ensure allauth Site record exists (Phase 9.1)
#
# django.contrib.sites requires one Site row. allauth uses it for
# default redirect URLs and email context. Idempotent.
# ============================================================================
log "Step 8b: Ensure allauth Site record exists"

python manage.py shell <<PY
from django.contrib.sites.models import Site

site, created = Site.objects.update_or_create(
    id=1,
    defaults={
        'domain': '${DOMAIN}',
        'name': 'Pritech PMS',
    },
)
print(f'Site: {"created" if created else "updated"} — {site.domain} ({site.name})')
PY
ok "allauth Site record ready"

# ============================================================================
# Step 9 — Apply migrations to every tenant schema
# (retry loop handles 'already exists' errors from regenerated migrations)
# ============================================================================
log "Step 9: Apply migrations to all tenant schemas"

MAX_MIGRATION_ATTEMPTS=15
MIGRATION_ATTEMPT=0
MIGRATION_DONE=false

while [[ ${MIGRATION_ATTEMPT} -lt ${MAX_MIGRATION_ATTEMPTS} ]]; do
    MIGRATION_ATTEMPT=$((MIGRATION_ATTEMPT + 1))

    rm -f /tmp/migrate-tenants.log
    set +e
    python manage.py migrate_schemas --noinput 2>&1 | tee /tmp/migrate-tenants.log
    MIGRATE_RC=${PIPESTATUS[0]}
    set -e

    if [[ ${MIGRATE_RC} -eq 0 ]]; then
        MIGRATION_DONE=true
        if [[ ${MIGRATION_ATTEMPT} -eq 1 ]]; then
            ok "All tenant schemas migrated"
        else
            ok "All tenant schemas migrated after ${MIGRATION_ATTEMPT} attempts"
        fi
        break
    fi

    if ! grep -qE 'already exists|DuplicateTable|DuplicateColumn' /tmp/migrate-tenants.log; then
        warn "Migration failed with an unexpected error (not 'already exists')."
        tail -40 /tmp/migrate-tenants.log | sed 's/^/    /'
        die "Cannot auto-recover."
    fi

    FAILED_MIG="$(grep -oP 'Applying \K[a-z_]+\.\d+_\w+' /tmp/migrate-tenants.log | tail -1 || true)"

    if [[ -z "${FAILED_MIG}" ]]; then
        warn "Could not identify failing migration."
        tail -40 /tmp/migrate-tenants.log | sed 's/^/    /'
        die "Manual intervention required."
    fi

    FAILED_APP="${FAILED_MIG%.*}"
    FAILED_NAME="${FAILED_MIG#*.}"
    DUP_OBJECT="$(grep -oP '(?:relation|column) "\K[^"]+(?=" already exists)' /tmp/migrate-tenants.log | tail -1 || true)"

    warn "Attempt ${MIGRATION_ATTEMPT}/${MAX_MIGRATION_ATTEMPTS}: '${FAILED_MIG}' failed — ${DUP_OBJECT:-object} already exists."
    info "Faking '${FAILED_APP}.${FAILED_NAME}' where the effect is present..."

    python manage.py shell <<PY
from django.db import connection
from django_tenants.utils import get_tenant_model

APP = "${FAILED_APP}"
NAME = "${FAILED_NAME}"
DUP_OBJECT = "${DUP_OBJECT}"

Tenant = get_tenant_model()
faked = skipped = 0

for tenant in Tenant.objects.all():
    connection.set_schema(tenant.schema_name)
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM django_migrations WHERE app = %s AND name = %s",
                    [APP, NAME])
        if cur.fetchone():
            continue
        if DUP_OBJECT:
            cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", [DUP_OBJECT])
            found = cur.fetchone() is not None
            if not found:
                cur.execute("SELECT 1 FROM information_schema.columns "
                            "WHERE column_name = %s LIMIT 1", [DUP_OBJECT])
                found = cur.fetchone() is not None
            if not found:
                print(f'  SKIP {tenant.schema_name}: {DUP_OBJECT} not present')
                skipped += 1
                continue
        cur.execute("INSERT INTO django_migrations (app, name, applied) "
                    "VALUES (%s, %s, NOW())", [APP, NAME])
        faked += 1
        print(f'  FAKED {APP}.{NAME} in {tenant.schema_name}')

print(f'\nFaked {faked} record(s), skipped {skipped} schema(s).')
PY

    sleep 1
done

if [[ "${MIGRATION_DONE}" != "true" ]]; then
    warn "Could not resolve all migration errors after ${MAX_MIGRATION_ATTEMPTS} attempts."
    die "Manual intervention required."
fi

# ============================================================================
# Step 9b — Post-migration verification
# ============================================================================
log "Step 9b: Verifying all schemas are up to date"
if python manage.py migrate_schemas --check 2>&1 | grep -q "No migrations to apply"; then
    ok "Every schema reports 'No migrations to apply'"
else
    warn "Some schemas still have pending migrations — rerunning"
    python manage.py migrate_schemas --noinput
    ok "Second pass complete"
fi

# ============================================================================
# Step 9c — Compile translations
# ============================================================================
log "Step 9c: Compiling translations"

mkdir -p "${PROJECT_DIR}/locale/en/LC_MESSAGES" \
         "${PROJECT_DIR}/locale/ny/LC_MESSAGES"

if ! command -v msgfmt >/dev/null 2>&1; then
    warn "msgfmt (gettext) not installed — Chichewa UI will fall back to English."
else
    set +e
    COMPILE_OUT=$(python manage.py compilemessages 2>&1)
    COMPILE_RC=$?
    set -e

    if [[ ${COMPILE_RC} -eq 0 ]]; then
        ok "Translations compiled"
        for lang in en ny; do
            MO_FILE="${PROJECT_DIR}/locale/${lang}/LC_MESSAGES/django.mo"
            if [[ -f "${MO_FILE}" ]]; then
                info "  ✔ locale/${lang}/LC_MESSAGES/django.mo ($(stat -c%s "${MO_FILE}") bytes)"
            else
                warn "  ✘ locale/${lang}/LC_MESSAGES/django.mo NOT generated"
            fi
        done
    else
        warn "compilemessages failed (exit ${COMPILE_RC})"
        echo "${COMPILE_OUT}" | tail -15 | sed 's/^/    /'
        if echo "${COMPILE_OUT}" | grep -q "duplicate message definition"; then
            warn "Duplicate msgid — dedupe the .po then re-run compilemessages."
        fi
        warn "Continuing — app runs fine, Chichewa strings fall back to English."
    fi
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

PHASE8_TEMPLATES=(
    "templates/registration/password_reset_form.html"
    "templates/registration/password_reset_done.html"
    "templates/registration/password_reset_confirm.html"
    "templates/registration/password_reset_complete.html"
    "templates/registration/password_reset_email.txt"
    "templates/registration/password_reset_subject.txt"
    "templates/partials/_language_switcher.html"
)
MISSING8=0
for tpl in "${PHASE8_TEMPLATES[@]}"; do
    [[ -f "${PROJECT_DIR}/${tpl}" ]] || { warn "Missing Phase 8 template: ${tpl}"; MISSING8=$((MISSING8 + 1)); }
done
[[ "${MISSING8}" -eq 0 ]] && ok "All 7 Phase 8 templates present"

PHASE9_TEMPLATES=(
    "templates/pages/dashboard.html"
    "templates/pages/properties/rent_list.html"
)
MISSING9=0
for tpl in "${PHASE9_TEMPLATES[@]}"; do
    [[ -f "${PROJECT_DIR}/${tpl}" ]] || { warn "Missing Phase 9 template: ${tpl}"; MISSING9=$((MISSING9 + 1)); }
done
[[ "${MISSING9}" -eq 0 ]] && ok "All Phase 9 templates present"

# ─── Verify BOTH URLconfs import cleanly ───
log "Step 10b: Verify URL patterns AND both URLconf imports"
python manage.py shell <<'PY'
import importlib
from django.urls import reverse, NoReverseMatch

errors = []
for mod in ('config.urls', 'config.urls_public'):
    try:
        importlib.import_module(mod)
        print(f'  ✔ {mod} imports cleanly')
    except Exception as e:
        errors.append(f'{mod}: {type(e).__name__}: {e}')
        print(f'  ✘ {mod} import failed: {type(e).__name__}: {e}')

checks = [
    ('tenant', 'home'),
    ('tenant', 'dashboard'),
    ('tenant', 'offline'),
    ('tenant', 'sync:sync'),
    ('tenant', 'communications:log_list'),
    ('tenant', 'communications:inbound_list'),
    ('tenant', 'communications:template_list'),
    ('tenant', 'health'),
    ('tenant', 'password_reset'),
    ('tenant', 'password_reset_done'),
    ('tenant', 'password_reset_complete'),
    ('tenant', 'properties:list'),
    ('tenant', 'properties:rent_list'),
    ('tenant', 'signup:signup'),
    ('tenant', 'signup:signup_success'),
]
for scope, name in checks:
    try:
        url = reverse(name)
        print(f'  ✔ {scope}:{name} → {url}')
    except NoReverseMatch:
        print(f'  ⚠ {scope}:{name} not reverse-resolvable')

# Public-schema checks
for name in ('two_factor:login', 'two_factor:setup',
             'public_home', 'account_login', 'account_signup',
             'socialaccount_login'):
    try:
        url = reverse(name)
        print(f'  ✔ public:{name} → {url}')
    except NoReverseMatch:
        print(f'  ⚠ public:{name} not reverse-resolvable')

try:
    from apps.realtime.routing import websocket_urlpatterns
    print(f'  ✔ apps.realtime.routing has {len(websocket_urlpatterns)} WebSocket routes')
except Exception as e:
    errors.append(f'apps.realtime.routing: {e}')
    print(f'  ✘ apps.realtime.routing failed to import: {e}')

try:
    from django.conf import settings as s
    backends = s.AUTHENTICATION_BACKENDS
    if any('axes' in b for b in backends):
        print(f'  ✔ Axes backend registered ({len(backends)} total)')
    else:
        print(f'  ⚠ Axes backend NOT in AUTHENTICATION_BACKENDS')
    if any('allauth' in b for b in backends):
        print(f'  ✔ allauth backend registered')
    else:
        print(f'  ⚠ allauth backend NOT in AUTHENTICATION_BACKENDS')
    if 'allauth.account.middleware.AccountMiddleware' in s.MIDDLEWARE:
        print(f'  ✔ allauth AccountMiddleware registered')
    else:
        print(f'  ⚠ allauth AccountMiddleware NOT in MIDDLEWARE')
    if s.PASSWORD_HASHERS and 'Argon2' in s.PASSWORD_HASHERS[0]:
        print(f'  ✔ Argon2 is the default password hasher')
    else:
        print(f'  ⚠ Argon2 is not the first password hasher')
    if getattr(s, 'SITE_ID', None) == 1:
        print(f'  ✔ SITE_ID = 1')
    else:
        print(f'  ⚠ SITE_ID missing or not 1')
except Exception as e:
    print(f'  ⚠ Could not inspect settings: {e}')

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

    location = /health/ {
        proxy_http_version 1.1;
        proxy_pass http://unix:${PROJECT_DIR}/gunicorn.sock;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        access_log off;
    }

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
fi

# ============================================================================
# Step 17 — Restart services
# ============================================================================
log "Step 17: Restart services"

restart_clean() {
    local svc="$1"
    systemctl stop "${svc}" 2>/dev/null || true
    systemctl reset-failed "${svc}" 2>/dev/null || true
    sleep 1
    systemctl start "${svc}"
}

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
    local label="$1" url="$2" extra="${3:-}"
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

log "  -- Phase 7: realtime --"
C14=$(check "ws-endpoint"     "https://${DOMAIN}/ws/notifications/")

log "  -- Phase 8: auth + health --"
C16=$(check "health"          "https://${DOMAIN}/health/")
C17=$(check "password-reset"  "https://${DOMAIN}/password-reset/")
C19=$(check "2fa-login"       "https://${DOMAIN}/account/login/")

log "  -- Phase 9: listings --"
C21=$(check "properties-list" "https://pritech.${DOMAIN}/properties/")
C22=$(check "properties-rent" "https://pritech.${DOMAIN}/properties/rent/")
C23=$(check "dashboard"       "https://pritech.${DOMAIN}/dashboard/")

log "  -- Phase 9.1: allauth / Google --"
C24=$(check "allauth-login"     "https://${DOMAIN}/accounts/login/")
C25=$(check "allauth-signup"    "https://${DOMAIN}/accounts/signup/")
C26=$(check "google-login"      "https://${DOMAIN}/accounts/google/login/")

HEALTH_BODY=$(curl -sS -k --max-time 10 "https://${DOMAIN}/health/" 2>/dev/null || echo '{}')
if echo "${HEALTH_BODY}" | grep -q '"status": "ok"'; then
    ok "Health check reports status=ok"
    echo "${HEALTH_BODY}" | sed 's/^/    /'
elif echo "${HEALTH_BODY}" | grep -q '"status": "degraded"'; then
    warn "Health check reports status=degraded:"
    echo "${HEALTH_BODY}" | sed 's/^/    /'
else
    warn "Health check did not return recognizable JSON"
fi

if [[ -f "${PROJECT_DIR}/locale/ny/LC_MESSAGES/django.mo" ]]; then
    ok "Chichewa translations compiled and present"
else
    warn "Chichewa .mo file missing — run: python manage.py compilemessages"
fi

# ============================================================================
# Done
# ============================================================================
chmod +x "${PROJECT_DIR}/deploy_pritech_pms.sh" 2>/dev/null || true

for script in backup_db.sh backup_media.sh restore_db.sh; do
    [[ -f "${PROJECT_DIR}/scripts/${script}" ]] && \
        chmod +x "${PROJECT_DIR}/scripts/${script}" 2>/dev/null || true
done

banner "Deploy complete — $(date '+%H:%M:%S')"
echo "  HEAD           : $(git -C ${PROJECT_DIR} rev-parse --short HEAD)"
echo "  Public site    : https://${DOMAIN}/"
echo "  Admin          : https://${DOMAIN}/admin/"
echo "  First tenant   : https://pritech.${DOMAIN}/"
echo "  Health check   : https://${DOMAIN}/health/"
echo "  Daphne port    : ${DAPHNE_PORT}"
echo "  WebSocket      : wss://${DOMAIN}/ws/notifications/"
echo ""

if [[ "${FAILED}" -gt 0 ]]; then
    warn "${FAILED} service(s) not active — see warnings above."
fi

echo "  ─── Google Sign-In: one-time setup ──────────────────────────────"
echo "  1. Configure OAuth client at https://console.cloud.google.com/apis/credentials"
echo "     Authorized redirect URI:"
echo "       https://${DOMAIN}/accounts/google/login/callback/"
echo "       https://*.${DOMAIN}/accounts/google/login/callback/"
echo "  2. Add to .env:"
echo "       GOOGLE_CLIENT_ID=..."
echo "       GOOGLE_CLIENT_SECRET=..."
echo "  3. Restart: sudo systemctl restart gunicorn-${PROJECT_NAME} daphne-${PROJECT_NAME}"
echo ""
echo "  Superuser (if newly created): admin@pritechmw.com / ChangeMe123!"
echo "  ⚠ CHANGE THE SUPERUSER PASSWORD IMMEDIATELY"