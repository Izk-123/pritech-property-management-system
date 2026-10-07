#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <backup-file.dump>"
    exit 1
fi

BACKUP_FILE="$1"
DB_NAME="${DB_NAME:-pritech_pms_db}"
DB_USER="${DB_USER:-pritech_pms_user}"
DB_HOST="${DB_HOST:-127.0.0.1}"

echo "WARNING: This will DROP and recreate database '$DB_NAME'"
read -p "Press Enter to continue or Ctrl+C to cancel"

# Terminate connections
sudo -u postgres psql -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
"

# Drop and recreate
sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;"
sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"

# Restore
PGPASSWORD="$DB_PASSWORD" pg_restore \
    --host="$DB_HOST" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --jobs=4 \
    --verbose \
    "$BACKUP_FILE"

echo "Restore complete. Run 'python manage.py migrate_schemas' to verify."