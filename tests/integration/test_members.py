import threading
import uuid

import pytest

from app.models.audit_log import AuditLog
from app.models.membership import Membership, MembershipRole
from app.models.task_assignment import TaskAssignment
from sqlalchemy.exc import IntegrityError

from app.db.errors import violates
from app.routers.members import count_owners_for_update
from tests.conftest import TestingSessionLocal
from tests.helpers import create_task, headers, join_as, register_and_login


def add(client, actor, email, role="member"):
    return client.post("/members", json={"email": email, "role": role}, headers=headers(actor))


def set_role(client, actor, target, role):
    return client.patch(f"/members/{target['user_id']}", json={"role": role}, headers=headers(actor))


def remove(client, actor, target):
    return client.delete(f"/members/{target['user_id']}", headers=headers(actor))


@pytest.fixture
def org(client):
    owner = register_and_login(client, email="owner@example.com", org="A")
    return {
        "owner": owner,
        "admin": join_as(client, owner, MembershipRole.admin, email="admin@example.com"),
        "member": join_as(client, owner, MembershipRole.member, email="member@example.com"),
    }


# --- listing and adding -------------------------------------------------------

def test_any_member_lists_the_members_of_their_organization_only(client, org):
    register_and_login(client, email="b@example.com", org="B")

    response = client.get("/members", headers=headers(org["member"]))

    assert response.status_code == 200
    assert {(m["email"], m["role"]) for m in response.json()} == {
        ("owner@example.com", "owner"),
        ("admin@example.com", "admin"),
        ("member@example.com", "member"),
    }


def test_an_added_user_can_work_in_the_organization_at_once(client, org):
    new = register_and_login(client, email="new@example.com", org="Own")

    assert add(client, org["owner"], "new@example.com").status_code == 201
    # Auto-accept: no invitation step, the membership exists right away.
    assert create_task(client, {**new, "org_id": org["owner"]["org_id"]}).status_code == 201


def test_adding_an_unknown_email_or_an_existing_member_is_refused(client, org):
    assert add(client, org["owner"], "nobody@example.com").status_code == 404
    assert add(client, org["owner"], "member@example.com").status_code == 409


def test_only_the_membership_constraint_counts_as_already_a_member(db_session, org):
    """Real Postgres errors: a duplicate membership is one, a missing user is not."""
    org_id = uuid.UUID(org["owner"]["org_id"])

    def integrity_error(user_id):
        db_session.add(Membership(user_id=user_id, organization_id=org_id, role=MembershipRole.member))
        with pytest.raises(IntegrityError) as raised:
            db_session.flush()
        db_session.rollback()
        return raised.value

    assert violates(integrity_error(uuid.UUID(org["member"]["user_id"])), "uq_user_organization")
    # A foreign key failure is not a duplicate.
    assert not violates(integrity_error(uuid.uuid4()), "uq_user_organization")


@pytest.mark.parametrize(
    "actor, role, expected",
    [
        ("owner", "owner", 201),
        ("owner", "admin", 201),
        ("admin", "member", 201),
        ("admin", "admin", 403),  # nobody grants a role at or above their own, except the owner
        ("admin", "owner", 403),
        ("member", "member", 403),
    ],
)
def test_who_can_add_which_role(client, org, actor, role, expected):
    register_and_login(client, email="new@example.com", org="Own")

    assert add(client, org[actor], "new@example.com", role).status_code == expected


# --- changing roles -----------------------------------------------------------

def test_only_the_owner_changes_roles(client, org):
    assert set_role(client, org["admin"], org["member"], "admin").status_code == 403
    response = set_role(client, org["owner"], org["member"], "admin")

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_the_last_owner_cannot_be_demoted_but_one_of_two_can(client, org):
    assert set_role(client, org["owner"], org["owner"], "admin").status_code == 409

    set_role(client, org["owner"], org["admin"], "owner")

    assert set_role(client, org["owner"], org["owner"], "admin").status_code == 200


# --- removing and leaving -----------------------------------------------------

@pytest.mark.parametrize(
    "actor, target, expected",
    [
        ("owner", "admin", 204),
        ("owner", "member", 204),
        ("admin", "member", 204),
        ("admin", "owner", 403),
        ("member", "admin", 403),
    ],
)
def test_who_can_remove_whom(client, org, actor, target, expected):
    assert remove(client, org[actor], org[target]).status_code == expected


def test_a_second_admin_cannot_remove_another_admin(client, org):
    other_admin = join_as(client, org["owner"], MembershipRole.admin, email="admin2@example.com")

    assert remove(client, other_admin, org["admin"]).status_code == 403


def test_a_removed_member_loses_access_on_the_next_request(client, org):
    remove(client, org["owner"], org["member"])

    assert create_task(client, org["member"]).status_code == 403


def test_removing_a_member_deletes_their_assignments_in_that_organization_only(client, db_session, org):
    member_id = uuid.UUID(org["member"]["user_id"])
    other = register_and_login(client, email="b@example.com", org="B")
    add(client, other, "member@example.com")
    for owner in (org["owner"], other):
        task_id = create_task(client, owner, type="confidential").json()["id"]
        assigned = client.post(f"/tasks/{task_id}/assignees", json={"user_id": str(member_id)},
                               headers=headers(owner))
        assert assigned.status_code == 201

    assert remove(client, org["owner"], org["member"]).status_code == 204

    db_session.expire_all()
    # The assignment in A is gone; the one in B stays, since the member is still in B.
    assert db_session.query(TaskAssignment).filter_by(user_id=member_id).count() == 1


def test_a_member_can_leave(client, org):
    assert remove(client, org["member"], org["member"]).status_code == 204
    assert create_task(client, org["member"]).status_code == 403


def test_the_only_owner_cannot_leave_until_there_is_another_owner(client, org):
    assert remove(client, org["owner"], org["owner"]).status_code == 409

    set_role(client, org["owner"], org["admin"], "owner")

    assert remove(client, org["owner"], org["owner"]).status_code == 204


def test_someone_outside_the_organization_is_a_404(client, org):
    outsider = register_and_login(client, email="b@example.com", org="B")

    assert set_role(client, org["owner"], outsider, "admin").status_code == 404
    assert remove(client, org["owner"], outsider).status_code == 404


# --- audit --------------------------------------------------------------------

def test_member_changes_are_audited(client, db_session, org):
    db_session.query(AuditLog).delete()  # the fixture's own joins are audited too
    db_session.commit()

    set_role(client, org["owner"], org["member"], "admin")
    remove(client, org["owner"], org["member"])

    entries = [(e.action, e.metadata_) for e in db_session.query(AuditLog).order_by(AuditLog.created_at)]
    assert entries == [
        ("member.role_changed", {"from": "member", "to": "admin"}),
        ("member.removed", {"role": "admin"}),
    ]


# --- the last-owner check under concurrency -----------------------------------

def test_a_second_owner_check_waits_for_the_first_and_sees_its_change(client, org):
    """Two demotions at once must not leave the organization without an owner.

    Session 1 counts the owners with FOR UPDATE and demotes one of two, without
    committing. Session 2's count must wait for that lock, and after session 1
    commits it must see one owner, not two.
    """
    second = join_as(client, org["owner"], MembershipRole.owner, email="owner2@example.com")
    org_id = uuid.UUID(org["owner"]["org_id"])
    s1, s2 = TestingSessionLocal(), TestingSessionLocal()
    seen = {}
    try:
        assert count_owners_for_update(s1, org_id) == 2
        s1.query(Membership).filter_by(user_id=uuid.UUID(second["user_id"]), organization_id=org_id) \
            .update({"role": MembershipRole.admin})

        waiter = threading.Thread(target=lambda: seen.update(n=count_owners_for_update(s2, org_id)))
        waiter.start()
        waiter.join(timeout=1)
        assert waiter.is_alive(), "the second count did not wait for the first transaction's lock"

        s1.commit()
        waiter.join(timeout=5)
        assert seen["n"] == 1
    finally:
        s2.rollback()
        s1.close()
        s2.close()
