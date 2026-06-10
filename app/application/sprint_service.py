from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.repositories.sprint import SprintRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.events import SprintCompleted
from app.events.dispatcher import EventDispatcher, dispatcher as default_dispatcher
from app.infrastructure.db.models import SprintStatus, ActivityLog


class SprintService:
    def __init__(self, db: AsyncSession, dispatcher: EventDispatcher = None):
        self.db = db
        self.repo = SprintRepository(db)
        self.dispatcher = dispatcher or default_dispatcher

    async def complete_active_sprint(
        self,
        sprint_id: str,
        target_sprint_id: Optional[str],
        selective_issue_ids: Optional[list[str]],
        actor_id: str,
    ) -> dict:
        sprint = await self.repo.get_by_id(sprint_id)
        if not sprint:
            raise NotFoundError("Sprint not found")
        if sprint.status != SprintStatus.active:
            raise ValidationError(
                f"Only active sprints can be completed. Current status: {sprint.status}"
            )

        metrics = await self.repo.get_sprint_metrics(sprint_id)
        all_incomplete = metrics["incomplete_ids"]
        items_to_move = selective_issue_ids if selective_issue_ids is not None else all_incomplete
        items_to_move = [i for i in items_to_move if i in all_incomplete]

        if items_to_move:
            await self.repo.bulk_carry_over_issues(items_to_move, target_sprint_id)
            for issue_id in items_to_move:
                self.db.add(ActivityLog(
                    issue_id=issue_id,
                    project_id=sprint.project_id,
                    actor_id=actor_id,
                    event_type="sprint_carry_over",
                    payload={"from_sprint_id": sprint_id, "to_sprint_id": target_sprint_id},
                ))

        sprint.status = SprintStatus.completed
        sprint.velocity = metrics["completed_points"]
        await self.db.commit()

        await self.dispatcher.dispatch(SprintCompleted(
            sprint_id=sprint_id,
            project_id=sprint.project_id,
            actor_id=actor_id,
            velocity=sprint.velocity,
            moved_issues_count=len(items_to_move),
            target_sprint_id=target_sprint_id,
        ))

        return {
            "sprint_id": sprint_id,
            "status": "completed",
            "velocity_recorded": sprint.velocity,
            "completed_stories": metrics["completed_count"],
            "carried_over_stories_count": len(items_to_move),
            "destination": f"sprint_id:{target_sprint_id}" if target_sprint_id else "backlog",
        }
