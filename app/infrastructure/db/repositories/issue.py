from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.infrastructure.db.models import Issue, WorkflowTransition

class IssueRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, issue_id: str) -> Optional[Issue]:
        result = await self.db.execute(select(Issue).where(Issue.id == issue_id))
        return result.scalar_one_or_none()

    async def get_allowed_transitions(self, project_id: str) -> list[tuple[str, str]]:
        """Fetches allowed status transition tuples for a given project."""
        result = await self.db.execute(
            select(WorkflowTransition.from_status_id, WorkflowTransition.to_status_id)
            .where(WorkflowTransition.project_id == project_id)
        )
        return result.all()
    
    async def get_transition_rule(self, project_id: str, from_status_id: str, to_status_id: str):
        result = await self.db.execute(
            select(WorkflowTransition).where(
                WorkflowTransition.project_id == project_id,
                WorkflowTransition.from_status_id == from_status_id,
                WorkflowTransition.to_status_id == to_status_id
            )
        )
        return result.scalar_one_or_none()

    async def count_issues_in_status(self, project_id: str, status_id: str) -> int:
        """Returns the number of issues currently in a given status column."""
        result = await self.db.execute(
            select(func.count()).where(
                Issue.project_id == project_id,
                Issue.status_id == status_id,
            )
        )
        return result.scalar() or 0

    async def update_issue_status_atomic(self, issue_id: str, current_version: int, new_status_id: str, reviewer_id: str = None) -> bool:
        stmt = (
            update(Issue)
            .where(Issue.id == issue_id, Issue.version == current_version)
            .values(
                status_id=new_status_id,
                reviewer_id=reviewer_id,
                version=current_version + 1
            )
        )
        result = await self.db.execute(stmt)
        return result.rowcount > 0