from typing import Optional
import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    String, Column, Text, Integer, ForeignKey, DateTime, Enum as SAEnum,
    JSON, Boolean, Index, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

def gen_uuid():
    return str(uuid.uuid4())

# ── Enums ────────────────────────────────────────────────────────────────────

class IssueType(str, enum.Enum):
    epic = "epic"
    story = "story"
    task = "task"
    bug = "bug"
    subtask = "subtask"

class IssuePriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class SprintStatus(str, enum.Enum):
    planned = "planned"
    active = "active"
    completed = "completed"

class Role(str, enum.Enum):
    admin = "admin"
    project_lead = "project_lead"
    member = "member"
    viewer = "viewer"

class CustomFieldType(str, enum.Enum):
    text = "text"
    number = "number"
    dropdown = "dropdown"
    date = "date"

# ── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    memberships: Mapped[list["ProjectMember"]] = relationship(back_populates="user")
    assigned_issues: Mapped[list["Issue"]] = relationship(
        back_populates="assignee", foreign_keys="Issue.assignee_id"
    )

# ── Projects ─────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    key: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # e.g. "PROJ"
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    members: Mapped[list["ProjectMember"]] = relationship(back_populates="project")
    issues: Mapped[list["Issue"]] = relationship(back_populates="project")
    sprints: Mapped[list["Sprint"]] = relationship(back_populates="project")
    statuses: Mapped[list["WorkflowStatus"]] = relationship(back_populates="project")
    custom_field_schemas: Mapped[list["ProjectCustomField"]] = relationship(back_populates="project")

class ProjectCustomField(Base):
    """Typed custom field schema definition per project (text, number, dropdown, date)."""
    __tablename__ = "project_custom_fields"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    field_type: Mapped[CustomFieldType] = mapped_column(SAEnum(CustomFieldType), nullable=False)
    options: Mapped[list] = mapped_column(JSON, default=list)  # choices for dropdown fields
    required: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped["Project"] = relationship(back_populates="custom_field_schemas")

    __table_args__ = (UniqueConstraint("project_id", "name"),)


class ProjectMember(Base):
    __tablename__ = "project_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[Role] = mapped_column(SAEnum(Role), default=Role.member)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="memberships")

    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

# ── Workflow ──────────────────────────────────────────────────────────────────

class WorkflowStatus(Base):
    """Configurable status columns per project e.g. To Do, In Progress, Done"""
    __tablename__ = "workflow_statuses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)  # column order on board
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)  # e.g. Done
    wip_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = unlimited

    project: Mapped["Project"] = relationship(back_populates="statuses")
    allowed_transitions: Mapped[list["WorkflowTransition"]] = relationship(
        back_populates="from_status", foreign_keys="WorkflowTransition.from_status_id"
    )

class WorkflowTransition(Base):
    """Allowed from_status -> to_status transitions"""
    __tablename__ = "workflow_transitions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    from_status_id: Mapped[str] = mapped_column(ForeignKey("workflow_statuses.id"), nullable=False)
    to_status_id: Mapped[str] = mapped_column(ForeignKey("workflow_statuses.id"), nullable=False)
    auto_assign_reviewer: Mapped[bool] = mapped_column(Boolean, default=False)

    from_status: Mapped["WorkflowStatus"] = relationship(
        back_populates="allowed_transitions", foreign_keys=[from_status_id]
    )

# ── Sprints ───────────────────────────────────────────────────────────────────

class Sprint(Base):
    __tablename__ = "sprints"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[SprintStatus] = mapped_column(SAEnum(SprintStatus), default=SprintStatus.planned)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    velocity: Mapped[int] = mapped_column(Integer, default=0)  # story points completed

    project: Mapped["Project"] = relationship(back_populates="sprints")
    issues: Mapped[list["Issue"]] = relationship(back_populates="sprint")

# ── Issues ────────────────────────────────────────────────────────────────────

class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    issue_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # PROJ-123
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    sprint_id: Mapped[str] = mapped_column(ForeignKey("sprints.id"), nullable=True)
    parent_id: Mapped[str] = mapped_column(ForeignKey("issues.id"), nullable=True)
    assignee_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status_id: Mapped[str] = mapped_column(ForeignKey("workflow_statuses.id"), nullable=False)
    reviewer_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)

    type: Mapped[IssueType] = mapped_column(SAEnum(IssueType), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    priority: Mapped[IssuePriority] = mapped_column(SAEnum(IssuePriority), default=IssuePriority.medium)
    story_points: Mapped[int] = mapped_column(Integer, nullable=True)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)

    # Optimistic locking
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="issues")
    sprint: Mapped["Sprint"] = relationship(back_populates="issues")
    assignee: Mapped["User"] = relationship(back_populates="assigned_issues", foreign_keys=[assignee_id])
    children: Mapped[list["Issue"]] = relationship("Issue", foreign_keys=[parent_id])
    comments: Mapped[list["Comment"]] = relationship(back_populates="issue")
    activity_logs: Mapped[list["ActivityLog"]] = relationship(back_populates="issue")
    watchers: Mapped[list["IssueWatcher"]] = relationship(back_populates="issue")

    __table_args__ = (
        Index("ix_issues_project_id", "project_id"),
        Index("ix_issues_sprint_id", "sprint_id"),
        Index("ix_issues_assignee_id", "assignee_id"),
        Index("ix_issues_status_id", "status_id"),
    )

# ── Comments ──────────────────────────────────────────────────────────────────

class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id"), nullable=False)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    parent_id: Mapped[str] = mapped_column(ForeignKey("comments.id"), nullable=True)  # threading
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[list] = mapped_column(JSON, default=list)  # list of user_ids
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    issue: Mapped["Issue"] = relationship(back_populates="comments")
    replies: Mapped[list["Comment"]] = relationship("Comment", foreign_keys=[parent_id])

# ── Activity Log ──────────────────────────────────────────────────────────────

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "status_changed"
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # before/after values
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    issue: Mapped["Issue"] = relationship(back_populates="activity_logs")

    __table_args__ = (
        Index("ix_activity_project_created", "project_id", "created_at"),
    )

# ── Watchers ──────────────────────────────────────────────────────────────────

class IssueWatcher(Base):
    __tablename__ = "issue_watchers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    issue: Mapped["Issue"] = relationship(back_populates="watchers")

    __table_args__ = (UniqueConstraint("issue_id", "user_id"),)