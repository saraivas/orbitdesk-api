import pytest

from app.models.audit_log import AuditLog
from app.models.membership import MembershipRole
from app.models.task import Task
from tests.conftest import TestingSessionLocal
from tests.helpers import create_task, join_as, register_and_login


def test_creating_a_task_writes_a_task_created_audit_entry(client, db_session):
    owner = register_and_login(client)

    task_id = create_task(client, owner, type="confidential").json()["id"]

    entries = db_session.query(AuditLog).all()
    assert len(entries) == 1
    entry = entries[0]
    assert (entry.action, entry.entity_type, str(entry.entity_id)) == ("task.created", "task", task_id)
    assert (str(entry.actor_user_id), str(entry.organization_id)) == (owner["user_id"], owner["org_id"])
    # Only the type: copying the title would spread confidential text to a
    # table that has no visibility rules.
    assert entry.metadata_ == {"type": "confidential"}


def test_a_refused_task_writes_no_audit_entry(client, db_session):
    owner = register_and_login(client)
    member = join_as(client, owner, MembershipRole.member, email="m@example.com")

    assert create_task(client, member, type="confidential").status_code == 403
    assert db_session.query(AuditLog).filter_by(action="task.created").count() == 0


def test_if_the_audit_write_fails_the_task_is_not_saved(client, monkeypatch):
    owner = register_and_login(client)

    def broken_audit(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr("app.routers.tasks.record_audit", broken_audit)

    with pytest.raises(RuntimeError):
        create_task(client, owner)

    # A separate session only sees committed rows.
    with TestingSessionLocal() as fresh:
        assert fresh.query(Task).count() == 0
