from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.db.models import WorkflowStatus, Sprint, SprintStatus, Issue
from app.domain.errors import NotFoundError
from app.core.caching import BoardCache


class BoardReadModel:
    """
    CQRS read side for the board view.

    Kept separate from the write models (IssueService, SprintService) so that
    read-path optimizations (caching, denormalization) never bleed into the
    command side.  All queries here are read-only and load everything in the
    minimum number of round-trips.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_board(self, project_id: str) -> dict:
        # Try cache first (30s TTL)
        cached = await BoardCache.get(project_id)
        if cached:
            return cached

        # Cache miss — fetch from DB (4 queries total, no N+1)
        # 1. Status columns — one query, ordered by position
        status_result = await self.db.execute(
            select(WorkflowStatus)
            .where(WorkflowStatus.project_id == project_id)
            .order_by(WorkflowStatus.position)
        )
        statuses = status_result.scalars().all()
        if not statuses:
            raise NotFoundError("Project not found or has no board columns")

        # 2. Active sprint — one query
        sprint_result = await self.db.execute(
            select(Sprint).where(
                Sprint.project_id == project_id,
                Sprint.status == SprintStatus.active,
            )
        )
        active_sprint = sprint_result.scalar_one_or_none()

        # 3. All issues for the project — single query, no N+1
        issues_result = await self.db.execute(
            select(Issue).where(Issue.project_id == project_id)
        )
        all_issues = issues_result.scalars().all()

        # 4. Group by status; sprint issues on board, rest to backlog
        issues_by_status: dict[str, list] = {s.id: [] for s in statuses}
        backlog_count = 0

        for issue in all_issues:
            if issue.status_id not in issues_by_status:
                continue
            on_board = (
                active_sprint is None
                or issue.sprint_id == active_sprint.id
            )
            if on_board:
                issues_by_status[issue.status_id].append({
                    "id": issue.id,
                    "issue_key": issue.issue_key,
                    "title": issue.title,
                    "type": issue.type.value,
                    "priority": issue.priority.value,
                    "story_points": issue.story_points,
                    "assignee_id": issue.assignee_id,
                    "parent_id": issue.parent_id,
                    "version": issue.version,
                })
            else:
                backlog_count += 1

        board = {
            "project_id": project_id,
            "active_sprint": {
                "id": active_sprint.id,
                "name": active_sprint.name,
                "end_date": active_sprint.end_date.isoformat() if active_sprint.end_date else None,
            } if active_sprint else None,
            "columns": [
                {
                    "status_id": s.id,
                    "name": s.name,
                    "position": s.position,
                    "is_terminal": s.is_terminal,
                    "issues": issues_by_status[s.id],
                    "issue_count": len(issues_by_status[s.id]),
                }
                for s in statuses
            ],
            "backlog_count": backlog_count,
        }

        # Store in cache for 30s
        await BoardCache.set(project_id, board)
        return board
