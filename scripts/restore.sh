#!/bin/sh
# Восстановление из резервной копии: ./scripts/restore.sh backups/massage-YYYYMMDD-HHMMSS.dump
# ВНИМАНИЕ: текущие данные в базе будут заменены данными из копии.
set -eu
FILE="${1:?Укажите файл резервной копии}"
[ -f "$FILE" ] || { echo "Файл не найден: $FILE"; exit 1; }
printf "Восстановить базу из %s? Текущие данные будут заменены. [yes/N] " "$FILE"
read -r ANSWER
[ "$ANSWER" = "yes" ] || { echo "Отменено"; exit 1; }
docker compose stop api bot worker
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$FILE"
docker compose start api bot worker
echo "Восстановлено из $FILE"
