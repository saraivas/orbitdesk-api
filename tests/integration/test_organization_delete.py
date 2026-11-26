import uuid

from app.models.audit_log import AuditLog
from app.models.membership import MembershipRole
from app.routers.organizations import soft_delete_organization
from tests.conftest import TestingSessionLocal
from tests.helpers import create_task, headers, join_as, register_and_login


def delete_org(client, session, confirm_name):
    return client.request("DELETE", "/organization", json={"confirm_name": confirm_name}, headers=headers(session))


def test_the_owner_deletes_the_organization_and_every_route_then_treats_it_as_unknown(client):
    owner = register_and_login(client, email="owner@example.com", org="Acme")
    member = join_as(client, owner, MembershipRole.member, email="m@example.com")
    create_task(client, owner)

    assert delete_org(client, owner, "Acme").status_code == 204

    # Same 403 as an organization the caller never belonged to (ADR 0007).
    for session in (owner, member):
        assert client.get("/tasks", headers=headers(session)).status_code == 403
        assert client.get("/members", headers=headers(session)).status_code == 403
    unknown = {**owner, "org_id": str(uuid.uuid4())}
    assert client.get("/tasks", headers=headers(unknown)).json() == client.get("/tasks", headers=headers(owner)).json()


def test_a_deleted_organization_leaves_the_list_and_the_audit_entry_stays(client, db_session):
    owner = register_and_login(client, email="owner@example.com", org="Acme")

    assert delete_org(client, owner, "Acme").status_code == 204

    mine = client.get("/organizations", headers={"Authorization": f"Bearer {owner['access']}"})
    assert mine.json() == []
    entry = db_session.query(AuditLog).filter(AuditLog.action == "organization.deleted").one()
    assert str(entry.entity_id) == owner["org_id"]


def test_a_wrong_confirmation_name_is_a_422_and_deletes_nothing(client):
    owner = register_and_login(client, email="owner@example.com", org="Acme")

    assert delete_org(client, owner, "acme").status_code == 422
    assert client.get("/tasks", headers=headers(owner)).status_code == 200


def test_only_the_owner_may_delete_the_organization(client):
    owner = register_and_login(client, email="owner@example.com", org="Acme")
    admin = join_as(client, owner, MembershipRole.admin, email="a@example.com")

    assert delete_org(client, admin, "Acme").status_code == 403
    assert client.get("/tasks", headers=headers(owner)).status_code == 200


def test_deleting_an_already_deleted_organization_reports_nothing_deleted(client):
    """Two deletes that both passed the membership check: only the first one counts."""
    owner = register_and_login(client, email="owner@example.com", org="Acme")
    org_id = uuid.UUID(owner["org_id"])
    db = TestingSessionLocal()
    try:
        assert soft_delete_organization(db, org_id)
        assert not soft_delete_organization(db, org_id)
    finally:
        db.close()
