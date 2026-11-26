from app.models.membership import MembershipRole
from tests.helpers import join_as, register_and_login


def my_organizations(client, session):
    return client.get("/organizations", headers={"Authorization": f"Bearer {session['access']}"})


def test_a_user_lists_every_organization_they_belong_to_with_their_role(client):
    owner_b = register_and_login(client, email="b@example.com", org="Beta")
    me = join_as(client, owner_b, MembershipRole.member, email="me@example.com")  # my own org is "me@example.com org"
    register_and_login(client, email="c@example.com", org="Gamma")  # not mine

    response = my_organizations(client, me)

    assert response.status_code == 200
    assert [(o["name"], o["role"]) for o in response.json()] == [
        ("Beta", "member"),
        ("me@example.com org", "owner"),
    ]
    assert owner_b["org_id"] in {o["id"] for o in response.json()}


def test_it_needs_no_organization_header_but_needs_a_login(client):
    assert client.get("/organizations").status_code == 401
