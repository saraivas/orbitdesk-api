import uuid

from pydantic import BaseModel, EmailStr


class AssigneeAdd(BaseModel):
    user_id: uuid.UUID


class AssigneeResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
