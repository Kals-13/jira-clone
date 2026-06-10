import logging
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.infrastructure.db.models import User, ProjectMember, Role

logger = logging.getLogger("jiralite.rbac")


async def require_project_membership(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectMember:
    """
    Dependency that enforces project membership.
    Returns the ProjectMember record if user is a member, else raises 403.
    """
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        logger.warning(
            "Access denied: user %s attempted to access project %s",
            current_user.id, project_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this project",
        )
    return member


async def require_project_role(
    required_role: Role,
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectMember:
    """
    Dependency that enforces a minimum project role.
    Example: require_project_role(Role.project_lead, project_id)

    Role hierarchy: admin > project_lead > member > viewer
    """
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        logger.warning(
            "Access denied: user %s not a member of project %s",
            current_user.id, project_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this project",
        )

    # Role hierarchy: higher values = more permissions
    role_hierarchy = {
        Role.viewer: 0,
        Role.member: 1,
        Role.project_lead: 2,
        Role.admin: 3,
    }

    if role_hierarchy.get(member.role, 0) < role_hierarchy.get(required_role, 0):
        logger.warning(
            "Access denied: user %s (role=%s) lacks required role %s for project %s",
            current_user.id, member.role, required_role, project_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This operation requires {required_role} role or higher",
        )

    return member
