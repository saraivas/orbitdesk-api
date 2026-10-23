import time
import uuid

from jose import jwt

from app.core.config import ALGORITHM, SECRET_KEY
from app.core.sessions import create_session
from app.core.security import create_access_token
from tests.helpers import create_task, headers, register_and_login


def test_a_malformed_organization_header_is_a_422_not_a_server_error(client):
    s = register_and_login(client)
    h = headers(s)
    h["X-Organization-Id"] = "not-a-uuid"

    response = client.post("/tasks", json={"title": "t"}, headers=h)

    assert response.status_code == 422


def test_a_missing_organization_header_is_a_422(client):
    s = register_and_login(client)
    h = headers(s)
    del h["X-Organization-Id"]

    assert client.post("/tasks", json={"title": "t"}, headers=h).status_code == 422


def test_an_unknown_organization_and_someone_elses_organization_get_the_same_403(client):
    a = register_and_login(client, email="a@example.com", org="A")
    b = register_and_login(client, email="b@example.com", org="B")

    someone_elses = headers(a)
    someone_elses["X-Organization-Id"] = b["org_id"]
    unknown = headers(a)
    unknown["X-Organization-Id"] = str(uuid.uuid4())

    r1 = client.post("/tasks", json={"title": "t"}, headers=someone_elses)
    r2 = client.post("/tasks", json={"title": "t"}, headers=unknown)

    assert (r1.status_code, r2.status_code) == (403, 403)
    assert r1.json() == r2.json()  # nothing reveals which organizations exist


def test_a_signed_token_whose_sub_is_not_a_uuid_is_a_401(client, redis_client):
    # The session exists and belongs to that "user", so only the sub check can stop it.
    s = register_and_login(client)
    session = create_session(redis_client, "not-a-uuid")
    forged = create_access_token("not-a-uuid", session.sid)

    assert create_task(client, s, access=forged).status_code == 401
