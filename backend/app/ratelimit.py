"""Простой ограничитель частоты запросов (скользящее окно, в памяти процесса).

Подходит для одного экземпляра backend (MVP). При масштабировании на несколько
экземпляров заменить на ограничение в reverse proxy или общем хранилище.
"""

import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# (префикс пути, метод или None) -> (запросов, окно в секундах)
RULES: list[tuple[str, str | None, int, int]] = [
    ("/api/v1/auth/", None, 20, 60),
    ("/api/v1/appointments", "POST", 20, 60),
    ("/api/v1/", None, 240, 60),
]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self._hits: dict[tuple, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _client_key(self, request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer ") and len(auth) > 20:
            return "t:" + auth[-24:]
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "?")
        return "ip:" + ip

    async def dispatch(self, request: Request, call_next):
        if self.enabled:
            path = request.url.path
            for prefix, method, limit, window in RULES:
                if path.startswith(prefix) and (method is None or method == request.method):
                    key = (prefix, method, self._client_key(request))
                    now = time.monotonic()
                    with self._lock:
                        q = self._hits[key]
                        while q and now - q[0] > window:
                            q.popleft()
                        if len(q) >= limit:
                            return JSONResponse(
                                {"error": {"code": "too_many_requests", "message": "Слишком много запросов, попробуйте позже", "details": None}},
                                status_code=429,
                                headers={"Retry-After": str(window)},
                            )
                        q.append(now)
                    break
        return await call_next(request)
