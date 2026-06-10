import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request

from app.core.redis import redis_client

logger = logging.getLogger("jiralite.idempotency")

TTL_SECONDS = 86_400  # 24 hours — long enough for any reasonable client retry window
MUTATION_METHODS = {"POST", "PATCH", "PUT"}


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Transparent idempotency layer for mutation endpoints.

    How it works:
      1. Client includes  Idempotency-Key: <uuid>  on any POST/PATCH/PUT.
      2. On first call: request is processed normally; the response (status + body)
         is stored in Redis under that key for 24 hours.
      3. On any retry with the same key: the cached response is returned immediately,
         no handler is invoked, no side effects re-run.
      4. Response carries  Idempotency-Replayed: true  so clients know it was a replay.

    If Redis is unavailable the request is processed normally (fail-open — idempotency
    degrades gracefully, it never blocks a request).
    """

    async def dispatch(self, request: Request, call_next):
        if request.method not in MUTATION_METHODS:
            return await call_next(request)

        key = request.headers.get("Idempotency-Key")
        if not key:
            return await call_next(request)

        cache_key = f"idempotency:{key}"

        try:
            cached = await redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                logger.info("Idempotency cache hit for key %s", key)
                return Response(
                    content=json.dumps(data["body"]),
                    status_code=data["status_code"],
                    media_type="application/json",
                    headers={
                        "Idempotency-Replayed": "true",
                        "X-Correlation-ID": getattr(request.state, "correlation_id", ""),
                    },
                )
        except Exception as exc:
            logger.warning("Redis unavailable during idempotency check: %s", exc)

        response = await call_next(request)

        # Buffer the streaming body so we can both store it and return it
        body_chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
        body_bytes = b"".join(body_chunks)

        # Cache only successful responses
        if 200 <= response.status_code < 300:
            try:
                body_json = json.loads(body_bytes)
                await redis_client.setex(
                    cache_key,
                    TTL_SECONDS,
                    json.dumps({"status_code": response.status_code, "body": body_json}),
                )
                logger.info("Idempotency response cached for key %s", key)
            except Exception as exc:
                logger.warning("Failed to cache idempotency response: %s", exc)

        # Return the response with the original body re-streamed
        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
