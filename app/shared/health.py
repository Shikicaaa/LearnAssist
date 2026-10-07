import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.shared.config import get_settings
from app.shared.db import engine

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
    try:
        redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(status_code=200 if all_ok else 503, content=checks)
