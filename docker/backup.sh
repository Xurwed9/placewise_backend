#!/bin/sh
set -eu

mkdir -p /backups

while true; do
    timestamp="$(date +%Y%m%d_%H%M%S)"
    target="/backups/placewise_${timestamp}.dump"

    echo "Creating database backup: ${target}"

    PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
        --host="${POSTGRES_HOST:-db}" \
        --username="${POSTGRES_USER}" \
        --dbname="${POSTGRES_DB}" \
        --format=custom \
        --file="${target}"

    find /backups -type f -name 'placewise_*.dump' -mtime +7 -delete

    sleep "${BACKUP_INTERVAL_SECONDS:-86400}"
done
