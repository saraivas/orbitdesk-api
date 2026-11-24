import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.membership import Membership


def record_audit(
    db: Session,
    membership: Membership,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    metadata: dict | None = None,
) -> None:
    """Add an audit entry to the caller's transaction (ADR 0002).

    It never commits: the caller commits the change and its audit entry
    together, so one cannot be saved without the other.
    """
    db.add(AuditLog(
        organization_id=membership.organization_id,
        actor_user_id=membership.user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=metadata,
    ))
