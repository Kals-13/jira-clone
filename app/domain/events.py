from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class DomainEvent:
    """Base class for all domain events. Every mutation produces one."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class IssueCreated(DomainEvent):
    issue_id: str = ""
    project_id: str = ""
    issue_type: str = ""
    status_id: str = ""
    reporter_id: str = ""


@dataclass
class IssueUpdated(DomainEvent):
    issue_id: str = ""
    issue_key: str = ""
    project_id: str = ""
    actor_id: str = ""
    changes: dict = field(default_factory=dict)
    version: int = 0


@dataclass
class StatusChanged(DomainEvent):
    issue_id: str = ""
    issue_key: str = ""
    project_id: str = ""
    actor_id: str = ""
    from_status_id: str = ""
    to_status_id: str = ""
    reviewer_id: Optional[str] = None
    auto_assigned: bool = False


@dataclass
class CommentAdded(DomainEvent):
    comment_id: str = ""
    issue_id: str = ""
    project_id: str = ""
    author_id: str = ""
    mentioned_user_ids: list = field(default_factory=list)
    watcher_ids: list = field(default_factory=list)


@dataclass
class SprintCompleted(DomainEvent):
    sprint_id: str = ""
    project_id: str = ""
    actor_id: str = ""
    velocity: int = 0
    moved_issues_count: int = 0
    target_sprint_id: Optional[str] = None
