# Запись на массаж — Telegram Mini App

[![CI](https://github.com/DTVibes/massage-booking/actions/workflows/ci.yml/badge.svg)](https://github.com/DTVibes/massage-booking/actions/workflows/ci.yml)
![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React 18](https://img.shields.io/badge/React_18-TypeScript-61DAFB?logo=react&logoColor=white)
![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?logo=docker&logoColor=white)

Онлайн-запись клиентов к массажисту внутри Telegram: клиент выбирает услугу, дату и свободное время, массажист управляет расписанием, клиентами, графиком и услугами в том же Mini App.

**Попробовать:** бот [@massage39bot](https://t.me/massage39bot) → «Записаться на массаж» (приложение открывается внутри Telegram).

<p>
  <img src="docs/screenshots/klient-1.webp" alt="Клиент: главная, выбор услуги, календарь, выбор времени, подтверждение" width="100%">
</p>

<details>
<summary><b>Ещё скриншоты</b>: после записи, панель массажиста</summary>

<img src="docs/screenshots/klient-2.webp" alt="Клиент: успешная запись, мои записи, перенос, профиль" width="100%">
<img src="docs/screenshots/admin-1.webp" alt="Массажист: расписание, карточка записи, месяц, клиенты, карточка клиента" width="100%">
<img src="docs/screenshots/admin-2.webp" alt="Массажист: рабочий график, услуги, настройки, ручная запись" width="100%">

</details>

### Главное

* **Двойная запись невозможна** — свободное время считает сервер, а окончательную гарантию даёт exclusion constraint PostgreSQL по интервалу времени (проверено тестами с 12 параллельными потоками и 8 HTTP-запросами).
* **Безопасный вход через Telegram** — подпись `initData` проверяется на сервере (HMAC-SHA256), роль администратора читается из БД на каждый запрос.
* **Надёжные уведомления** — задачи создаются в той же транзакции, что и запись; обработчик берёт их через `FOR UPDATE SKIP LOCKED`, повторяет при ошибках и учитывает лимиты Telegram.
* **Идемпотентность** — повторное нажатие «Записаться» не создаёт дубль (`Idempotency-Key`).
* **67 тестов** на настоящем PostgreSQL, GitHub Actions на каждый коммит, запуск в production одной командой с автоматическим HTTPS.

**Стек:** React 18 + TypeScript + Vite + Tailwind CSS · официальный Telegram Mini Apps SDK (`telegram-web-app.js`) · Python 3.13 + FastAPI + Pydantic + SQLAlchemy 2 + Alembic · PostgreSQL 16 · aiogram 3 · Docker Compose · Caddy · Pytest.

Подробно об устройстве, схеме БД, алгоритме слотов и принятых допущениях — [docs/architecture.md](docs/architecture.md).

## Возможности

**Клиент:** авторизация через Telegram (подпись `initData` проверяется сервером) · обязательный телефон перед первой записью · выбор услуги, даты (14 дней) и времени · подтверждение · «Мои записи» (предстоящие, история, отменённые) · отмена и перенос не позднее чем за 6 ч · профиль.

**Массажист:** расписание по дням, неделям и месяцам с фильтром по статусу · карточка записи с историей изменений · ручное создание записи (в т.ч. клиенту без Telegram) · перенос, отмена, «визит состоялся», «неявка» · клиенты с поиском, пагинацией, статистикой и внутренними заметками · недельный график с несколькими интервалами в день · исключения (выходной, закрытое время, перерыв, дополнительное время) с предупреждением о конфликтах · услуги · настройки · журнал изменений.

**Бот:** `/start`, `/book`, `/mybookings`, `/help`, кнопка открытия Mini App · подтверждения, отмены, переносы · напоминания за 24 и 2 часа · уведомления массажисту.

**Параметры по умолчанию** (меняются в «Настройках» без правки кода): услуга 60 мин, шаг 30 мин, буфер 10 мин, горизонт 14 дней, самостоятельная отмена не позднее чем за 6 ч, напоминания за 24 и 2 ч, график пн–пт 10:00–19:00.

---

## 1. Настройка Telegram-бота (BotFather)

1. Откройте [@BotFather](https://t.me/BotFather) → `/newbot` → задайте имя и username. Сохраните токен — это `BOT_TOKEN`.
2. Узнайте свой Telegram ID (например, через [@userinfobot](https://t.me/userinfobot)) — это `ADMIN_TELEGRAM_IDS`. Несколько администраторов — через запятую.
3. Mini App URL. Нужен публичный **HTTPS**-адрес фронтенда (`FRONTEND_URL`), например `https://booking.example.com`:
   * кнопка меню и кнопки в сообщениях бота настраиваются автоматически при старте бота, если `FRONTEND_URL` начинается с `https://`;
   * по желанию: `/mybots` → ваш бот → **Bot Settings → Configure Mini App → Enable Mini App** и укажите тот же URL — тогда приложение будет открываться и по ссылке `https://t.me/<bot>/<app>`;
   * по желанию: `/setdescription`, `/setuserpic` — описание и аватар бота.
4. Команды бота регистрируются автоматически при запуске (`/start`, `/book`, `/mybookings`, `/help`).

> Telegram открывает Mini App только по HTTPS. Для локальной проверки внутри Telegram используйте туннель (например, `cloudflared tunnel --url http://localhost:8080` или ngrok) и укажите выданный HTTPS-адрес в `FRONTEND_URL`.

## 2. Быстрый запуск в Docker (локально)

```bash
cp .env.example .env
# заполните BOT_TOKEN, ADMIN_TELEGRAM_IDS, POSTGRES_PASSWORD, SECRET_KEY, FRONTEND_URL
docker compose up -d --build
```

* Mini App и API: http://localhost:8080 (API — `/api/v1`, документация — `/api/docs`).
* При старте контейнер `api` сам применяет миграции (`alembic upgrade head`) и создаёт настройки, график и услугу по умолчанию (`python -m app.cli init`, повторный запуск ничего не меняет).
* Данные PostgreSQL хранятся в томе `pgdata` и сохраняются при перезапуске (`docker compose restart` / `down` без `-v`).

Полезные команды:

```bash
docker compose logs -f api bot worker                       # логи
docker compose exec api python -m app.cli create-admin --telegram-id 123456789 --name "Анна"
docker compose exec api python -m app.cli revoke-admin --telegram-id 123456789
docker compose exec api alembic current                     # версия схемы БД
```

### Первый администратор

Любой из двух способов:
* указать Telegram ID в `ADMIN_TELEGRAM_IDS` — роль назначится при входе;
* выполнить `python -m app.cli create-admin --telegram-id <ID>`.

Самостоятельно получить роль через приложение или API нельзя. Администратор, открыв Mini App, сразу попадает в панель управления; «Настройки → Открыть как клиент» показывает клиентский интерфейс.

## 3. Локальная разработка без Docker

Требуется Python 3.13, Node.js 22, PostgreSQL 16.

```bash
# база
createdb massage

# backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env          # DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/massage
alembic upgrade head
python -m app.cli init
uvicorn app.main:app --reload --port 8000   # API
python -m app.bot                            # бот (отдельный терминал)
python -m app.worker                         # уведомления (отдельный терминал)

# frontend
cd ../frontend
npm ci
npm run dev                                  # http://localhost:5173, /api проксируется на :8000
```

Открыть Mini App в обычном браузере (только `npm run dev`): сгенерируйте подписанный вашим `BOT_TOKEN` initData —

```bash
cd backend && python scripts/dev_init_data.py --telegram-id 123456789 --name "Анна" --url
```

и откройте выведенную ссылку. Подпись проверяется сервером так же, как настоящая; в production-сборке этот механизм отключён.

### Тесты

```bash
createdb massage_test
cd backend
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/massage_test pytest
```

Тесты используют настоящий PostgreSQL (нужны exclusion constraint и транзакции) и прогоняют миграции с нуля. Покрыто: проверка initData и сессий, права доступа и невозможность повысить роль, обязательный телефон, расчёт слотов, буфер, горизонт и часовой пояс, исключения графика, запрет прошедшего времени и времени вне графика, отмена за 6 ч, перенос (в т.ч. неудачный — исходная запись сохраняется), параллельное бронирование (потоки и HTTP), идемпотентность, конфликты при изменении графика, админ-операции, уведомления (дедупликация, повторы, ошибки Telegram), сохранность данных после переподключения.

## 4. Production-развёртывание

1. Сервер с Docker и Docker Compose (v2.24+), DNS-запись `A` для домена → IP сервера, открыты порты 80 и 443.
2. Скопируйте проект, создайте `.env` из `.env.example`:
   * `DOMAIN=booking.example.com`, `FRONTEND_URL=https://booking.example.com`, `APP_BASE_URL=https://booking.example.com`;
   * сложные `POSTGRES_PASSWORD` и `SECRET_KEY` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
3. Запустите с HTTPS (Caddy автоматически получит сертификат Let's Encrypt):

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

4. Откройте бота в Telegram → `/start` → «Записаться на массаж».
5. В панели администратора заполните «Настройки» (название, адрес, контакты), «Услуги» (стоимость) и «График».

Обновление: `git pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` — миграции применятся автоматически.

Если у вас уже есть reverse proxy (nginx, Traefik), не используйте `docker-compose.prod.yml`: проксируйте ваш HTTPS-домен на порт `WEB_PORT` (по умолчанию 8080).

## 5. Резервное копирование и восстановление

```bash
./scripts/backup.sh                    # создаёт backups/massage-YYYYMMDD-HHMMSS.dump (pg_dump, custom format)
KEEP_DAYS=30 ./scripts/backup.sh /mnt/backups
./scripts/restore.sh backups/massage-20261101-030000.dump   # спросит подтверждение
```

Рекомендуется ежедневный запуск по cron и копирование файлов за пределы сервера:

```
0 3 * * * cd /opt/massage-booking && ./scripts/backup.sh >> backups/backup.log 2>&1
```

Проверяйте восстановление на тестовой машине хотя бы раз в месяц. Восстановление останавливает `api`, `bot`, `worker`, заменяет данные и запускает их снова.

## 6. API

Префикс `/api/v1`, интерактивная документация — `/api/docs`. Ошибки в едином формате:

```json
{"error": {"code": "slot_taken", "message": "Это время только что заняли…", "details": null}}
```

Коды: `401` — нет или истекла авторизация, `403` — недостаточно прав, `404` — не найдено (в т.ч. чужая запись), `409` — конфликт (слот занят, поздно отменять, конфликт с графиком), `422` — невалидные данные, `429` — слишком частые запросы.

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/auth/telegram` | проверка initData, выдача сессии |
| GET | `/info` | публичные сведения: название, адрес, контакты, правила |
| GET / PATCH | `/me`, `/me/profile` | профиль, телефон, напоминания |
| GET | `/services` | активные услуги |
| GET | `/availability/dates`, `/availability/slots` | доступные даты и время |
| POST | `/appointments` | создание (заголовок `Idempotency-Key`) |
| GET | `/appointments/my` | свои записи |
| POST | `/appointments/{id}/cancel`, `/appointments/{id}/reschedule` | отмена, перенос |
| GET / POST | `/admin/appointments` | расписание за период (фильтр по статусу), ручное создание |
| GET / PATCH | `/admin/appointments/{id}` | карточка с историей; перенос, отмена, статус, комментарий |
| GET | `/admin/availability/slots` | свободные слоты для ручной записи и переноса |
| GET / POST | `/admin/clients` | клиенты (поиск, пагинация), добавление клиента без Telegram |
| GET / PATCH | `/admin/clients/{id}` | карточка клиента, заметки, блокировка |
| GET / PUT | `/admin/schedule` | недельный график (`force` — сохранить при конфликтах) |
| POST / DELETE | `/admin/schedule/exceptions[/{id}]` | исключения из графика |
| GET | `/admin/schedule/conflicts` | записи вне текущего графика |
| GET / POST / PATCH | `/admin/services[/{id}]` | услуги |
| GET / PATCH | `/admin/settings` | настройки |
| GET | `/admin/audit` | журнал действий администратора |

## 7. Переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | токен бота (только на сервере, во frontend не попадает) |
| `ADMIN_TELEGRAM_IDS` | Telegram ID администраторов через запятую |
| `DATABASE_URL` | строка подключения SQLAlchemy (`postgresql+psycopg://…`); в Docker собирается из `POSTGRES_*` |
| `APP_BASE_URL`, `FRONTEND_URL` | публичные адреса API и Mini App (разрешены в CORS; `FRONTEND_URL` — кнопка в боте) |
| `TIMEZONE` | часовой пояс по умолчанию при первой инициализации |
| `SECRET_KEY` | ключ подписи сессий |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | параметры контейнера PostgreSQL |
| `DOMAIN` | домен для HTTPS (`docker-compose.prod.yml`) |
| `SESSION_TTL_SECONDS`, `INIT_DATA_MAX_AGE_SECONDS` | срок сессии и допустимый возраст initData |
| `TELEGRAM_PROXY`, `TELEGRAM_API_URL` | прокси или зеркало Bot API, если с сервера заблокирован `api.telegram.org` (часто у хостингов в РФ) |
| `RATE_LIMIT_ENABLED`, `DEFAULT_PHONE_REGION`, `LOG_LEVEL`, `WEB_PORT`, `API_WORKERS` | прочее |

## 8. Известные ограничения

* Онлайн-оплата, абонементы, несколько массажистов и филиалов, внешние календари не входят в MVP (архитектура допускает расширение: снимки параметров в записях, буфер на уровне услуги, ограничение пересечений можно расширить полем `master_id` с `btree_gist`).
* Телефон вводится вручную и не подтверждается по SMS.
* Бот работает через long polling (один экземпляр процесса `bot`). Обработчиков уведомлений можно запускать несколько.
* Ограничитель частоты запросов хранится в памяти процесса API (каждый воркер uvicorn считает отдельно) — для нескольких серверов нужен общий лимитер.
* Сессия живёт 24 часа; после этого приложение автоматически переавторизуется по initData, а если и он устарел — просит открыть Mini App заново.
* Статусы «визит состоялся» / «неявка» массажист проставляет вручную.
* Telegram отправляет сообщения только тем, кто запускал бота или разрешил ему писать при открытии Mini App; остальным уведомления помечаются как пропущенные.
* Время на устройстве клиента не используется: все даты показываются в часовом поясе массажиста.
