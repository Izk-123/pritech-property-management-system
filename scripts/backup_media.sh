#!/usr/bin/env bash
set -euo pipefail

MEDIA_DIR="${MEDIA_DIR:-/home/project/pritech-pms/media}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/pritech/media}"

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date -u +%Y%m%d)

tar --exclude='*.tmp' --exclude='cache/*' \
    -czf "$BACKUP_DIR/media_${TIMESTAMP}.tar.gz" \
    -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"

find "$BACKUP_DIR" -name "media_*.tar.gz" -mtime +14 -delete
echo "[$(date)] Media backup complete"