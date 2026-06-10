from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional
import base64
from datetime import datetime

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.infrastructure.db.models import User, ActivityLog

router = APIRouter()

@router.get("/{project_id}/activity")
async def get_activity_feed(
    project_id: str,
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(ActivityLog).where(ActivityLog.project_id == project_id)

    if event_type:
        stmt = stmt.where(ActivityLog.event_type == event_type)

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(
                base64.b64decode(cursor.encode()).decode()
            )
            stmt = stmt.where(ActivityLog.created_at < cursor_dt)
        except Exception:
            pass

    stmt = stmt.order_by(desc(ActivityLog.created_at)).limit(limit + 1)
    result = await db.execute(stmt)
    logs = list(result.scalars().all())

    next_cursor = None
    if len(logs) > limit:
        logs = logs[:limit]
        next_cursor = base64.b64encode(
            logs[-1].created_at.isoformat().encode()
        ).decode()

    return {
        "project_id": project_id,
        "logs": [
            {
                "id": log.id,
                "issue_id": log.issue_id,
                "actor_id": log.actor_id,
                "event_type": log.event_type,
                "payload": log.payload,
                "timestamp": log.created_at.isoformat()
            }
            for log in logs
        ],
        "next_cursor": next_cursor
    }