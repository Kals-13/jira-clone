import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.models import Project, ProjectMember, Role, WorkflowStatus, WorkflowTransition

class ProjectRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_project_with_defaults(self, name: str, key: str, description: str = None, creator_id: str = None) -> Project:
        project = Project(
            id=str(uuid.uuid4()),
            name=name,
            key=key.upper(),
            description=description
        )
        self.db.add(project)
        await self.db.flush()

        if creator_id:
            self.db.add(ProjectMember(
                project_id=project.id,
                user_id=creator_id,
                role=Role.project_lead
            ))
        
        # 1. Generate 4 unique IDs for the complete workflow cycle
        todo_id = str(uuid.uuid4())
        inprogress_id = str(uuid.uuid4())
        inreview_id = str(uuid.uuid4())
        done_id = str(uuid.uuid4())

        # 2. Build out the 4 column records
        default_columns = [
            WorkflowStatus(id=todo_id, project_id=project.id, name="To Do", position=0, is_terminal=False),
            WorkflowStatus(id=inprogress_id, project_id=project.id, name="In Progress", position=1, is_terminal=False),
            WorkflowStatus(id=inreview_id, project_id=project.id, name="In Review", position=2, is_terminal=False),
            WorkflowStatus(id=done_id, project_id=project.id, name="Done", position=3, is_terminal=True)
        ]
        self.db.add_all(default_columns)
        
        # 3. Stitch pathways together and toggle auto-assignment rules
        default_transitions = [
            # To Do -> In Progress
            WorkflowTransition(
                id=str(uuid.uuid4()), project_id=project.id, 
                from_status_id=todo_id, to_status_id=inprogress_id, 
                auto_assign_reviewer=False
            ),
            # In Progress -> In Review (Enforces reviewer allocation logic triggers)
            WorkflowTransition(
                id=str(uuid.uuid4()), project_id=project.id, 
                from_status_id=inprogress_id, to_status_id=inreview_id, 
                auto_assign_reviewer=True
            ),
            # In Review -> Done
            WorkflowTransition(
                id=str(uuid.uuid4()), project_id=project.id, 
                from_status_id=inreview_id, to_status_id=done_id, 
                auto_assign_reviewer=False
            )
        ]
        self.db.add_all(default_transitions)
        
        await self.db.commit()
        await self.db.refresh(project)
        
        return project
    
    async def get_transition_rule(self, project_id: str, from_status_id: str, to_status_id: str):
        """Fetches the full transition rule row matching the specific pathway."""
        result = await self.db.execute(
            select(WorkflowTransition).where(
                WorkflowTransition.project_id == project_id,
                WorkflowTransition.from_status_id == from_status_id,
                WorkflowTransition.to_status_id == to_status_id
            )
        )
        return result.scalar_one_or_none()