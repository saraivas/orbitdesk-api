import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.deps import get_current_membership, require_permission
from app.models.membership import Membership, MembershipRole
from app.models.task import Task, TaskType
from app.models.task_assignment import TaskAssignment
from app.core.audit import record_audit
from app.core.permissions import has_permission
from app.schemas.task import TaskCreate, TaskPage, TaskResponse, TaskUpdate

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
    return get_visible_task(db, membership, task_id)


def get_visible_task(db: Session, membership: Membership, task_id: uuid.UUID) -> Task:
    task = visible_tasks(db, membership).filter(Task.id == task_id).first()
    if task is None:
        # The same answer for a task that does not exist and one the caller may
        # not see, so nothing reveals that a hidden task exists (ADR 0004).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def get_editable_task(db: Session, membership: Membership, task_id: uuid.UUID) -> Task:
    """A task the member may change: the owner, its creator or an assignee (ADR 0006).

    Visibility is checked first. A task the caller cannot see is a 404, and
    only a task they can see but not edit is a 403, which reveals nothing
    they do not already know.
    """
    task = get_visible_task(db, membership, task_id)
    if membership.role == MembershipRole.owner or task.created_by == membership.user_id:
        return task
    assigned = db.query(exists().where(
        TaskAssignment.task_id == task.id, TaskAssignment.user_id == membership.user_id
    )).scalar()
    if not assigned:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot change this task")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: uuid.UUID,
    data: TaskUpdate,
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("task.update")),
):
    task = get_editable_task(db, membership, task_id)
    changes = data.model_dump(exclude_unset=True)  # omitted fields stay as they are
    if changes:
        for field, value in changes.items():
            setattr(task, field, value)
        # Field names only: the values may be confidential, and the audit log
        # has no visibility rules.
        record_audit(db, membership, "task.updated", "task", task.id, {"fields": sorted(changes)})
        db.commit()
        db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("task.delete")),
):
    task = get_editable_task(db, membership, task_id)
    db.query(TaskAssignment).filter(TaskAssignment.task_id == task.id).delete(synchronize_session=False)
    # Hard delete: the audit log has no foreign key to tasks, so this entry stays.
    record_audit(db, membership, "task.deleted", "task", task.id, {"type": task.type.value})
    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
