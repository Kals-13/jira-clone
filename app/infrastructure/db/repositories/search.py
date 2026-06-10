import base64
from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from app.infrastructure.db.models import Issue, Comment

class SearchRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def decode_cursor(cursor_str: Optional[str]) -> Optional[datetime]:
        """Decodes a base64 string cursor back into a native Python datetime object."""
        if not cursor_str:
            return None
        try:
            decoded_bytes = base64.b64decode(cursor_str.encode("utf-8"))
            return datetime.fromisoformat(decoded_bytes.decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def encode_cursor(dt: datetime) -> str:
        """Encodes a record creation timestamp into a cursor string for secure pagination."""
        return base64.b64encode(dt.isoformat().encode("utf-8")).decode("utf-8")

    async def search_issues(
        self,
        project_id: str,
        search_query: Optional[str] = None,
        status_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        issue_type: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> Tuple[List[Issue], Optional[str]]:
        """
        Executes high-performance structured filtering and full-text searches across 
        issue properties using fast cursor positioning instead of slow database offset drops.
        """
        # Base query sorted strictly by creation time descending
        stmt = select(Issue).where(Issue.project_id == project_id).order_by(desc(Issue.created_at))

        filters = []

        # 1. Inject Cursor Pagination Constraints (created_at < cursor_timestamp)
        cursor_dt = self.decode_cursor(cursor)
        if cursor_dt:
            filters.append(Issue.created_at < cursor_dt)

        # 2. Inject Structured Search Fields
        if status_id:
            filters.append(Issue.status_id == status_id)
        if assignee_id:
            filters.append(Issue.assignee_id == assignee_id)
        if issue_type:
            filters.append(Issue.type == issue_type)

        # 3. Inject Postgres Native Full-Text Search (across Title and Description fields)
        if search_query:
            # We match using plainto_tsquery which normalizes spaces and word stems automatically
            search_vector = func.to_tsvector('english', Issue.title + ' ' + func.coalesce(Issue.description, ''))
            ts_query = func.plainto_tsquery('english', search_query)
            filters.append(search_vector.op('@@')(ts_query))

        # Apply compiled filters
        if filters:
            stmt = stmt.where(and_(*filters))

        # Fetch limit + 1 to easily determine if a subsequent page exists
        stmt = stmt.limit(limit + 1)
        
        result = await self.db.execute(stmt)
        issues = list(result.scalars().all())

        # Determine if there's a next page and isolate the cursor
        next_cursor = None
        if len(issues) > limit:
            has_next = True
            issues = issues[:limit]  # Drop the extra check element
            next_cursor = self.encode_cursor(issues[-1].created_at)
        
        return issues, next_cursor