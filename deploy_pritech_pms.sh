#!/bin/bash
set -euo pipefail

PROJECT_NAME="pritech-pms"
PROJECT_DIR="/home/project/pritech-pms"
VENV_DIR="$PROJECT_DIR/venv"
REPO_URL="https://github.com/Izk-123/pritech-property-management-system.git"
BRANCH="main"

DOMAIN="pms.pritechmw.com"
SERVER_IP="204.168.251.91"

DB_NAME="pritech_pms_db"
DB_USER="pritech_pms_user"
DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
DJANGO_SECRET="$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-50)"

echo "======================================================="
echo "Deploying Pritech PMS"
echo "Domain: $DOMAIN"
echo "DB: $DB_NAME / $DB_USER"
echo "DB password: $DB_PASS"
echo "======================================================="

# 1. Clone or update repo
if [ ! -d "$PROJECT_DIR/.git" ]; then
    git clone --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
else
    cd "$PROJECT_DIR"
    git stash || true
    git pull origin "$BRANCH"
    git stash pop || true
fi

cd "$PROJECT_DIR"

# 2. Python venv
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip wheel
pip install -r requirements.txt
pip install python-decouple psycopg2-binary gunicorn whitenoise django-tailwind django-auditlog

# 3. Create .env only once
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cat > "$PROJECT_DIR/.env" <<EOF
SECRET_KEY=$DJANGO_SECRET
DEBUG=False
ALLOWED_HOSTS=$DOMAIN,$SERVER_IP,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://$DOMAIN

DB_ENGINE=postgres
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASS
DB_HOST=127.0.0.1
DB_PORT=5432
EOF
    chmod 600 "$PROJECT_DIR/.env"
else
    echo ".env already exists — leaving it unchanged."
fi

# 4. PostgreSQL database + role
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
      CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';
   ELSE
      ALTER ROLE $DB_USER WITH PASSWORD '$DB_PASS';
   END IF;
END
\$\$;
SQL

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" \
    | grep -q 1 || sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"

# 5. Django setup
python manage.py migrate --noinput
python manage.py tailwind build || true
python manage.py collectstatic --noinput

DJANGO_SUPERUSER_PASSWORD='ChangeMe123!' \
python manage.py createsuperuser --noinput \
    --username admin --email admin@example.com || true

# 6. Gunicorn systemd service
sudo tee /etc/systemd/system/gunicorn-${PROJECT_NAME}.service > /dev/null <<EOF
[Unit]
Description=Gunicorn for Pritech PMS
After=network.target postgresql.service

[Service]
User=root
Group=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$VENV_DIR/bin/gunicorn --workers 3 --bind unix:$PROJECT_DIR/gunicorn.sock config.wsgi:application
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn-${PROJECT_NAME}

# 7. Nginx config
sudo tee /etc/nginx/sites-available/${PROJECT_NAME} > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 25M;

    location /static/ {
        alias $PROJECT_DIR/staticfiles/;
        expires 30d;
        access_log off;
    }

    location /media/ {
        alias $PROJECT_DIR/media/;
        expires 7d;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:$PROJECT_DIR/gunicorn.sock;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/${PROJECT_NAME} \
    /etc/nginx/sites-enabled/${PROJECT_NAME}

sudo nginx -t
sudo systemctl reload nginx

# 8. SSL with Certbot
if getent hosts "$DOMAIN" > /dev/null; then
    sudo certbot --nginx -d "$DOMAIN" \
        --non-interactive --agree-tos \
        --register-unsafely-without-email --redirect || true
else
    echo "DNS for $DOMAIN is not pointing here yet."
    echo "After DNS is live, run:"
    echo "sudo certbot --nginx -d $DOMAIN"
fi

# 9. Status
echo "======================================================="
echo "Deployment complete."
echo "Check service:"
echo "  sudo systemctl status gunicorn-${PROJECT_NAME}"
echo "Logs:"
echo "  sudo journalctl -u gunicorn-${PROJECT_NAME} -f"
echo "Site:"
echo "  https://$DOMAIN"
echo "  Admin: https://$DOMAIN/admin/"
echo "Superuser: admin / ChangeMe123!  <-- CHANGE THIS"
echo "======================================================="