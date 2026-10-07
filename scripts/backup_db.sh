#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${DB_NAME:-pritech_pms_db}"
DB_USER="${DB_USER:-pritech_pms_user}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pritech}"
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/pritech_pms_${TIMESTAMP}.dump"

echo "[$(date)] Starting database backup → $BACKUP_FILE"

PGPASSWORD="$DB_PASSWORD" pg_dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --format=custom \
    --compress=9 \
    --file="$BACKUP_FILE" \
    "$DB_NAME"

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date)] Backup complete: $BACKUP_SIZE"

# Verify integrity
if pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
    echo "[$(date)] Integrity check passed"
else
    echo "[$(date)] ERROR: backup file is corrupt"
    exit 1
fi

# Prune old backups
find "$BACKUP_DIR" -name "pritech_pms_*.dump" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] Pruned backups older than $RETENTION_DAYS days"