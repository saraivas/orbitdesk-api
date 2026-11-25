import uuid

import pytest

from app.models.membership import MembershipRole
from app.models.task import Task
from tests.helpers import create_task, join_as, register_and_login


def test_owner_creates_a_task_in_the_organization_of_the_header(client, db_session):
    owner = register_and_login(client)

    response = create_task(client, owner, title="  Write the ADR  ")

    assert response.status_code == 201
    body = response.json()
    assert (body["title"], body["type"], body["status"]) == ("Write the ADR", "standard", "todo")
    assert body["created_by"] == owner["user_id"]
    task = db_session.get(Task, uuid.UUID(body["id"]))
    assert str(task.organization_id) == owner["org_id"]


def test_an_organization_id_in_the_body_is_ignored(client, db_session):
    owner = register_and_login(client, email="a@example.com", org="A")
    other = register_and_login(client, email="b@example.com", org="B")

    response = create_task(client, owner, organization_id=other["org_id"])

    task = db_session.get(Task, uuid.UUID(response.json()["id"]))
    assert str(task.organization_id) == owner["org_id"]


@pytest.mark.parametrize(
    "role, task_type, expected",
    [
        (MembershipRole.member, "standard", 201),
        (MembershipRole.member, "confidential", 403),
        (MembershipRole.admin, "confidential", 201),
        (MembershipRole.owner, "confidential", 201),
    ],
)
def test_who_can_create_which_type(client, db_session, role, task_type, expected):
    owner = register_and_login(client)
    caller = owner if role == MembershipRole.owner else join_as(
        client, owner, role, email="someone@example.com"
    )

    assert create_task(client, caller, type=task_type).status_code == expected
