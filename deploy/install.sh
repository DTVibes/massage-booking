#!/bin/bash
# Установка на чистый сервер Ubuntu 22.04/24.04. Запускать от root из папки проекта:
#   bash deploy/install.sh
# Скрипт ставит Docker, спрашивает токен бота, ваш Telegram ID и домен,
# создаёт .env со случайными паролями и запускает приложение с HTTPS.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$(id -u)" -ne 0 ]; then echo "Запустите от root: sudo bash deploy/install.sh"; exit 1; fi

echo "==> Устанавливаю Docker..."
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q docker.io docker-compose-v2 git curl openssl
fi
# Docker Hub ограничивает доступ из некоторых стран — используем зеркало Google.
if [ ! -f /etc/docker/daemon.json ]; then
  mkdir -p /etc/docker
  echo '{ "registry-mirrors": ["https://mirror.gcr.io"] }' > /etc/docker/daemon.json
fi
systemctl enable --now docker >/dev/null 2>&1 || true
systemctl restart docker

if [ ! -f .env ]; then
  echo
  read -rp "Токен бота от @BotFather: " BOT_TOKEN
  read -rp "Ваш Telegram ID (цифры, узнать у @userinfobot): " ADMIN_ID
  read -rp "Домен (например massage-dt.ru): " DOMAIN
  DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN%/}"
  PG_PASS="$(openssl rand -hex 24)"
  SECRET="$(openssl rand -hex 32)"
  sed -e "s|^BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" \
      -e "s|^ADMIN_TELEGRAM_IDS=.*|ADMIN_TELEGRAM_IDS=${ADMIN_ID}|" \
      -e "s|^FRONTEND_URL=.*|FRONTEND_URL=https://${DOMAIN}|" \
      -e "s|^APP_BASE_URL=.*|APP_BASE_URL=https://${DOMAIN}|" \
      -e "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|" \
      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PG_PASS}|" \
      -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://massage:${PG_PASS}@localhost:5432/massage|" \
      -e "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" \
      .env.example > .env
  chmod 600 .env
  echo "==> Файл .env создан."
else
  echo "==> Файл .env уже есть — использую его."
fi

echo "==> Собираю и запускаю приложение (первый раз 5–10 минут)..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo
echo "==> Готово. Состояние сервисов:"
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
DOMAIN_SET="$(grep '^DOMAIN=' .env | cut -d= -f2)"
echo
echo "Откройте https://${DOMAIN_SET} — сертификат может выпускаться 1–2 минуты."
echo "Затем напишите боту /start в Telegram."
