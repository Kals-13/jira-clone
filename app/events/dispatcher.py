import asyncio
import logging
from app.domain.events import (
    DomainEvent, IssueCreated, IssueUpdated, StatusChanged, CommentAdded, SprintCompleted
)
from app.api.websocket import manager
from app.events.bus import notification_bus
from app.events.handlers import dispatch_email_notification
from app.core.metrics import MetricsCollector

logger = logging.getLogger("jiralite.dispatcher")


class EventDispatcher:
    """
    Routes typed domain events to their side-effect handlers:
    WebSocket broadcasts and out-of-band notifications.

    Services emit events; this class decides who gets notified and how.
    Nothing in the domain layer imports from here.
    """

    async def dispatch(self, event: DomainEvent) -> None:
        logger.info(
            "dispatching event %s for project %s",
            type(event).__name__,
            getattr(event, "project_id", "unknown"),
        )
        if isinstance(event, IssueCreated):
            await self._on_issue_created(event)
        elif isinstance(event, IssueUpdated):
            await self._on_issue_updated(event)
        elif isinstance(event, StatusChanged):
            await self._on_status_changed(event)
        elif isinstance(event, CommentAdded):
            await self._on_comment_added(event)
        elif isinstance(event, SprintCompleted):
            await self._on_sprint_completed(event)
        else:
            logger.warning("No handler registered for event type: %s", type(event).__name__)

    async def _on_issue_created(self, event: IssueCreated) -> None:
        MetricsCollector.record_issue_created()
        await manager.broadcast_to_project(event.project_id, {
            "event_type": "issue_created",
            "event_id": event.event_id,
            "issue_id": event.issue_id,
            "issue_type": event.issue_type,
            "status_id": event.status_id,
        })

    async def _on_issue_updated(self, event: IssueUpdated) -> None:
        await manager.broadcast_to_project(event.project_id, {
            "event_type": "issue_updated",
            "event_id": event.event_id,
            "issue_id": event.issue_id,
            "issue_key": event.issue_key,
            "changes": event.changes,
            "version": event.version,
        })

    async def _on_status_changed(self, event: StatusChanged) -> None:
        MetricsCollector.record_issue_transitioned()
        await manager.broadcast_to_project(event.project_id, {
            "event_type": "issue_moved",
            "event_id": event.event_id,
            "issue_id": event.issue_id,
            "issue_key": event.issue_key,
            "from_status_id": event.from_status_id,
            "to_status_id": event.to_status_id,
            "reviewer_id": event.reviewer_id,
        })
        if event.reviewer_id and event.auto_assigned:
            asyncio.create_task(notification_bus.call_external_service(
                dispatch_email_notification,
                {
                    "type": "reviewer_assigned",
                    "target_user_id": event.reviewer_id,
                    "issue_id": event.issue_id,
                    "title": f"You were auto-assigned as reviewer on {event.issue_key}",
                }
            ))

    async def _on_comment_added(self, event: CommentAdded) -> None:
        MetricsCollector.record_comment_added()
        await manager.broadcast_to_project(event.project_id, {
            "event_type": "comment_added",
            "event_id": event.event_id,
            "issue_id": event.issue_id,
            "comment_id": event.comment_id,
            "author_id": event.author_id,
        })
        # Mention alerts
        for user_id in event.mentioned_user_ids:
            asyncio.create_task(notification_bus.call_external_service(
                dispatch_email_notification,
                {
                    "type": "mention",
                    "target_user_id": user_id,
                    "issue_id": event.issue_id,
                    "title": f"You were mentioned in a comment by {event.author_id}",
                }
            ))
        # Watcher alerts (skip the author — they don't need to notify themselves)
        for watcher_id in event.watcher_ids:
            if watcher_id == event.author_id:
                continue
            asyncio.create_task(notification_bus.call_external_service(
                dispatch_email_notification,
                {
                    "type": "watcher_update",
                    "target_user_id": watcher_id,
                    "issue_id": event.issue_id,
                    "title": f"New comment on an issue you are watching",
                }
            ))

    async def _on_sprint_completed(self, event: SprintCompleted) -> None:
        MetricsCollector.record_sprint_completed()
        await manager.broadcast_to_project(event.project_id, {
            "event_type": "sprint_updated",
            "event_id": event.event_id,
            "sprint_id": event.sprint_id,
            "velocity": event.velocity,
            "moved_issues_count": event.moved_issues_count,
            "target_sprint_id": event.target_sprint_id,
        })

dispatcher = EventDispatcher()
