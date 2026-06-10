from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.infrastructure.db.models import Sprint, Issue, WorkflowStatus, SprintStatus

class SprintRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, sprint_id: str) -> Optional[Sprint]:
        result = await self.db.execute(select(Sprint).where(Sprint.id == sprint_id))
        return result.scalar_one_or_none()

    async def create_sprint(self, project_id: str, name: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Sprint:
        sprint = Sprint(project_id=project_id, name=name, start_date=start_date, end_date=end_date, status=SprintStatus.planned)
        self.db.add(sprint)

        await self.db.commit()

        await self.db.refresh(sprint)
        return sprint

    async def get_sprint_metrics(self, sprint_id: str) -> dict:
        """
        Calculates completed vs incomplete stories and points.
        An issue is complete if its status has is_terminal = True.
        """
        # Fetch all issues associated with this sprint along with terminal state of their status
        stmt = (
            select(Issue.id, Issue.story_points, WorkflowStatus.is_terminal)
            .join(WorkflowStatus, Issue.status_id == WorkflowStatus.id)
            .where(Issue.sprint_id == sprint_id)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        completed_points = 0
        completed_count = 0
        incomplete_points = 0
        incomplete_count = 0
        incomplete_ids = []

        for issue_id, points, is_terminal in rows:
            pts = points or 0
            if is_terminal:
                completed_count += 1
                completed_points += pts
            else:
                incomplete_count += 1
                incomplete_points += pts
                incomplete_ids.append(issue_id)

        return {
            "completed_count": completed_count,
            "completed_points": completed_points,
            "incomplete_count": incomplete_count,
            "incomplete_points": incomplete_points,
            "incomplete_ids": incomplete_ids
        }

    async def bulk_carry_over_issues(self, issue_ids: List[str], target_sprint_id: Optional[str]):
        """Bulk updates issues to a new sprint or resets to backlog (None)"""
        if not issue_ids:
            return
        
        stmt = (
            update(Issue)
            .where(Issue.id.in_(issue_ids))
            .values(sprint_id=target_sprint_id, version=Issue.version + 1)
        )
        await self.db.execute(stmt)
        await self.db.flush()