"""Генерирует подписанный initData для локальной разработки без Telegram.

    python scripts/dev_init_data.py --telegram-id 111 --name "Иван"

Откройте http://localhost:5173/?initData=<вывод> (работает только в режиме vite dev).
Подпись делается вашим BOT_TOKEN, поэтому сервер проверяет её так же, как настоящую.
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.security import build_init_data  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--telegram-id", type=int, required=True)
parser.add_argument("--name", default="Тестовый клиент")
parser.add_argument("--url", action="store_true", help="вывести готовую ссылку на vite dev")
args = parser.parse_args()

token = get_settings().bot_token
if not token:
    raise SystemExit("BOT_TOKEN не задан")
init_data = build_init_data({"id": args.telegram_id, "first_name": args.name, "allows_write_to_pm": True}, token)
print(f"http://localhost:5173/?initData={quote(init_data)}" if args.url else init_data)
