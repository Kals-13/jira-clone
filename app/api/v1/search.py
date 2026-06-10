from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.infrastructure.db.models import User
from app.infrastructure.db.repositories.search import SearchRepository

router = APIRouter()

@router.get("/")
async def search_issues(
    project_id: str = Query(..., description="Project ID to search within"),
    q: Optional[str] = Query(None, description="Full-text search across title and description"),
    status_id: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    issue_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    repo = SearchRepository(db)
    issues, next_cursor = await repo.search_issues(
        project_id=project_id,
        search_query=q,
        status_id=status_id,
        assignee_id=assignee_id,
        issue_type=issue_type,
        limit=limit,
        cursor=cursor
    )
    return {
        "results": [
            {
                "id": issue.id,
                "issue_key": issue.issue_key,
                "title": issue.title,
                "type": issue.type.value,
                "status_id": issue.status_id,
                "assignee_id": issue.assignee_id,
                "priority": issue.priority.value,
                "created_at": issue.created_at.isoformat()
            }
            for issue in issues
        ],
        "next_cursor": next_cursor,
        "count": len(issues)
    }