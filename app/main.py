from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base
from app.core.redis import redis_client
from app.core.middleware import CorrelationMiddleware, setup_logging
from app.core.idempotency import IdempotencyMiddleware
from app.core.rate_limiting import RateLimitMiddleware
from app.domain.errors import JiraLiteError
from app.api.v1 import projects, issues, sprints, comments, search, health, auth, activity
from app.api import websocket

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        await redis_client.ping()
    except Exception:
        pass

    yield

    # Shutdown — graceful drain of WebSocket connections
    import logging
    logger = logging.getLogger("jiralite.shutdown")
    logger.info("Shutting down gracefully...")

    # Close all active WebSocket connections to drain in-flight traffic
    for project_id, connections in list(websocket.manager.active_connections.items()):
        for ws, user_id in connections:
            try:
                await ws.close(code=1000, reason="Server shutting down")
                logger.info("Closed WS connection for user %s on project %s", user_id, project_id)
            except Exception as exc:
                logger.warning("Failed to close WS connection: %s", exc)

    # Clean up database and cache connections
    await engine.dispose()
    try:
        await redis_client.aclose()
    except AttributeError:
        await redis_client.close()
    logger.info("Shutdown complete")


app = FastAPI(title="JiraLite", version="1.0.0", lifespan=lifespan)

# ── Middleware (order matters — CorrelationMiddleware must be outermost) ───────

app.add_middleware(CorrelationMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(JiraLiteError)
async def domain_error_handler(request: Request, exc: JiraLiteError):
    """
    Converts every typed domain error into a consistent JSON envelope.
    The correlation ID is echoed so clients can cross-reference server logs.
    """
    cid = getattr(request.state, "correlation_id", "unknown")
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error": exc.code,
            "message": str(exc),
            "correlation_id": cid,
        },
        headers={"X-Correlation-ID": cid},
    )

@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    import logging
    cid = getattr(request.state, "correlation_id", "unknown")
    logging.getLogger("jiralite").error(
        "Unhandled exception [%s]: %s", cid, str(exc), exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected server-side error occurred.",
            "correlation_id": cid,
        },
        headers={"X-Correlation-ID": cid},
    )

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(auth.router,      prefix="/api/v1/auth",     tags=["auth"])
app.include_router(projects.router,  prefix="/api/v1/projects", tags=["projects"])
app.include_router(issues.router,    prefix="/api/v1/issues",   tags=["issues"])
app.include_router(sprints.router,   prefix="/api/v1/sprints",  tags=["sprints"])
app.include_router(comments.router,  prefix="/api/v1/issues",   tags=["comments"])
app.include_router(search.router,    prefix="/api/v1/search",   tags=["search"])
app.include_router(activity.router,  prefix="/api/v1/projects", tags=["activity"])
app.include_router(health.router,    prefix="/api",             tags=["health"])
app.include_router(websocket.router, prefix="/ws",              tags=["websocket"])
