import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models.membership import MembershipRole


class MemberAdd(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.member


class MemberRoleUpdate(BaseModel):
    role: MembershipRole


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    role: MembershipRole
    created_at: datetime
