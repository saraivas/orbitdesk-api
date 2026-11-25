import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.deps import get_current_membership
from app.models.membership import Membership, MembershipRole
from app.models.task import Task, TaskType
from app.models.task_assignment import TaskAssignment
from app.core.audit import record_audit
from app.core.permissions import has_permission
from app.schemas.task import TaskCreate, TaskPage, TaskResponse

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
    db.flush()  # assigns new_task.id for the audit entry
    # The type only, never the title: the audit log has no visibility rules.
    record_audit(db, membership, "task.created", "task", new_task.id, {"type": new_task.type.value})
    db.commit()
    db.refresh(new_task)

    return new_task


def visible_tasks(db: Session, membership: Membership):
    """Tasks the member may see, as SQL (ADRs 0002 and 0004).

    The list, its total and the detail all start from this query, so they
    cannot disagree about who sees what.
    """
    query = db.query(Task).filter(Task.organization_id == membership.organization_id)
    if membership.role == MembershipRole.owner:
        return query
    assigned = exists().where(
        TaskAssignment.task_id == Task.id,
        TaskAssignment.user_id == membership.user_id,
    )
    return query.filter(or_(
        Task.type == TaskType.standard,
        Task.created_by == membership.user_id,
        assigned,
    ))


@router.get("", response_model=TaskPage)
def list_tasks(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    membership: Membership = Depends(get_current_membership),
):
    query = visible_tasks(db, membership)
    items = (
        query.order_by(Task.created_at.desc(), Task.id)  # id breaks ties, so pages are stable
        .limit(limit)
        .offset(offset)
        .all()
    )
    return TaskPage(items=items, total=query.count())


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: Membership = Depends(get_current_membership),
):
    task = visible_tasks(db, membership).filter(Task.id == task_id).first()
    if task is None:
        # The same answer for a task that does not exist and one the caller may
        # not see, so nothing reveals that a hidden task exists (ADR 0004).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task
