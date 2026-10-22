from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import decode_token
from app.core.permissions import has_permission
from app.core.redis import get_redis
from app.core.sessions import is_session_active
from app.models.user import User
from app.models.membership import Membership

bearer_scheme = HTTPBearer()


def get_access_payload(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    r: redis.Redis = Depends(get_redis),
) -> dict:
    """Decode the access token and check that its session still exists (ADR 0003)."""
    payload = decode_token(credentials.credentials)
    sid = payload.get("sid") if payload else None
    sub = payload.get("sub") if payload else None

    if (
        payload is None
        or payload.get("type") != "access"
        or not isinstance(sid, str)
        or not isinstance(sub, str)
        or not is_session_active(r, sid, sub)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return payload


def get_current_user(
    payload: dict = Depends(get_access_payload),
    db: Session = Depends(get_db),
) -> User:
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


def get_current_membership(
    x_organization_id: str = Header(..., alias="X-Organization-Id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Membership:
    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == current_user.id,
            Membership.organization_id == x_organization_id,
        )
        .first()
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    return membership


def require_permission(permission: str):
    def checker(membership: Membership = Depends(get_current_membership)) -> Membership:
        if not has_permission(membership.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission}",
            )
        return membership

    return checker
