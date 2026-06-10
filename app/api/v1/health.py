from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.redis import redis_client
from app.api.websocket import manager
from app.core.metrics import metrics_registry
from prometheus_client import generate_latest
import time

router = APIRouter()

@router.get("/health/live")
async def liveness():
    """Simple liveness — if this responds, the process is alive."""
    return {"status": "ok"}

@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """
    Readiness — checks DB and Redis are reachable.
    Returns 503 if either is down so load balancers stop routing traffic here.
    """
    checks = {}

    # Check DB
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"

    # Check Redis
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"

    all_ok = all(v == "ok" for v in checks.values())

    if not all_ok:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"status": "degraded", "checks": checks})

    return {"status": "ok", "checks": checks}

@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    return Response(
        content=generate_latest(metrics_registry),
        media_type="text/plain; version=0.0.4",
    )