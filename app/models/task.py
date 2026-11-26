import uuid
import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base import Base


class TaskStatus(str, enum.Enum):
    todo = "todo"
    doing = "doing"
    done = "done"


class TaskType(str, enum.Enum):
    standard = "standard"
    confidential = "confidential"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.todo, nullable=False)
    type = Column(Enum(TaskType), default=TaskType.standard, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # GET /tasks orders by created_at within one organization: these return a
    # page in index order instead of reading and sorting every task of the
    # organization. The first also serves any lookup by organization_id alone.
    __table_args__ = (
        Index("ix_tasks_org_created", "organization_id", "created_at"),
        Index("ix_tasks_org_status_created", "organization_id", "status", "created_at"),
    )
