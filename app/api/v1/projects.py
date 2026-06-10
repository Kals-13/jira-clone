from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Any

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.rbac import require_project_membership, require_project_role
from app.infrastructure.db.models import (
    User, Project, Sprint, WorkflowStatus,
    ProjectMember, ProjectCustomField, CustomFieldType, Role
)
from app.infrastructure.db.repositories.project import ProjectRepository
from app.infrastructure.db.repositories.audit import AuditRepository
from app.application.issue_service import IssueService
from app.application.read_models import BoardReadModel
import re

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE
)

router = APIRouter()

class ProjectCreateRequest(BaseModel):
    name: str
    key: str
    description: Optional[str] = None

class CustomFieldCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    field_type: CustomFieldType
    options: Optional[List[str]] = []
    required: bool = False

class ProjectScopedIssueRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    issue_type: str
    status_id: str
    parent_id: Optional[str] = None
    assignee_id: Optional[str] = None
    story_points: Optional[int] = None
    priority: Optional[str] = "medium"
    labels: Optional[List[str]] = []
    custom_fields: Optional[Dict[str, Any]] = {}


@router.post("/", status_code=201)
async def create_project(
    payload: ProjectCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    repo = ProjectRepository(db)
    project = await repo.create_project_with_defaults(
        name=payload.name,
        key=payload.key,
        description=payload.description,
        creator_id=current_user.id
    )
    return {
        "project_id": project.id,
        "project_key": project.key,
        "name": project.name
    }

@router.get("/")
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Row-level security
    result = await db.execute(
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return [
        {"id": p.id, "key": p.key, "name": p.name, "created_at": p.created_at.isoformat()}
        for p in projects
    ]

@router.get("/{project_id}")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"id": project.id, "key": project.key, "name": project.name, "description": project.description}

@router.get("/{project_id}/board")
async def get_board(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get board for a project (requires membership)."""
    await require_project_membership(project_id, db, current_user)
    return await BoardReadModel(db).get_board(project_id)

@router.post("/{project_id}/issues", status_code=201)
async def create_issue_for_project(
    project_id: str,
    payload: ProjectScopedIssueRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an issue (requires project membership)."""
    await require_project_membership(project_id, db, current_user)
    payload_dict = payload.dict()
    payload_dict["project_id"] = project_id
    service = IssueService(db)
    issue = await service.create_issue(payload=payload_dict, reporter_id=current_user.id)
    return {
        "issue_id": issue.id,
        "issue_key": issue.issue_key,
        "status_id": issue.status_id,
        "version": issue.version
    }

@router.delete("/{project_id}", status_code=200)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a project (requires admin or project_lead role)."""
    member = await require_project_role(Role.project_lead, project_id, db, current_user)

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Audit log the deletion
    audit = AuditRepository(db)
    await audit.log_project_deletion(project_id, current_user.id, project.name)

    # Delete all related data (cascade is handled by FK constraints)
    await db.delete(project)
    await db.commit()

    return {"status": "deleted", "project_id": project_id, "project_name": project.name}

@router.patch("/{project_id}/statuses/{status_id}", status_code=200)
async def update_status_config(
    project_id: str,
    status_id: str,
    wip_limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set or clear the WIP limit on a status column.
    Accepts either UUID or status name (e.g., "In Progress", "To Do").
    Pass wip_limit=null to remove the limit.
    """
    # Resolve status name → UUID if needed
    if not UUID_PATTERN.match(status_id):
        name_result = await db.execute(
            select(WorkflowStatus).where(
                WorkflowStatus.project_id == project_id,
                WorkflowStatus.name == status_id,
            )
        )
        resolved = name_result.scalar_one_or_none()
        if not resolved:
            raise HTTPException(
                status_code=404,
                detail=f"Status '{status_id}' not found in this project"
            )
        status_id = resolved.id

    result = await db.execute(
        select(WorkflowStatus).where(
            WorkflowStatus.id == status_id,
            WorkflowStatus.project_id == project_id
        )
    )
    status = result.scalar_one_or_none()
    if not status:
        raise HTTPException(status_code=404, detail="Status not found")

    status.wip_limit = wip_limit
    await db.commit()
    return {
        "status_id": status.id,
        "name": status.name,
        "wip_limit": status.wip_limit
    }

@router.post("/{project_id}/custom-fields", status_code=201)
async def create_custom_field(
    project_id: str,
    payload: CustomFieldCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Define a typed custom field schema for a project."""
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.field_type == CustomFieldType.dropdown and not payload.options:
        raise HTTPException(status_code=400, detail="Dropdown fields require at least one option")

    field = ProjectCustomField(
        project_id=project_id,
        name=payload.name,
        field_type=payload.field_type,
        options=payload.options or [],
        required=payload.required
    )
    db.add(field)
    try:
        await db.commit()
        await db.refresh(field)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A custom field with that name already exists on this project")

    return {
        "id": field.id,
        "name": field.name,
        "field_type": field.field_type.value,
        "options": field.options,
        "required": field.required
    }

@router.get("/{project_id}/custom-fields")
async def list_custom_fields(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Return the typed custom field schema for a project."""
    result = await db.execute(
        select(ProjectCustomField)
        .where(ProjectCustomField.project_id == project_id)
        .order_by(ProjectCustomField.name)
    )
    fields = result.scalars().all()
    return [
        {
            "id": f.id,
            "name": f.name,
            "field_type": f.field_type.value,
            "options": f.options,
            "required": f.required
        }
        for f in fields
    ]

@router.delete("/{project_id}/custom-fields/{field_id}", status_code=200)
async def delete_custom_field(
    project_id: str,
    field_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ProjectCustomField).where(
            ProjectCustomField.id == field_id,
            ProjectCustomField.project_id == project_id
        )
    )
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Custom field not found")
    await db.delete(field)
    await db.commit()
    return {"status": "deleted", "field_id": field_id}

@router.get("/{project_id}/sprints")
async def list_sprints(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Sprint).where(Sprint.project_id == project_id).order_by(Sprint.start_date.desc())
    )
    sprints = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "status": s.status.value,
            "start_date": s.start_date.isoformat() if s.start_date else None,
            "end_date": s.end_date.isoformat() if s.end_date else None,
            "velocity": s.velocity
        }
        for s in sprints
    ]