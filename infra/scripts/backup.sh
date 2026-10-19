#!/usr/bin/env bash
# Nightly Postgres backup (cron on the VM):  15 3 * * * ~/doctune/infra/scripts/backup.sh
# Keeps 7 daily dumps locally; copy them off the VM (e.g. to R2 once it's set up) for real safety.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
dest=~/backups
mkdir -p "$dest"
file="$dest/doctune-$(date -u +%Y%m%d).sql.gz"
# DATABASE_URL_SYNC uses the SQLAlchemy driver prefix; pg_dump wants a plain postgres URL
url="${DATABASE_URL_SYNC/postgresql+psycopg/postgresql}"
docker run --rm postgres:16-alpine pg_dump --no-owner --no-privileges "$url" | gzip > "$file"
find "$dest" -name 'doctune-*.sql.gz' -mtime +7 -delete
echo "backup written: $file ($(du -h "$file" | cut -f1))"
