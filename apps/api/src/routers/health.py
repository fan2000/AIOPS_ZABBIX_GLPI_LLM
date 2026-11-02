"""Routes de santé, liveness et readiness pour Docker et Kubernetes."""

from fastapi import APIRouter, Response, status
from database.connection import engine
from packages.connectors.redis_streams import redis_streams

router = APIRouter(tags=["Health"])


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict:
    """Vérifie que l'API est en vie."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe(response: Response) -> dict:
    """Vérifie la connectivité de la base PostgreSQL et de Redis."""
    db_ok = False
    redis_ok = False

    # Test DB
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    # Test Redis
    try:
        client = await redis_streams.get_client()
        redis_ok = client is not None
    except Exception:
        redis_ok = False

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if db_ok else "degraded",
        "database_connected": db_ok,
        "redis_connected": redis_ok,
    }
