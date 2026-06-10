import re
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.db.models import Comment, User, Issue, IssueWatcher
from app.domain.errors import NotFoundError
from app.domain.events import CommentAdded
from app.events.dispatcher import EventDispatcher, dispatcher as default_dispatcher


class CollaborationService:
    def __init__(self, db: AsyncSession, dispatcher: EventDispatcher = None):
        self.db = db
        self.dispatcher = dispatcher or default_dispatcher
        self._mention_re = re.compile(r"@([\w.\-]+)")

    async def add_comment(
        self,
        issue_id: str,
        author_id: str,
        body: str,
        parent_id: Optional[str] = None,
    ) -> Comment:
        issue_result = await self.db.execute(select(Issue).where(Issue.id == issue_id))
        issue = issue_result.scalar_one_or_none()
        if not issue:
            raise NotFoundError("Issue not found")

        # Parse @mention display names → user IDs
        raw_mentions = self._mention_re.findall(body)
        mentioned_ids: list[str] = []
        if raw_mentions:
            res = await self.db.execute(
                select(User.id).where(User.display_name.in_(raw_mentions))
            )
            mentioned_ids = list(res.scalars().all())

        comment_id = str(uuid.uuid4())
        comment = Comment(
            id=comment_id,
            issue_id=issue_id,
            author_id=author_id,
            body=body,
            parent_id=parent_id,
            mentions=mentioned_ids,
        )
        self.db.add(comment)

        # Auto-subscribe the commenter as a watcher
        await self._ensure_watcher(issue_id, author_id)

        # Collect current watcher IDs before committing so the dispatcher
        # can send notifications without needing a DB session itself.
        watcher_result = await self.db.execute(
            select(IssueWatcher.user_id).where(IssueWatcher.issue_id == issue_id)
        )
        watcher_ids = list(watcher_result.scalars().all())

        await self.db.commit()

        await self.dispatcher.dispatch(CommentAdded(
            comment_id=comment_id,
            issue_id=issue_id,
            project_id=issue.project_id,
            author_id=author_id,
            mentioned_user_ids=mentioned_ids,
            watcher_ids=watcher_ids,
        ))
        return comment

    async def add_watcher(self, issue_id: str, user_id: str) -> IssueWatcher:
        watcher = await self._ensure_watcher(issue_id, user_id)
        await self.db.commit()
        return watcher

    async def _ensure_watcher(self, issue_id: str, user_id: str) -> IssueWatcher:
        existing = (await self.db.execute(
            select(IssueWatcher).where(
                IssueWatcher.issue_id == issue_id,
                IssueWatcher.user_id == user_id,
            )
        )).scalar_one_or_none()
        if existing:
            return existing
        watcher = IssueWatcher(id=str(uuid.uuid4()), issue_id=issue_id, user_id=user_id)
        self.db.add(watcher)
        return watcher
