import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.permissions import has_permission
from app.db.session import get_db
from app.deps import get_current_membership, require_permission
from app.models.membership import Membership, MembershipRole
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from app.models.user import User
from app.schemas.member import MemberAdd, MemberResponse, MemberRoleUpdate

router = APIRouter(prefix="/members", tags=["members"])


def count_owners_for_update(db: Session, organization_id: uuid.UUID) -> int:
    """Count the organization's owners, locking their rows until the transaction ends.

    Two requests that each demote or remove one of the last two owners would
    both count two owners and both pass. With FOR UPDATE the second waits for
    the first to commit, then counts again and sees one (ADR 0005).

    Callers load the target membership before calling this, without a lock.
    That is still safe: after waiting, Postgres re-checks each locked row
    against the WHERE, so an owner demoted meanwhile is no longer counted.
    """
    return len(
        db.query(Membership)
        .filter(
            Membership.organization_id == organization_id,
            Membership.role == MembershipRole.owner,
        )
        .with_for_update()
        .all()
    )


def ensure_another_owner(db: Session, organization_id: uuid.UUID) -> None:
    if count_owners_for_update(db, organization_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization needs at least one owner",
        )


def can_manage(actor: Membership, role: MembershipRole) -> bool:
    """The owner manages every role; an admin only members (ADR 0005)."""
    return actor.role == MembershipRole.owner or role == MembershipRole.member


def get_target(db: Session, actor: Membership, user_id: uuid.UUID) -> Membership:
    target = (
        db.query(Membership)
        .filter(Membership.organization_id == actor.organization_id, Membership.user_id == user_id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return target


def is_duplicate_member(error: IntegrityError) -> bool:
    """True only for the (user_id, organization_id) unique constraint.

    A foreign-key failure, for example, must not be reported as "already a
    member". The constraint name comes from the Postgres driver (psycopg2).
    """
    return getattr(error.orig.diag, "constraint_name", None) == "uq_user_organization"


def to_response(membership: Membership, email: str) -> MemberResponse:
    return MemberResponse(
        user_id=membership.user_id, email=email, role=membership.role, created_at=membership.created_at
    )


@router.get("", response_model=list[MemberResponse])
def list_members(
    db: Session = Depends(get_db),
    membership: Membership = Depends(get_current_membership),
):
    rows = (
        db.query(Membership, User.email)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.organization_id == membership.organization_id)
        .order_by(Membership.created_at, Membership.user_id)
        .all()
    )
    return [to_response(m, email) for m, email in rows]


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(
    data: MemberAdd,
    db: Session = Depends(get_db),
    actor: Membership = Depends(require_permission("member.invite")),
):
    if not can_manage(actor, data.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot grant this role")

    user = db.query(User).filter(User.email == data.email).first()
    if user is None:
        # Known limitation: this tells the caller the email has no account (ADR 0005).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Auto-accept: no invitation step, the membership exists at once.
    new = Membership(user_id=user.id, organization_id=actor.organization_id, role=data.role)
    db.add(new)
    try:
        db.flush()
    except IntegrityError as error:
        # uq_user_organization decides, not a read before the insert: two
        # concurrent adds would both pass such a read (ADR 0005).
        db.rollback()
        if not is_duplicate_member(error):
            raise  # any other integrity error is unexpected: let it be a 500
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member")
    record_audit(db, actor, "member.invited", "member", user.id, {"role": data.role.value})
    db.commit()
    db.refresh(new)
    return to_response(new, user.email)


@router.patch("/{user_id}", response_model=MemberResponse)
def change_role(
    user_id: uuid.UUID,
    data: MemberRoleUpdate,
    db: Session = Depends(get_db),
    actor: Membership = Depends(require_permission("member.update_role")),
):
    target = get_target(db, actor, user_id)
    if target.role != data.role:
        if target.role == MembershipRole.owner:
            ensure_another_owner(db, actor.organization_id)
        record_audit(db, actor, "member.role_changed", "member", user_id,
                     {"from": target.role.value, "to": data.role.value})
        target.role = data.role
        db.commit()
    email = db.query(User.email).filter(User.id == user_id).scalar()
    return to_response(target, email)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: Membership = Depends(get_current_membership),
):
    target = get_target(db, actor, user_id)
    leaving = target.user_id == actor.user_id
    if not leaving and not (has_permission(actor.role, "member.remove") and can_manage(actor, target.role)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot remove this member")
    if target.role == MembershipRole.owner:
        ensure_another_owner(db, actor.organization_id)

    # Assignments go too: kept, they would give back access to confidential
    # tasks if the user were added again.
    org_tasks = select(Task.id).where(Task.organization_id == actor.organization_id)
    db.query(TaskAssignment).filter(
        TaskAssignment.user_id == user_id, TaskAssignment.task_id.in_(org_tasks)
    ).delete(synchronize_session=False)
    record_audit(db, actor, "member.removed", "member", user_id, {"role": target.role.value})
    db.delete(target)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
