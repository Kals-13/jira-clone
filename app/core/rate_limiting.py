import os
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.redis import redis_client
from app.core.middleware import correlation_id_ctx

logger = logging.getLogger("jiralite.ratelimit")

RATE_LIMIT_PER_USER = 100  # requests per minute
RATE_LIMIT_PER_IP = 1000   # requests per minute
DISABLE_RATE_LIMIT = os.getenv("DISABLE_RATE_LIMIT", "false").lower() == "true"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Token-bucket rate limiting:
    - Per-user limit: 100 req/min (authenticated users)
    - Per-IP limit: 1000 req/min (all traffic)

    Requests that exceed the limit get 429 Too Many Requests.
    Rate limits are stored in Redis with 60s TTL.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting if disabled (for load testing)
        if DISABLE_RATE_LIMIT:
            return await call_next(request)

        # Extract user ID from token if authenticated
        cid = correlation_id_ctx.get()
        client_ip = request.client.host if request.client else "unknown"
        user_id = None

        # Try to extract user ID from Authorization header (without full auth dependency)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                from app.core.security import decode_token
                payload = decode_token(token)
                user_id = payload.get("sub")
            except Exception:
                pass

        # Check rate limits
        try:
            # Per-IP limit
            ip_key = f"ratelimit:ip:{client_ip}"
            ip_count = await redis_client.incr(ip_key)
            if ip_count == 1:
                await redis_client.expire(ip_key, 60)

            if ip_count > RATE_LIMIT_PER_IP:
                logger.warning(
                    "[%s] IP rate limit exceeded: %s (%d requests)",
                    cid, client_ip, ip_count,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "TOO_MANY_REQUESTS",
                        "message": f"Rate limit exceeded (max {RATE_LIMIT_PER_IP}/min per IP)",
                        "correlation_id": cid,
                    },
                    headers={"X-Correlation-ID": cid},
                )

            # Per-user limit (only if authenticated)
            if user_id:
                user_key = f"ratelimit:user:{user_id}"
                user_count = await redis_client.incr(user_key)
                if user_count == 1:
                    await redis_client.expire(user_key, 60)

                if user_count > RATE_LIMIT_PER_USER:
                    logger.warning(
                        "[%s] User rate limit exceeded: %s (%d requests)",
                        cid, user_id, user_count,
                    )
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "error": "TOO_MANY_REQUESTS",
                            "message": f"Rate limit exceeded (max {RATE_LIMIT_PER_USER}/min per user)",
                            "correlation_id": cid,
                        },
                        headers={"X-Correlation-ID": cid},
                    )

        except Exception as exc:
            logger.warning("Rate limit check failed: %s", exc)
            # Fail open — if Redis is down, don't block the request

        response = await call_next(request)
        return response
