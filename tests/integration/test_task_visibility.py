import uuid

import pytest

from app.models.membership import MembershipRole
from app.models.task_assignment import TaskAssignment
from tests.helpers import create_task, headers, join_as, register_and_login


@pytest.fixture
def org(client, db_session):
    """One organization with every visibility case of ADR 0002, plus a task in another organization.

    Only owners and admins can create confidential tasks, so a member reaches a
    confidential task only by being assigned to it. There is no assignment
    endpoint yet, so the assignment row is inserted directly.
    """
    owner = register_and_login(client, email="owner@example.com", org="A")
    admin = join_as(client, db_session, owner, MembershipRole.admin, email="admin@example.com")
    m1 = join_as(client, db_session, owner, MembershipRole.member, email="m1@example.com")
    m2 = join_as(client, db_session, owner, MembershipRole.member, email="m2@example.com")
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


@pytest.mark.parametrize(
    "caller, expected",
    [
        # The owner sees everything in the organization, never another organization.
        ("owner", {"standard_by_m2", "confidential_by_owner", "confidential_by_admin",
                   "confidential_assigned_to_m1"}),
        # An admin sees their own confidential task, not anyone else's (ADR 0002).
        ("admin", {"standard_by_m2", "confidential_by_admin"}),
        # A member sees a confidential task only when assigned to it.
        ("m1", {"standard_by_m2", "confidential_assigned_to_m1"}),
        ("m2", {"standard_by_m2"}),
    ],
)
def test_the_list_shows_only_what_the_caller_may_see(client, org, caller, expected):
    response = client.get("/tasks", headers=headers(org[caller]))

    assert response.status_code == 200
    body = response.json()
    assert {t["title"] for t in body["items"]} == expected
    # The total counts the same visible tasks, never the hidden ones.
    assert body["total"] == len(expected)


def test_a_task_the_caller_may_not_see_is_a_404_like_one_that_does_not_exist(client, org):
    h = headers(org["m2"])
    hidden = client.get(f"/tasks/{org['tasks']['confidential_by_owner']}", headers=h)
    other_org = client.get(f"/tasks/{org['tasks']['other_org']}", headers=h)
    missing = client.get(f"/tasks/{uuid.uuid4()}", headers=h)

    assert (hidden.status_code, other_org.status_code, missing.status_code) == (404, 404, 404)
    assert hidden.json() == other_org.json() == missing.json()  # nothing tells them apart


def test_an_assigned_member_can_open_the_confidential_task(client, org):
    task_id = org["tasks"]["confidential_assigned_to_m1"]

    response = client.get(f"/tasks/{task_id}", headers=headers(org["m1"]))

    assert response.status_code == 200
    assert response.json()["id"] == task_id


def test_pages_do_not_overlap_and_the_total_ignores_the_page(client, org):
    h = headers(org["owner"])

    first = client.get("/tasks?limit=3&offset=0", headers=h).json()
    second = client.get("/tasks?limit=3&offset=3", headers=h).json()

    assert (len(first["items"]), len(second["items"])) == (3, 1)
    assert first["total"] == second["total"] == 4
    assert not {t["id"] for t in first["items"]} & {t["id"] for t in second["items"]}


def test_a_member_pages_through_only_visible_tasks(client, org):
    # Hidden tasks sit between m1's visible ones. If the rule ran in Python
    # after LIMIT, a page could come back empty or short (ADR 0004).
    h = headers(org["m1"])

    pages = [client.get(f"/tasks?limit=1&offset={i}", headers=h).json() for i in range(2)]

    assert [len(p["items"]) for p in pages] == [1, 1]
    assert {p["items"][0]["title"] for p in pages} == {"standard_by_m2", "confidential_assigned_to_m1"}
    assert all(p["total"] == 2 for p in pages)


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_page_parameters_out_of_range_are_a_422(client, org, query):
    assert client.get(f"/tasks?{query}", headers=headers(org["owner"])).status_code == 422


def test_a_page_past_the_end_is_empty_and_leaks_nothing(client, org):
    # m2 sees one task. Hidden tasks must not fill pages beyond the visible ones,
    # and the total still counts only what m2 may see.
    response = client.get("/tasks?limit=10&offset=1", headers=headers(org["m2"]))

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 1}


def test_the_list_is_newest_first(client, org):
    body = client.get("/tasks", headers=headers(org["owner"])).json()

    # The fixture creates the tasks in this order; the newest comes first.
    assert [t["title"] for t in body["items"]] == [
        "confidential_assigned_to_m1",
        "confidential_by_admin",
        "confidential_by_owner",
        "standard_by_m2",
    ]
