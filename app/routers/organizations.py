import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.audit import record_audit
from app.db.session import get_db
from app.deps import get_current_user, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import MyOrganizationResponse, OrganizationDelete

router = APIRouter(tags=["organizations"])


@router.get("/organizations", response_model=list[MyOrganizationResponse])
def list_my_organizations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The organizations the caller belongs to, with their role in each.

    It needs no X-Organization-Id: it is how a client finds the ids to send
    in that header (ADR 0001). Deleted organizations are left out (ADR 0007).
    """
    rows = (
        db.query(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .filter(Membership.user_id == user.id, Organization.deleted_at.is_(None))
        .order_by(Organization.name, Organization.id)
        .all()
    )
    return [MyOrganizationResponse(id=org.id, name=org.name, role=role) for org, role in rows]


def soft_delete_organization(db: Session, organization_id: uuid.UUID) -> bool:
    """Mark the organization deleted; False if it already was.

    Two deletes can both pass the membership check before either commits.
    The second UPDATE waits for the first's row lock, then matches no row, so
    only one request deletes and writes the audit entry.
    """
    return db.query(Organization).filter(
        Organization.id == organization_id,
        Organization.deleted_at.is_(None),
    ).update({Organization.deleted_at: func.now()}, synchronize_session=False) == 1


@router.delete("/organization", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    data: OrganizationDelete,
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("organization.delete")),
):
    """Soft-delete the caller's organization; the body must repeat its name (ADR 0007)."""
    organization = db.get(Organization, membership.organization_id)
    if data.confirm_name != organization.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="confirm_name does not match the organization's name",
        )
    if not soft_delete_organization(db, organization.id):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )
    record_audit(db, membership, "organization.deleted", "organization", organization.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
