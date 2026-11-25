import uuid

import pytest

from app.models.audit_log import AuditLog
from app.models.task import Task
from app.models.task_assignment import TaskAssignment
from tests.helpers import headers


def patch(client, tasks_org, caller, task, body):
    return client.patch(f"/tasks/{tasks_org['tasks'][task]}", json=body, headers=headers(tasks_org[caller]))


def delete(client, tasks_org, caller, task):
    return client.delete(f"/tasks/{tasks_org['tasks'][task]}", headers=headers(tasks_org[caller]))


# --- who may edit (ADR 0006) --------------------------------------------------

@pytest.mark.parametrize(
    "caller, task, expected",
    [
        ("m2", "standard_by_m2", 200),             # creator
        ("owner", "standard_by_m2", 200),          # owner edits everything
        ("m1", "confidential_assigned_to_m1", 200),  # assigned
        ("m1", "standard_by_m2", 403),             # sees it, but neither creator nor assigned
        ("admin", "standard_by_m2", 403),          # being admin does not grant editing
        ("m1", "confidential_by_owner", 404),      # cannot see it: same as missing
        ("admin", "confidential_by_owner", 404),
        ("owner", "other_org", 404),
    ],
)
def test_who_can_edit_which_task(client, tasks_org, caller, task, expected):
    assert patch(client, tasks_org, caller, task, {"status": "done"}).status_code == expected


def test_a_hidden_task_and_a_missing_one_get_the_same_404(client, tasks_org):
    h = headers(tasks_org["m1"])
    hidden = client.patch(f"/tasks/{tasks_org['tasks']['confidential_by_owner']}", json={}, headers=h)
    missing = client.patch(f"/tasks/{uuid.uuid4()}", json={}, headers=h)

    assert (hidden.status_code, missing.status_code) == (404, 404)
    assert hidden.json() == missing.json()


# --- what a PATCH changes -----------------------------------------------------

def test_an_empty_patch_changes_nothing_and_is_not_audited(client, db_session, tasks_org):
    patch(client, tasks_org, "m2", "standard_by_m2", {"description": "keep me"})
    before = db_session.query(AuditLog).filter_by(action="task.updated").count()

    body = patch(client, tasks_org, "m2", "standard_by_m2", {}).json()

    assert (body["title"], body["description"]) == ("standard_by_m2", "keep me")
    assert db_session.query(AuditLog).filter_by(action="task.updated").count() == before


def test_null_clears_the_description_but_not_the_title(client, tasks_org):
    patch(client, tasks_org, "m2", "standard_by_m2", {"description": "x"})

    cleared = patch(client, tasks_org, "m2", "standard_by_m2", {"description": None})

    assert cleared.status_code == 200
    assert cleared.json()["description"] is None
    assert patch(client, tasks_org, "m2", "standard_by_m2", {"title": None}).status_code == 422
    assert patch(client, tasks_org, "m2", "standard_by_m2", {"title": "  "}).status_code == 422
    assert patch(client, tasks_org, "m2", "standard_by_m2", {"status": None}).status_code == 422


def test_the_type_cannot_be_changed(client, tasks_org):
    body = patch(client, tasks_org, "m2", "standard_by_m2", {"type": "confidential"}).json()

    assert body["type"] == "standard"


def test_an_edit_audits_the_changed_fields_not_their_values(client, db_session, tasks_org):
    patch(client, tasks_org, "m2", "standard_by_m2", {"title": "secret plan", "status": "doing"})

    entry = db_session.query(AuditLog).filter_by(action="task.updated").one()
    assert entry.metadata_ == {"fields": ["status", "title"]}


# --- who may delete, and what deleting does -----------------------------------

@pytest.mark.parametrize(
    "caller, task, expected",
    [
        ("owner", "confidential_by_admin", 204),   # owner deletes anything in the organization
        ("admin", "confidential_by_admin", 204),   # admin deletes what they created
        ("admin", "standard_by_m2", 403),          # admin sees it, but did not create it
        ("admin", "confidential_by_owner", 404),   # admin cannot see it
        ("m2", "standard_by_m2", 403),             # members have no task.delete permission
        ("owner", "other_org", 404),
    ],
)
def test_who_can_delete_which_task(client, tasks_org, caller, task, expected):
    assert delete(client, tasks_org, caller, task).status_code == expected


def test_deleting_removes_the_task_and_its_assignments_and_keeps_the_audit(client, db_session, tasks_org):
    task_id = uuid.UUID(tasks_org["tasks"]["confidential_assigned_to_m1"])

    assert delete(client, tasks_org, "owner", "confidential_assigned_to_m1").status_code == 204

    db_session.expire_all()
    assert db_session.get(Task, task_id) is None
    assert db_session.query(TaskAssignment).filter_by(task_id=task_id).count() == 0
    entry = db_session.query(AuditLog).filter_by(action="task.deleted").one()
    assert (entry.entity_id, entry.metadata_) == (task_id, {"type": "confidential"})


def test_deleting_twice_is_a_404_the_second_time(client, tasks_org):
    assert delete(client, tasks_org, "owner", "standard_by_m2").status_code == 204
    assert delete(client, tasks_org, "owner", "standard_by_m2").status_code == 404
