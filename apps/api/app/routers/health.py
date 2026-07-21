from typing import Any

import asyncpg
from fastapi import APIRouter
from redis.asyncio import Redis

from apps.api.app.config import get_settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, str] = {}

    connection = await asyncpg.connect(settings.database_url)
    try:
        await connection.fetchval("SELECT 1")
        checks["postgres"] = "ok"
    finally:
        await connection.close()

    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.ping()
        checks["redis"] = "ok"
    finally:
        await redis.aclose()

    return {"status": "ok", "checks": checks}
