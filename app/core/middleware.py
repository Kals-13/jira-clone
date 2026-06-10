import uuid
import time
import logging
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.core.metrics import MetricsCollector

# Propagates correlation ID through the entire async call stack for a request.
# Any logger in the app can call correlation_id_ctx.get() to read the current ID.
correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="no-correlation-id"
)


class CorrelationFilter(logging.Filter):
    """Injects correlation_id into every log record automatically."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get()
        return True


def setup_logging() -> None:
    """
    Configures structured logging with correlation ID in every log line.
    Call once at application startup before the first request.
    """
    fmt = "%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    filt = CorrelationFilter()
    for handler in logging.root.handlers:
        handler.addFilter(filt)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Per-request middleware that:
    1. Reads X-Correlation-ID from the request header (or generates a fresh UUID).
    2. Stores it in both request.state and the async context variable so any
       downstream logger automatically picks it up.
    3. Echoes it back in the response header so clients can trace their requests.
    4. Logs method, path, status code, and wall-clock latency for every request.
    """

    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_ctx.set(cid)
        request.state.correlation_id = cid

        start = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        duration_s = duration_ms / 1000.0
        response.headers["X-Correlation-ID"] = cid

        logging.getLogger("jiralite.request").info(
            "%s %s → %d (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        try:
            MetricsCollector.record_http_request(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
                duration_seconds=duration_s,
            )
        except Exception as exc:
            logging.getLogger("jiralite.metrics").warning("Failed to record request metric: %s", exc)

        return response
