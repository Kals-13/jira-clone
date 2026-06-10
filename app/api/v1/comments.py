from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.application.collaboration_service import CollaborationService
from app.api.v1.auth import get_current_user
from app.infrastructure.db.models import User, Comment

router = APIRouter()

class CommentCreateRequest(BaseModel):
    body: str
    parent_id: Optional[str] = None

@router.get("/{issue_id}/comments")
async def list_comments(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Comment)
        .where(Comment.issue_id == issue_id, Comment.parent_id == None)
        .order_by(Comment.created_at.asc())
    )
    top_level = result.scalars().all()

    def serialize(c: Comment):
        return {
            "id": c.id,
            "body": c.body,
            "author_id": c.author_id,
            "mentions": c.mentions,
            "created_at": c.created_at.isoformat(),
            "parent_id": c.parent_id,
        }

    return [serialize(c) for c in top_level]

@router.post("/{issue_id}/comments", status_code=201)
async def create_comment(
    issue_id: str,
    payload: CommentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = CollaborationService(db)
    comment = await service.add_comment(
        issue_id=issue_id,
        author_id=current_user.id,
        body=payload.body,
        parent_id=payload.parent_id
    )
    return {
        "comment_id": comment.id,
        "issue_id": issue_id,
        "body": comment.body,
        "author_id": comment.author_id,
        "mentions": comment.mentions,
        "created_at": comment.created_at.isoformat(),
        "parent_id": comment.parent_id,
        "status": "created"
    }

@router.post("/{issue_id}/watch", status_code=200)
async def watch_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = CollaborationService(db)
    await service.add_watcher(issue_id=issue_id, user_id=current_user.id)
    return {"status": "watching"}

@router.get("/{issue_id}/watchers")
async def list_watchers(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.infrastructure.db.models import IssueWatcher
    result = await db.execute(
        select(IssueWatcher).where(IssueWatcher.issue_id == issue_id)
    )
    watchers = result.scalars().all()
    return {"issue_id": issue_id, "watchers": [w.user_id for w in watchers]}