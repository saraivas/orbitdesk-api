import redis
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app.core.redis import get_redis
from app.core.sessions import (
    RotationStatus,
    create_session,
    new_id,
    revoke_all_sessions,
    revoke_session,
    rotate_session,
)
from app.db.session import get_db
from app.deps import get_access_payload
from app.schemas.auth import RefreshRequest, TokenResponse
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.organization import Organization
from app.models.membership import Membership, MembershipRole
from app.schemas.organization import UserRegisterWithOrg, RegisterResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegisterWithOrg, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    new_user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
    )
    db.add(new_user)
    db.flush()

    new_org = Organization(
        name=user_data.organization_name,
        created_by=new_user.id,
    )
    db.add(new_org)
    db.flush()

    membership = Membership(
        user_id=new_user.id,
        organization_id=new_org.id,
        role=MembershipRole.owner,
    )
    db.add(membership)

    db.commit()
    db.refresh(new_user)
    db.refresh(new_org)

    return RegisterResponse(
        user_id=new_user.id,
        email=new_user.email,
        organization=new_org,
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _invalid_refresh() -> HTTPException:
    # One response for every kind of rejection, so a caller learns nothing
    # about why the token was refused.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )


@router.post("/login", response_model=TokenResponse)
def login(
    user_data: UserCreate,
    response: Response,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    user = db.query(User).filter(User.email == user_data.email).first()

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    session = create_session(r, str(user.id))
    _no_store(response)
    return TokenResponse(
        access_token=create_access_token(str(user.id), session.sid),
        refresh_token=create_refresh_token(str(user.id), session.sid, session.jti, session.expires_at),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    body: RefreshRequest,
    response: Response,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise _invalid_refresh()

    sub, sid, jti = payload.get("sub"), payload.get("sid"), payload.get("jti")
    if not all(isinstance(value, str) for value in (sub, sid, jti)):
        raise _invalid_refresh()

    new_jti = new_id()
    rotation = rotate_session(r, sid, sub, jti, new_jti)
    if rotation.status is not RotationStatus.ROTATED:
        raise _invalid_refresh()

    # The session is valid and rotated; the user may still have been deleted.
    user = db.query(User).filter(User.id == sub).first()
    if user is None:
        revoke_session(r, sid, sub)
        raise _invalid_refresh()

    _no_store(response)
    return TokenResponse(
        access_token=create_access_token(sub, sid),
        refresh_token=create_refresh_token(sub, sid, new_jti, rotation.expires_at),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: dict = Depends(get_access_payload),
    r: redis.Redis = Depends(get_redis),
):
    """End the session of the access token used for this call."""
    revoke_session(r, payload["sid"], payload["sub"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    payload: dict = Depends(get_access_payload),
    r: redis.Redis = Depends(get_redis),
):
    """End every session of the caller, on all devices."""
    revoke_all_sessions(r, payload["sub"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
