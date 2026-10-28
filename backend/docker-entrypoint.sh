#!/bin/sh
set -e

case "$1" in
  api)
    # Миграции и начальные данные (идемпотентно) перед стартом API.
    alembic upgrade head
    python -m app.cli init
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers "${API_WORKERS:-2}"
    ;;
  bot)
    exec python -m app.bot
    ;;
  worker)
    exec python -m app.worker
    ;;
  *)
    exec "$@"
    ;;
esac
