import uuid

import pytest

from app.models.audit_log import AuditLog
from tests.helpers import headers, register_and_login


def assign(client, tasks_org, caller, task, user):
    return client.post(
        f"/tasks/{tasks_org['tasks'][task]}/assignees",
        json={"user_id": user["user_id"]},
        headers=headers(tasks_org[caller]),
    )


def unassign(client, tasks_org, caller, task, user):
    return client.delete(
        f"/tasks/{tasks_org['tasks'][task]}/assignees/{user['user_id']}",
        headers=headers(tasks_org[caller]),
    )


def assignees(client, tasks_org, caller, task):
    return client.get(f"/tasks/{tasks_org['tasks'][task]}/assignees", headers=headers(tasks_org[caller]))


def can_see(client, tasks_org, caller, task):
    return client.get(f"/tasks/{tasks_org['tasks'][task]}", headers=headers(tasks_org[caller])).status_code == 200


# --- who may assign (ADR 0002) ------------------------------------------------

@pytest.mark.parametrize(
    "caller, task, target, expected",
    [
        ("owner", "confidential_by_admin", "m2", 201),     # the owner assigns on any task
        ("admin", "confidential_by_admin", "m2", 201),     # the creator assigns
        ("m2", "standard_by_m2", "m1", 201),               # a member who created the task too
        ("admin", "standard_by_m2", "m1", 403),            # sees it, did not create it
        ("m1", "confidential_assigned_to_m1", "m2", 403),  # an assignee does not assign others
        ("m2", "confidential_by_owner", "m1", 404),        # cannot see it
    ],
)
def test_only_the_creator_or_the_owner_assigns(client, tasks_org, caller, task, target, expected):
    assert assign(client, tasks_org, caller, task, tasks_org[target]).status_code == expected


def test_only_members_of_the_organization_can_be_assigned(client, tasks_org):
    outsider = register_and_login(client, email="stranger@example.com", org="Elsewhere")

    response = assign(client, tasks_org, "owner", "confidential_by_owner", outsider)

    assert response.status_code == 404


def test_assigning_the_same_person_twice_is_a_409(client, tasks_org):
    assert assign(client, tasks_org, "owner", "confidential_by_owner", tasks_org["m2"]).status_code == 201
    assert assign(client, tasks_org, "owner", "confidential_by_owner", tasks_org["m2"]).status_code == 409


# --- assignment is access -----------------------------------------------------

def test_assigning_gives_access_and_unassigning_takes_it_back(client, tasks_org):
    task = "confidential_by_owner"
    assert not can_see(client, tasks_org, "m2", task)

    assign(client, tasks_org, "owner", task, tasks_org["m2"])
    assert can_see(client, tasks_org, "m2", task)

    assert unassign(client, tasks_org, "owner", task, tasks_org["m2"]).status_code == 204
    assert not can_see(client, tasks_org, "m2", task)


def test_unassigning_someone_not_assigned_is_a_404(client, tasks_org):
    assert unassign(client, tasks_org, "owner", "confidential_by_owner", tasks_org["m2"]).status_code == 404


def test_an_assignee_cannot_unassign(client, tasks_org):
    task = "confidential_assigned_to_m1"
    assert unassign(client, tasks_org, "m1", task, tasks_org["m1"]).status_code == 403


# --- listing ------------------------------------------------------------------

def test_whoever_sees_the_task_sees_its_assignees(client, tasks_org):
    response = assignees(client, tasks_org, "m1", "confidential_assigned_to_m1")

    assert response.status_code == 200
    assert [a["email"] for a in response.json()] == ["m1@example.com"]


def test_the_assignees_of_a_hidden_task_are_a_404(client, tasks_org):
    assert assignees(client, tasks_org, "m2", "confidential_assigned_to_m1").status_code == 404


# --- audit --------------------------------------------------------------------

def test_assignment_changes_are_audited(client, db_session, tasks_org):
    task = "confidential_by_owner"
    m2 = uuid.UUID(tasks_org["m2"]["user_id"])

    assign(client, tasks_org, "owner", task, tasks_org["m2"])
    unassign(client, tasks_org, "owner", task, tasks_org["m2"])

    entries = (
        db_session.query(AuditLog)
        .filter(AuditLog.action.in_(["task.assigned", "task.unassigned"]),
                AuditLog.entity_id == uuid.UUID(tasks_org["tasks"][task]))
        .order_by(AuditLog.created_at)
        .all()
    )
    assert [(e.action, e.metadata_) for e in entries] == [
        ("task.assigned", {"user_id": str(m2)}),
        ("task.unassigned", {"user_id": str(m2)}),
    ]
