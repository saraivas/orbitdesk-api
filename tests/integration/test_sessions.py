import threading
import time

import redis
from jose import jwt

from app.core.config import ALGORITHM, SECRET_KEY
from app.core.redis import get_redis
from app.core.sessions import (
    RotationStatus,
    SESSION_KEY,
    USER_SESSIONS_KEY,
    create_session,
    new_id,
    rotate_session,
)
from app.main import app
from tests.conftest import TEST_REDIS_URL
from tests.helpers import create_task, register_and_login


def claims(token):
    return jwt.get_unverified_claims(token)


def refresh(client, token):
    return client.post("/auth/refresh", json={"refresh_token": token})


# --- login creates a session -------------------------------------------------

def test_login_creates_a_session_in_redis_with_a_30_day_ttl(client, redis_client):
    s = register_and_login(client)
    sid = claims(s["access"])["sid"]

    assert claims(s["refresh"])["sid"] == sid
    assert redis_client.hget(SESSION_KEY.format(sid=sid), "user_id") == s["user_id"]
    ttl = redis_client.ttl(SESSION_KEY.format(sid=sid))
    assert 29 * 86400 < ttl <= 30 * 86400
    assert sid in redis_client.smembers(USER_SESSIONS_KEY.format(user_id=s["user_id"]))


def test_login_response_is_not_cacheable(client):
    register_and_login(client, email="nc@example.com")
    response = client.post("/auth/login", json={"email": "nc@example.com", "password": "senha123"})
    assert response.headers["cache-control"] == "no-store"


# --- the access token is checked against the session -------------------------

def test_access_token_works_while_the_session_exists(client):
    s = register_and_login(client)
    assert create_task(client, s).status_code == 201


def test_access_token_stops_working_when_the_session_is_deleted(client, redis_client):
    s = register_and_login(client)
    redis_client.delete(SESSION_KEY.format(sid=claims(s["access"])["sid"]))
    assert create_task(client, s).status_code == 401


def test_access_token_without_a_session_id_is_rejected(client):
    s = register_and_login(client)
    old_style = jwt.encode({"sub": s["user_id"], "exp": int(time.time()) + 600, "type": "access"},
                           SECRET_KEY, algorithm=ALGORITHM)
    assert create_task(client, s, access=old_style).status_code == 401


# --- refresh -----------------------------------------------------------------

def test_refresh_returns_a_new_pair_and_keeps_the_session(client):
    s = register_and_login(client)
    response = refresh(client, s["refresh"])

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert claims(body["refresh_token"])["jti"] != claims(s["refresh"])["jti"]
    assert claims(body["refresh_token"])["sid"] == claims(s["refresh"])["sid"]
    assert create_task(client, s, access=body["access_token"]).status_code == 201


def test_refresh_token_in_the_query_string_is_not_accepted(client):
    s = register_and_login(client)
    assert client.post(f"/auth/refresh?refresh_token={s['refresh']}").status_code == 422


def test_refresh_rejects_an_access_token_garbage_and_no_session_with_the_same_answer(client, redis_client):
    s = register_and_login(client)
    gone = register_and_login(client, email="gone@example.com")
    redis_client.delete(SESSION_KEY.format(sid=claims(gone["refresh"])["sid"]))

    answers = [refresh(client, t) for t in (s["access"], "not-a-jwt", gone["refresh"])]

    assert [a.status_code for a in answers] == [401, 401, 401]
    assert len({a.json()["detail"] for a in answers}) == 1


def test_reusing_a_refresh_token_revokes_the_whole_session(client):
    s = register_and_login(client)
    new = refresh(client, s["refresh"]).json()

    reuse = refresh(client, s["refresh"])  # the old token, again
    assert reuse.status_code == 401

    # the legitimate newer tokens died with the session
    assert refresh(client, new["refresh_token"]).status_code == 401
    assert create_task(client, s, access=new["access_token"]).status_code == 401


def test_refresh_does_not_extend_the_session(client, redis_client):
    s = register_and_login(client)
    key = SESSION_KEY.format(sid=claims(s["refresh"])["sid"])
    redis_client.expire(key, 1000)

    refresh(client, s["refresh"])

    assert redis_client.ttl(key) <= 1000


def test_refresh_token_never_outlives_its_session(client, redis_client):
    s = register_and_login(client)
    key = SESSION_KEY.format(sid=claims(s["refresh"])["sid"])
    end = int(time.time()) + 120
    redis_client.hset(key, "expires_at", end)

    new = refresh(client, s["refresh"]).json()

    assert claims(new["refresh_token"])["exp"] <= end


def test_refresh_fails_and_ends_the_session_if_the_user_no_longer_exists(client, db_session, redis_client):
    from app.models.membership import Membership
    from app.models.organization import Organization
    from app.models.user import User

    s = register_and_login(client)
    db_session.query(Membership).delete()
    db_session.query(Organization).delete()
    db_session.query(User).delete()
    db_session.commit()

    assert refresh(client, s["refresh"]).status_code == 401
    assert not redis_client.exists(SESSION_KEY.format(sid=claims(s["refresh"])["sid"]))


# --- logout ------------------------------------------------------------------

def login(client, email="owner@example.com"):
    tokens = client.post("/auth/login", json={"email": email, "password": "senha123"}).json()
    return tokens["access_token"], tokens["refresh_token"]


def auth(access):
    return {"Authorization": f"Bearer {access}"}


def test_logout_ends_only_the_session_it_was_called_with(client, redis_client):
    s = register_and_login(client)
    other_access, other_refresh = login(client)  # a second device

    assert client.post("/auth/logout", headers=auth(s["access"])).status_code == 204

    assert create_task(client, s).status_code == 401
    assert refresh(client, s["refresh"]).status_code == 401
    sid = claims(s["access"])["sid"]
    assert sid not in redis_client.smembers(USER_SESSIONS_KEY.format(user_id=s["user_id"]))
    assert create_task(client, s, access=other_access).status_code == 201
    assert refresh(client, other_refresh).status_code == 200


def test_logging_out_twice_is_refused_the_second_time(client):
    s = register_and_login(client)
    assert client.post("/auth/logout", headers=auth(s["access"])).status_code == 204
    assert client.post("/auth/logout", headers=auth(s["access"])).status_code == 401


def test_logout_all_ends_every_session_of_the_caller_and_nobody_elses(client, redis_client):
    a = register_and_login(client, email="a@example.com")
    a2_access, a2_refresh = login(client, email="a@example.com")
    b = register_and_login(client, email="b@example.com")

    assert client.post("/auth/logout-all", headers=auth(a["access"])).status_code == 204

    assert create_task(client, a).status_code == 401
    assert create_task(client, a, access=a2_access).status_code == 401
    assert refresh(client, a2_refresh).status_code == 401
    assert not redis_client.exists(USER_SESSIONS_KEY.format(user_id=a["user_id"]))
    assert create_task(client, b).status_code == 201


# --- atomic rotation ---------------------------------------------------------

def test_two_simultaneous_refreshes_with_the_same_token_cannot_both_win(redis_client):
    for _ in range(25):
        redis_client.flushdb()
        session = create_session(redis_client, "user-1")
        results = []
        barrier = threading.Barrier(2)

        def attempt():
            conn = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
            barrier.wait()
            results.append(rotate_session(conn, session.sid, "user-1", session.jti, new_id()).status)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        assert sorted(r.value for r in results) == [-1, 1]
        assert not redis_client.exists(SESSION_KEY.format(sid=session.sid))  # reuse ended it


def test_rotation_for_another_users_session_is_refused(redis_client):
    session = create_session(redis_client, "user-1")
    result = rotate_session(redis_client, session.sid, "user-2", session.jti, new_id())
    assert result.status is RotationStatus.MISSING
    assert redis_client.exists(SESSION_KEY.format(sid=session.sid))


# --- Redis down: authentication fails closed ---------------------------------

def test_login_refresh_and_protected_routes_answer_503_when_redis_is_down(client):
    s = register_and_login(client)
    down = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: down

    assert client.post("/auth/login", json={"email": "owner@example.com", "password": "senha123"}).status_code == 503
    assert refresh(client, s["refresh"]).status_code == 503
    assert create_task(client, s).status_code == 503
