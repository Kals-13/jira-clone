from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.application.sprint_service import SprintService
from app.api.v1.auth import get_current_user
from app.infrastructure.db.models import User, Sprint, SprintStatus, Issue

router = APIRouter()

class SprintCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    project_id: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class SprintUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class CompleteSprintRequest(BaseModel):
    target_sprint_id: Optional[str] = None
    selective_issue_ids: Optional[List[str]] = None


@router.post("/", status_code=201)
async def create_sprint(
    payload: SprintCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = SprintService(db)
    start_date = payload.start_date.replace(tzinfo=None) if payload.start_date and payload.start_date.tzinfo else payload.start_date
    end_date = payload.end_date.replace(tzinfo=None) if payload.end_date and payload.end_date.tzinfo else payload.end_date
    sprint = await service.repo.create_sprint(
        project_id=payload.project_id,
        name=payload.name,
        start_date=start_date,
        end_date=end_date
    )
    return {"sprint_id": sprint.id, "name": sprint.name, "status": sprint.status.value}

@router.patch("/{sprint_id}", status_code=200)
async def update_sprint(
    sprint_id: str,
    payload: SprintUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update sprint name or date range. Only allowed while sprint is planned or active."""
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    if sprint.status == SprintStatus.completed:
        raise HTTPException(status_code=400, detail="Completed sprints cannot be modified")

    if payload.name is not None:
        sprint.name = payload.name
    if payload.start_date is not None:
        sprint.start_date = payload.start_date.replace(tzinfo=None) if payload.start_date.tzinfo else payload.start_date
    if payload.end_date is not None:
        sprint.end_date = payload.end_date.replace(tzinfo=None) if payload.end_date.tzinfo else payload.end_date

    await db.commit()
    await db.refresh(sprint)
    return {
        "sprint_id": sprint.id,
        "name": sprint.name,
        "status": sprint.status.value,
        "start_date": sprint.start_date.isoformat() if sprint.start_date else None,
        "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
    }

@router.delete("/{sprint_id}", status_code=200)
async def delete_sprint(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a sprint. Only planned sprints can be deleted; issues are moved to backlog."""
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    if sprint.status != SprintStatus.planned:
        raise HTTPException(
            status_code=400,
            detail=f"Only planned sprints can be deleted. Current status: {sprint.status.value}"
        )

    # Move any assigned issues back to backlog before deleting
    issues_result = await db.execute(select(Issue).where(Issue.sprint_id == sprint_id))
    for issue in issues_result.scalars().all():
        issue.sprint_id = None

    await db.delete(sprint)
    await db.commit()
    return {"status": "deleted", "sprint_id": sprint_id}

@router.post("/{sprint_id}/start", status_code=200)
async def start_sprint(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Starts a sprint. Uses PostgreSQL advisory lock to prevent
    two users from starting the same sprint simultaneously.
    """
    # Advisory lock: prevents race conditions on sprint start
    # pg_try_advisory_xact_lock uses a hash of the sprint_id string
    lock_key = abs(hash(sprint_id)) % (2**31)
    lock_result = await db.execute(text(f"SELECT pg_try_advisory_xact_lock({lock_key})"))
    lock_acquired = lock_result.scalar()

    if not lock_acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another operation is already modifying this sprint. Please retry."
        )

    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    if sprint.status != SprintStatus.planned:
        raise HTTPException(
            status_code=400,
            detail=f"Only planned sprints can be started. Current status: {sprint.status.value}"
        )

    # Check no other active sprint exists for this project
    active_result = await db.execute(
        select(Sprint).where(
            Sprint.project_id == sprint.project_id,
            Sprint.status == SprintStatus.active
        )
    )
    if active_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A sprint is already active for this project.")

    sprint.status = SprintStatus.active
    await db.commit()
    await db.refresh(sprint)

    return {
        "sprint_id": sprint.id,
        "name": sprint.name,
        "status": sprint.status.value,
        "start_date": sprint.start_date.isoformat() if sprint.start_date else None
    }

@router.post("/{sprint_id}/complete", status_code=200)
async def complete_sprint(
    sprint_id: str,
    payload: CompleteSprintRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Advisory lock on complete
    lock_key = abs(hash(sprint_id)) % (2**31)
    await db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))

    service = SprintService(db)
    summary = await service.complete_active_sprint(
        sprint_id=sprint_id,
        target_sprint_id=payload.target_sprint_id,
        selective_issue_ids=payload.selective_issue_ids,
        actor_id=current_user.id
    )
    return summary

@router.post("/{sprint_id}/issues/{issue_id}", status_code=200)
async def move_issue_to_sprint(
    sprint_id: str,
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Move an issue from backlog to sprint."""
    issue_result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = issue_result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    sprint_result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = sprint_result.scalar_one_or_none()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")

    issue.sprint_id = sprint_id
    issue.version += 1
    await db.commit()
    return {"issue_id": issue_id, "sprint_id": sprint_id, "status": "moved"}

@router.delete("/{sprint_id}/issues/{issue_id}", status_code=200)
async def remove_issue_from_sprint(
    sprint_id: str,
    issue_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Move an issue back to backlog."""
    issue_result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = issue_result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue.sprint_id = None
    issue.version += 1
    await db.commit()
    return {"issue_id": issue_id, "status": "moved to backlog"}
