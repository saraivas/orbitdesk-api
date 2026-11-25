from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import MyOrganizationResponse

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[MyOrganizationResponse])
def list_my_organizations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The organizations the caller belongs to, with their role in each.

    It needs no X-Organization-Id: it is how a client finds the ids to send
    in that header (ADR 0001).
    """
    rows = (
        db.query(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .filter(Membership.user_id == user.id)
        .order_by(Organization.name, Organization.id)
        .all()
    )
    return [MyOrganizationResponse(id=org.id, name=org.name, role=role) for org, role in rows]
