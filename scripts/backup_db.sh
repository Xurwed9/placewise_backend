#!/usr/bin/env bash
set -euo pipefail

# Local/manual backup helper. In docker-compose the `backup` service does this daily.
: "${DB_NAME:?DB_NAME is required}"
: "${DB_USER:?DB_USER is required}"
: "${DB_HOST:=127.0.0.1}"
: "${DB_PORT:=5432}"
: "${BACKUP_DIR:=./backups}"

mkdir -p "$BACKUP_DIR"
timestamp="$(date +%Y%m%d_%H%M%S)"
target="$BACKUP_DIR/placewise_${timestamp}.dump"

echo "Creating backup: $target"
PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --format=custom \
    --file="$target"

find "$BACKUP_DIR" -type f -name 'placewise_*.dump' -mtime +7 -delete
