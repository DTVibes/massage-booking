#!/bin/sh
# Резервная копия PostgreSQL: ./scripts/backup.sh [каталог]  (по умолчанию ./backups)
# Для ежедневного запуска добавьте в crontab:
#   0 3 * * * cd /opt/massage-booking && ./scripts/backup.sh >> backups/backup.log 2>&1
set -eu
DIR="${1:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p "$DIR"
FILE="$DIR/massage-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$FILE"
echo "Готово: $FILE ($(du -h "$FILE" | cut -f1))"
find "$DIR" -name 'massage-*.dump' -mtime +"$KEEP_DAYS" -delete
