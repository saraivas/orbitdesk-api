import uuid

from tests.helpers import headers


def titles(client, session, **params):
    response = client.get("/tasks", params=params, headers=headers(session))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == len(body["items"])
    return sorted(t["title"] for t in body["items"])


def test_filtering_by_another_users_assignments_never_reveals_hidden_tasks(client, tasks_org):
    # m1 is assigned to a confidential task that m2 cannot see. Filtering by
    # m1 must not show it to m2: filters narrow visible_tasks, never widen it.
    m1, m2 = tasks_org["m1"], tasks_org["m2"]

    assert titles(client, m2, assignee=m1["user_id"]) == []
    assert titles(client, tasks_org["owner"], assignee=m1["user_id"]) == ["confidential_assigned_to_m1"]


def test_me_filters_by_the_caller(client, tasks_org):
    assert titles(client, tasks_org["m1"], assignee="me") == ["confidential_assigned_to_m1"]
    assert titles(client, tasks_org["m2"], created_by="me") == ["standard_by_m2"]
    assert titles(client, tasks_org["owner"], created_by=tasks_org["admin"]["user_id"]) == ["confidential_by_admin"]


def test_status_filter_and_total_count_only_matching_tasks(client, tasks_org):
    m2 = tasks_org["m2"]
    task_id = tasks_org["tasks"]["standard_by_m2"]
    assert client.patch(f"/tasks/{task_id}", json={"status": "doing"}, headers=headers(m2)).status_code == 200

    assert titles(client, tasks_org["owner"], status="doing") == ["standard_by_m2"]
    assert "standard_by_m2" not in titles(client, tasks_org["owner"], status="todo")


def test_the_filtered_total_counts_every_page_not_just_this_one(client, tasks_org):
    # The owner created 2 confidential tasks; a page of 1 must still report 2.
    response = client.get("/tasks", params={"created_by": "me", "limit": 1}, headers=headers(tasks_org["owner"]))
    assert len(response.json()["items"]) == 1
    assert response.json()["total"] == 2


def test_filters_combine(client, tasks_org):
    owner = tasks_org["owner"]
    assert titles(client, owner, created_by="me", assignee=tasks_org["m1"]["user_id"]) == ["confidential_assigned_to_m1"]
    assert titles(client, owner, created_by="me", assignee=tasks_org["m2"]["user_id"]) == []


def test_an_unknown_user_is_an_empty_list_and_a_malformed_one_is_a_422(client, tasks_org):
    owner = tasks_org["owner"]
    assert titles(client, owner, assignee=str(uuid.uuid4())) == []
    for params in ({"assignee": "someone"}, {"created_by": "1"}, {"status": "archived"}):
        assert client.get("/tasks", params=params, headers=headers(owner)).status_code == 422
