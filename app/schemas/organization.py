import uuid
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict


class UserRegisterWithOrg(BaseModel):
    email: EmailStr
    password: str
    organization_name: str

    @field_validator("organization_name")
    @classmethod
    def organization_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Organization name cannot be blank")
        return value.strip()


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    organization: OrganizationResponse
