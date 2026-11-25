import uuid

import pytest

from app.models.membership import MembershipRole
from app.models.task_assignment import TaskAssignment
from tests.helpers import create_task, join_as, register_and_login


@pytest.fixture
def tasks_org(client, db_session):
    """One organization with every visibility case of ADR 0002, plus a task in another organization.

    Only owners and admins can create confidential tasks, so a member reaches a
    confidential task only by being assigned to it. There is no assignment
    endpoint yet, so the assignment row is inserted directly.
    """
    owner = register_and_login(client, email="owner@example.com", org="A")
    admin = join_as(client, owner, MembershipRole.admin, email="admin@example.com")
    m1 = join_as(client, owner, MembershipRole.member, email="m1@example.com")
    m2 = join_as(client, owner, MembershipRole.member, email="m2@example.com")
    outsider = register_and_login(client, email="b@example.com", org="B")

    def task(session, title, type="standard"):
        return create_task(client, session, title=title, type=type).json()["id"]

    tasks = {
        "standard_by_m2": task(m2, "standard_by_m2"),
        "confidential_by_owner": task(owner, "confidential_by_owner", "confidential"),
        "confidential_by_admin": task(admin, "confidential_by_admin", "confidential"),
        "confidential_assigned_to_m1": task(owner, "confidential_assigned_to_m1", "confidential"),
        "other_org": task(outsider, "other_org"),
    }
    db_session.add(TaskAssignment(
        task_id=uuid.UUID(tasks["confidential_assigned_to_m1"]),
        user_id=uuid.UUID(m1["user_id"]),
        assigned_by=uuid.UUID(owner["user_id"]),
    ))
    db_session.commit()

    return {"owner": owner, "admin": admin, "m1": m1, "m2": m2, "tasks": tasks}
