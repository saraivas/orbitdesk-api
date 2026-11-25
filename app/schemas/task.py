import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from app.models.task import TaskStatus, TaskType


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: TaskType = TaskType.standard

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip()


class TaskUpdate(BaseModel):
    # An unknown field is a 422: silently ignoring {"type": ...} or a typo
    # would answer 200 for a change that never happened.
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def required_fields_are_not_cleared(self) -> "TaskUpdate":
        # Omitted means "leave as is"; an explicit null means "clear", which
        # only the description allows (the columns are NOT NULL).
        for field in ("title", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TaskResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    status: TaskStatus
    type: TaskType
    created_by: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class TaskPage(BaseModel):
    items: list[TaskResponse]
    total: int  # tasks the caller may see, across all pages
