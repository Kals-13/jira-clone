import re
import random
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repositories.issue import IssueRepository
from app.domain.workflow import WorkflowEngine
from app.domain.errors import NotFoundError, ConflictError, WorkflowError
from app.domain.events import IssueCreated, IssueUpdated, StatusChanged
from app.events.dispatcher import EventDispatcher, dispatcher as default_dispatcher
from app.infrastructure.db.models import Issue, ActivityLog, Project, IssueType, WorkflowStatus
from app.core.caching import BoardCache

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class IssueService:
    def __init__(self, db: AsyncSession, dispatcher: EventDispatcher = None):
        self.db = db
        self.repo = IssueRepository(db)
        self.dispatcher = dispatcher or default_dispatcher

    async def create_issue(self, payload: dict, reporter_id: str) -> Issue:
        # Resolve status name → UUID if a human-readable name was passed
        if not UUID_PATTERN.match(payload["status_id"]):
            result = await self.db.execute(
                select(WorkflowStatus).where(
                    WorkflowStatus.project_id == payload["project_id"],
                    WorkflowStatus.name == payload["status_id"],
                )
            )
            resolved = result.scalar_one_or_none()
            if not resolved:
                raise WorkflowError(
                    f"Status column '{payload['status_id']}' does not exist for this project."
                )
            payload["status_id"] = resolved.id

        project_result = await self.db.execute(
            select(Project).where(Project.id == payload["project_id"])
        )
        project = project_result.scalar_one_or_none()
        project_key = project.key if project else "TASK"
        issue_key = f"{project_key}-{random.randint(100, 999)}"

        issue = Issue(
            title=payload["title"],
            description=payload.get("description"),
            type=IssueType(payload["issue_type"].lower()),
            project_id=payload["project_id"],
            status_id=payload["status_id"],
            parent_id=payload.get("parent_id"),
            story_points=payload.get("story_points"),
            custom_fields=payload.get("custom_fields") or {},
            reporter_id=reporter_id,
            issue_key=issue_key,
            version=1,
        )
        self.db.add(issue)
        await self.db.commit()
        await self.db.refresh(issue)

        self.db.add(ActivityLog(
            issue_id=issue.id,
            project_id=issue.project_id,
            actor_id=reporter_id,
            event_type="issue_created",
            payload={"type": issue.type, "parent_id": issue.parent_id},
        ))
        await self.db.commit()

        await self.dispatcher.dispatch(IssueCreated(
            issue_id=issue.id,
            project_id=issue.project_id,
            issue_type=issue.type,
            status_id=issue.status_id,
            reporter_id=reporter_id,
        ))

        await BoardCache.invalidate(issue.project_id)
        return issue

    async def update_issue(self, issue_id: str, payload: dict, actor_id: str) -> Issue:
        issue = await self.repo.get_by_id(issue_id)
        if not issue:
            raise NotFoundError("Issue not found")

        incoming_version = payload.pop("version")
        if issue.version != incoming_version:
            raise ConflictError(
                f"Version conflict. Expected {issue.version}, got {incoming_version}."
            )

        updatable = [
            "title", "description", "assignee_id", "reviewer_id",
            "story_points", "priority", "labels", "custom_fields", "sprint_id",
        ]
        changes = {}
        for field in updatable:
            if field in payload and payload[field] is not None:
                old_val = getattr(issue, field)
                new_val = payload[field]
                if old_val != new_val:
                    changes[field] = {"from": str(old_val), "to": str(new_val)}
                    setattr(issue, field, new_val)

        if not changes:
            return issue

        issue.version += 1
        self.db.add(ActivityLog(
            issue_id=issue.id,
            project_id=issue.project_id,
            actor_id=actor_id,
            event_type="issue_updated",
            payload={"changes": changes},
        ))
        await self.db.commit()
        await self.db.refresh(issue)

        await self.dispatcher.dispatch(IssueUpdated(
            issue_id=issue.id,
            issue_key=issue.issue_key,
            project_id=issue.project_id,
            actor_id=actor_id,
            changes=changes,
            version=issue.version,
        ))

        await BoardCache.invalidate(issue.project_id)
        return issue

    async def transition_issue(self, issue_id: str, target_status_id: str, actor_id: str) -> Issue:
        issue = await self.repo.get_by_id(issue_id)
        if not issue:
            raise NotFoundError("Issue not found")

        # Resolve status name → UUID if needed
        if not UUID_PATTERN.match(target_status_id):
            result = await self.db.execute(
                select(WorkflowStatus).where(
                    WorkflowStatus.project_id == issue.project_id,
                    func.lower(WorkflowStatus.name) == target_status_id.lower(),
                )
            )
            resolved = result.scalar_one_or_none()
            if not resolved:
                raise WorkflowError(f"Status '{target_status_id}' not found for this project")
            target_status_id = resolved.id

        allowed = await self.repo.get_allowed_transitions(issue.project_id)
        is_valid, allowed_targets = WorkflowEngine.validate_transition(
            current_status_id=issue.status_id,
            target_status_id=target_status_id,
            allowed_transitions=allowed,
        )
        if not is_valid:
            names_result = await self.db.execute(
                select(WorkflowStatus.id, WorkflowStatus.name)
                .where(WorkflowStatus.id.in_(allowed_targets))
            )
            raise WorkflowError(
                f"Transition not allowed. Permitted targets: "
                + str([{"id": r.id, "name": r.name} for r in names_result.all()])
            )

        # ── WIP limit check ───────────────────────────────────────────────────
        # Acquire a transaction-scoped advisory lock keyed to the target status.
        # This serializes concurrent transitions into the same column so two
        # requests can't both read "one slot remaining" and both proceed past
        # the limit — one will wait for the other to commit first.
        target_status_result = await self.db.execute(
            select(WorkflowStatus).where(WorkflowStatus.id == target_status_id)
        )
        target_status = target_status_result.scalar_one_or_none()

        if target_status and target_status.wip_limit is not None:
            lock_key = abs(hash(f"wip:{target_status_id}")) % (2 ** 31)
            await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))

            current_count = await self.repo.count_issues_in_status(
                project_id=issue.project_id,
                status_id=target_status_id,
            )
            if current_count >= target_status.wip_limit:
                raise ConflictError(
                    f"WIP limit of {target_status.wip_limit} reached for "
                    f"'{target_status.name}' ({current_count} issues in column). "
                    f"Move or complete an issue before adding another."
                )

        old_status_id = issue.status_id
        rule = await self.repo.get_transition_rule(
            project_id=issue.project_id,
            from_status_id=old_status_id,
            to_status_id=target_status_id,
        )
        reviewer_id = issue.reviewer_id
        auto_assigned = False
        if rule and rule.auto_assign_reviewer:
            reviewer_id = actor_id
            auto_assigned = True

        success = await self.repo.update_issue_status_atomic(
            issue_id=issue.id,
            current_version=issue.version,
            new_status_id=target_status_id,
            reviewer_id=reviewer_id,
        )
        if not success:
            raise ConflictError("Version conflict detected during status transition. Please refresh and retry.")

        self.db.add(ActivityLog(
            issue_id=issue.id,
            project_id=issue.project_id,
            actor_id=actor_id,
            event_type="status_changed",
            payload={
                "from": old_status_id,
                "to": target_status_id,
                "auto_assigned": auto_assigned,
                "reviewer_id": reviewer_id,
            },
        ))
        await self.db.commit()
        await self.db.refresh(issue)

        await self.dispatcher.dispatch(StatusChanged(
            issue_id=issue.id,
            issue_key=issue.issue_key,
            project_id=issue.project_id,
            actor_id=actor_id,
            from_status_id=old_status_id,
            to_status_id=target_status_id,
            reviewer_id=reviewer_id,
            auto_assigned=auto_assigned,
        ))

        await BoardCache.invalidate(issue.project_id)
        return issue
