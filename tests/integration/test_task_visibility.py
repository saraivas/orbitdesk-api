import uuid

import pytest

from tests.helpers import headers


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
def test_the_list_shows_only_what_the_caller_may_see(client, tasks_org, caller, expected):
    response = client.get("/tasks", headers=headers(tasks_org[caller]))

    assert response.status_code == 200
    body = response.json()
    assert {t["title"] for t in body["items"]} == expected
    # The total counts the same visible tasks, never the hidden ones.
    assert body["total"] == len(expected)


def test_a_task_the_caller_may_not_see_is_a_404_like_one_that_does_not_exist(client, tasks_org):
    h = headers(tasks_org["m2"])
    hidden = client.get(f"/tasks/{tasks_org['tasks']['confidential_by_owner']}", headers=h)
    other_org = client.get(f"/tasks/{tasks_org['tasks']['other_org']}", headers=h)
    missing = client.get(f"/tasks/{uuid.uuid4()}", headers=h)

    assert (hidden.status_code, other_org.status_code, missing.status_code) == (404, 404, 404)
    assert hidden.json() == other_org.json() == missing.json()  # nothing tells them apart


def test_an_assigned_member_can_open_the_confidential_task(client, tasks_org):
    task_id = tasks_org["tasks"]["confidential_assigned_to_m1"]

    response = client.get(f"/tasks/{task_id}", headers=headers(tasks_org["m1"]))

    assert response.status_code == 200
    assert response.json()["id"] == task_id


def test_pages_do_not_overlap_and_the_total_ignores_the_page(client, tasks_org):
    h = headers(tasks_org["owner"])

    first = client.get("/tasks?limit=3&offset=0", headers=h).json()
    second = client.get("/tasks?limit=3&offset=3", headers=h).json()

    assert (len(first["items"]), len(second["items"])) == (3, 1)
    assert first["total"] == second["total"] == 4
    assert not {t["id"] for t in first["items"]} & {t["id"] for t in second["items"]}


def test_a_member_pages_through_only_visible_tasks(client, tasks_org):
    # Hidden tasks sit between m1's visible ones. If the rule ran in Python
    # after LIMIT, a page could come back empty or short (ADR 0004).
    h = headers(tasks_org["m1"])

    pages = [client.get(f"/tasks?limit=1&offset={i}", headers=h).json() for i in range(2)]

    assert [len(p["items"]) for p in pages] == [1, 1]
    assert {p["items"][0]["title"] for p in pages} == {"standard_by_m2", "confidential_assigned_to_m1"}
    assert all(p["total"] == 2 for p in pages)


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_page_parameters_out_of_range_are_a_422(client, tasks_org, query):
    assert client.get(f"/tasks?{query}", headers=headers(tasks_org["owner"])).status_code == 422


def test_a_page_past_the_end_is_empty_and_leaks_nothing(client, tasks_org):
    # m2 sees one task. Hidden tasks must not fill pages beyond the visible ones,
    # and the total still counts only what m2 may see.
    response = client.get("/tasks?limit=10&offset=1", headers=headers(tasks_org["m2"]))

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 1}


def test_the_list_is_newest_first(client, tasks_org):
    body = client.get("/tasks", headers=headers(tasks_org["owner"])).json()

    # The fixture creates the tasks in this order; the newest comes first.
    assert [t["title"] for t in body["items"]] == [
        "confidential_assigned_to_m1",
        "confidential_by_admin",
        "confidential_by_owner",
        "standard_by_m2",
    ]
