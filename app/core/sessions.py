"""Server-side sessions in Redis (ADR 0003).

Keys:
  orbitdesk:v1:session:{sid}          hash: user_id, jti, expires_at (TTL = session lifetime)
  orbitdesk:v1:user:{user_id}:sessions  set of that user's sids
"""
import enum
import secrets
import time
from dataclasses import dataclass

import redis

from app.core.config import SESSION_MAX_LIFETIME_DAYS

SESSION_KEY = "orbitdesk:v1:session:{sid}"
USER_SESSIONS_KEY = "orbitdesk:v1:user:{user_id}:sessions"

# Compare-and-rotate in one atomic step. Returns {status, expires_at}:
#   1  the jti matched: it was replaced by the new one
#   0  no such session (or it belongs to someone else)
#  -1  the jti did not match: the token was already used, so the session is deleted
_ROTATE_SCRIPT = """
local user_id = redis.call('HGET', KEYS[1], 'user_id')
if not user_id or user_id ~= ARGV[3] then return {0, 0} end
local current = redis.call('HGET', KEYS[1], 'jti')
if current ~= ARGV[1] then
  redis.call('DEL', KEYS[1])
  redis.call('SREM', KEYS[2], ARGV[4])
  return {-1, 0}
end
redis.call('HSET', KEYS[1], 'jti', ARGV[2])
return {1, tonumber(redis.call('HGET', KEYS[1], 'expires_at'))}
"""


class RotationStatus(enum.Enum):
    ROTATED = 1
    MISSING = 0
    REUSED = -1


@dataclass
class Session:
    sid: str
    jti: str
    expires_at: int


@dataclass
class Rotation:
    status: RotationStatus
    expires_at: int = 0


def new_id() -> str:
    return secrets.token_urlsafe(16)


def create_session(r: redis.Redis, user_id: str) -> Session:
    ttl = SESSION_MAX_LIFETIME_DAYS * 86400
    session = Session(sid=new_id(), jti=new_id(), expires_at=int(time.time()) + ttl)
    key = SESSION_KEY.format(sid=session.sid)
    user_key = USER_SESSIONS_KEY.format(user_id=user_id)
    pipe = r.pipeline()
    pipe.hset(key, mapping={"user_id": user_id, "jti": session.jti, "expires_at": session.expires_at})
    pipe.expire(key, ttl)  # set once; rotation never extends it
    pipe.sadd(user_key, session.sid)
    pipe.expire(user_key, ttl)
    pipe.execute()
    return session


def rotate_session(r: redis.Redis, sid: str, user_id: str, jti: str, new_jti: str) -> Rotation:
    status, expires_at = r.eval(
        _ROTATE_SCRIPT,
        2,
        SESSION_KEY.format(sid=sid),
        USER_SESSIONS_KEY.format(user_id=user_id),
        jti,
        new_jti,
        user_id,
        sid,
    )
    return Rotation(RotationStatus(status), int(expires_at))


def is_session_active(r: redis.Redis, sid: str, user_id: str) -> bool:
    return r.hget(SESSION_KEY.format(sid=sid), "user_id") == user_id


def revoke_session(r: redis.Redis, sid: str, user_id: str) -> None:
    pipe = r.pipeline()
    pipe.delete(SESSION_KEY.format(sid=sid))
    pipe.srem(USER_SESSIONS_KEY.format(user_id=user_id), sid)
    pipe.execute()


def revoke_all_sessions(r: redis.Redis, user_id: str) -> None:
    user_key = USER_SESSIONS_KEY.format(user_id=user_id)
    pipe = r.pipeline()
    for sid in r.smembers(user_key):
        pipe.delete(SESSION_KEY.format(sid=sid))
    pipe.delete(user_key)
    pipe.execute()
