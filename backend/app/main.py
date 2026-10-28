import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import admin, auth, client
from app.config import get_settings
from app.db import engine
from app.errors import install_error_handlers
from app.ratelimit import RateLimitMiddleware

cfg = get_settings()
logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Запись на массаж — API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
install_error_handlers(app)
app.add_middleware(RateLimitMiddleware, enabled=cfg.rate_limit_enabled)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in {cfg.frontend_url.rstrip("/"), cfg.app_base_url.rstrip("/")} if o],
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

api = APIRouter(prefix="/api/v1")
api.include_router(auth.router)
api.include_router(client.router)
api.include_router(admin.router)
app.include_router(api)


@app.get("/api/health", tags=["health"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
