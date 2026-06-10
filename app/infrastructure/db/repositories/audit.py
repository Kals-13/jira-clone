import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert

from app.infrastructure.db.models import ActivityLog

logger = logging.getLogger("jiralite.audit")


class AuditRepository:
    """
    Logs sensitive operations for compliance and security auditing.
    Unlike regular ActivityLog (issue mutations), these are system-level events.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_role_change(
        self,
        project_id: str,
        actor_id: str,
        target_user_id: str,
        old_role: str,
        new_role: str,
    ) -> None:
        """Log when a user's role is changed in a project."""
        log = ActivityLog(
            issue_id=None,  # System event, not issue-specific
            project_id=project_id,
            actor_id=actor_id,
            event_type="role_changed",
            payload={
                "target_user_id": target_user_id,
                "old_role": old_role,
                "new_role": new_role,
            },
        )
        self.db.add(log)
        await self.db.commit()
        logger.warning(
            "AUDIT: Role change - actor=%s changed user=%s role: %s → %s (project=%s)",
            actor_id, target_user_id, old_role, new_role, project_id,
        )

    async def log_project_deletion(
        self,
        project_id: str,
        actor_id: str,
        project_name: str,
    ) -> None:
        """Log when a project is deleted."""
        log = ActivityLog(
            issue_id=None,
            project_id=project_id,
            actor_id=actor_id,
            event_type="project_deleted",
            payload={"project_name": project_name},
        )
        self.db.add(log)
        await self.db.commit()
        logger.warning(
            "AUDIT: Project deletion - actor=%s deleted project=%s (%s)",
            actor_id, project_id, project_name,
        )

    async def log_access_denied(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        reason: str,
    ) -> None:
        """Log denied access attempts to sensitive resources."""
        logger.warning(
            "AUDIT: Access denied - actor=%s tried to access %s=%s (reason: %s)",
            actor_id, resource_type, resource_id, reason,
        )

    async def log_failed_auth(
        self,
        email: str,
        reason: str,
    ) -> None:
        """Log failed authentication attempts."""
        logger.warning(
            "AUDIT: Failed auth - email=%s (reason: %s)",
            email, reason,
        )
