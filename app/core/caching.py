import json
import logging
from app.core.redis import redis_client

logger = logging.getLogger("jiralite.cache")

BOARD_CACHE_TTL = 30  # seconds


class BoardCache:
    """
    Caching layer for board queries.

    Boards are read-heavy and don't need real-time freshness — 30s staleness
    is acceptable. Cache key is project_id; cache is invalidated on any issue
    mutation (create, transition, sprint move).
    """

    @staticmethod
    async def get(project_id: str) -> dict | None:
        """Retrieve cached board, or None if not in cache."""
        try:
            key = f"board:{project_id}"
            cached = await redis_client.get(key)
            if cached:
                logger.info("Board cache HIT for project %s", project_id)
                return json.loads(cached)
            else:
                logger.info("Board cache MISS for project %s (key=%s)", project_id, key)
        except Exception as exc:
            logger.error("Failed to read board cache: %s", exc, exc_info=True)
        return None

    @staticmethod
    async def set(project_id: str, board_data: dict) -> None:
        """Store board in cache for BOARD_CACHE_TTL seconds."""
        try:
            key = f"board:{project_id}"
            result = await redis_client.setex(
                key,
                BOARD_CACHE_TTL,
                json.dumps(board_data),
            )
            logger.info("Board cached for project %s (key=%s, ttl=%ds, result=%s)",
                       project_id, key, BOARD_CACHE_TTL, result)
        except Exception as exc:
            logger.error("Failed to write board cache: %s", exc, exc_info=True)

    @staticmethod
    async def invalidate(project_id: str) -> None:
        """Invalidate board cache for a project."""
        try:
            await redis_client.delete(f"board:{project_id}")
            logger.debug("Board cache invalidated for project %s", project_id)
        except Exception as exc:
            logger.warning("Failed to invalidate board cache: %s", exc)
