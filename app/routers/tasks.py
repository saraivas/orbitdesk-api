from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.deps import get_current_membership
from app.models.membership import Membership
from app.models.task import Task, TaskType
from app.core.permissions import has_permission
from app.schemas.task import TaskCreate, TaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    task_data: TaskCreate,
    db: Session = Depends(get_db),
    membership: Membership = Depends(get_current_membership),
):
    required_permission = (
        "task.create_confidential" if task_data.type == TaskType.confidential else "task.create"
    )

    if not has_permission(membership.role, required_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {required_permission}",
        )

    new_task = Task(
        organization_id=membership.organization_id,
        created_by=membership.user_id,
        title=task_data.title,
        description=task_data.description,
        type=task_data.type,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return new_task
