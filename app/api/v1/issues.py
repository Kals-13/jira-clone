from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import uuid

from app.core.database import get_db
from app.application.issue_service import IssueService
from app.api.v1.auth import get_current_user
from app.infrastructure.db.models import User, Issue, WorkflowStatus, ActivityLog

router = APIRouter()


class IssueUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    reviewer_id: Optional[str] = None
    story_points: Optional[int] = None
    priority: Optional[str] = None
    labels: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    sprint_id: Optional[str] = None
    version: int 

class TransitionRequest(BaseModel):
    target_status_id: str


@router.get("/{issue_id}")
async def get_issue(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return {
        "id": issue.id,
        "issue_key": issue.issue_key,
        "title": issue.title,
        "description": issue.description,
        "type": issue.type.value,
        "status_id": issue.status_id,
        "priority": issue.priority.value,
        "story_points": issue.story_points,
        "assignee_id": issue.assignee_id,
        "reviewer_id": issue.reviewer_id,
        "reporter_id": issue.reporter_id,
        "parent_id": issue.parent_id,
        "sprint_id": issue.sprint_id,
        "labels": issue.labels,
        "custom_fields": issue.custom_fields,
        "version": issue.version,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
    }

@router.patch("/{issue_id}")
async def update_issue(
    issue_id: str,
    payload: IssueUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = IssueService(db)
    updated = await service.update_issue(
        issue_id=issue_id,
        payload=payload.dict(exclude_unset=True),
        actor_id=current_user.id
    )
    return {
        "issue_id": updated.id,
        "version": updated.version,
        "updated_at": updated.updated_at.isoformat()
    }

@router.post("/{issue_id}/transitions")
async def transition_issue(
    issue_id: str,
    payload: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = IssueService(db)
    updated_issue = await service.transition_issue(
        issue_id=issue_id,
        target_status_id=payload.target_status_id,
        actor_id=current_user.id
    )
    return {
        "status": "success",
        "issue_id": updated_issue.id,
        "current_status": updated_issue.status_id,
        "version": updated_issue.version
    }