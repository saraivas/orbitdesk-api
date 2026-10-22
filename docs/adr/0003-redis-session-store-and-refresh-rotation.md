# 0003. Server-side sessions in Redis, with rotating refresh tokens

## Status

Accepted. Sessions, refresh rotation and fail-closed behaviour are
implemented; logout and the header and `sub` validation listed under "Also in
this change" are not yet.

## Context

Today `POST /auth/refresh` takes the refresh token as a query parameter (so it
ends up in URLs and logs), does not check that the user still exists, does not
return a new refresh token, and a refresh token stays valid for its full 7
days no matter what. There is no way to end a session: logging out is the
client forgetting the token.

[tasklane-api ADR 0010](https://github.com/saraivas/tasklane-api/blob/main/docs/adr/0010-refresh-token-rotation-and-session-limit.md)
fixed the first problems without server state and listed what it could not
do: refresh tokens are not single-use and a session cannot be revoked. This
project is meant to cover that gap, so it keeps session state on the server.

Sessions could also live in PostgreSQL. Redis is chosen because keys can
expire by themselves (TTL) and because the project is also a study of how to
use and operate Redis. It is not chosen for performance, and no performance
claim is made here.

## Decision

**Sessions.** Logging in creates a session identified by a random `sid`,
stored in Redis:

- `orbitdesk:v1:session:{sid}` is a hash with the user id, the `jti` of the
  refresh token currently allowed and the session end (`expires_at`, epoch
  seconds, used to cap refresh tokens). It has a TTL of 30 days, set once at login
  and never extended, so a session ends 30 days after login.
- `orbitdesk:v1:user:{user_id}:sessions` is a set of that user's `sid`s, used
  to end all of them.

**Tokens.** Both tokens carry `sid`. The refresh token also carries a `jti`
(random, one per refresh token) and expires 7 days after it was issued, or when
the session ends, whichever comes first.

**Refresh.** The refresh token is sent in the JSON body, never in the URL.
A Lua script runs in Redis, so the check and the change are one atomic step:

1. session missing: reject.
2. `jti` equals the stored one: store the new `jti` and issue a new pair.
3. `jti` differs: the token was already used. Delete the whole session and
   reject. This is reuse detection: if a stolen refresh token is used, either
   the thief or the owner is revoked on the next attempt.

Every rejection is the same `401` with the same message, and responses that
carry tokens send `Cache-Control: no-store`. The user is loaded from the
database and must still exist.

**Logout.** `POST /auth/logout` deletes the caller's session.
`POST /auth/logout-all` deletes every session of the caller.

**Access tokens are checked against the session.** `get_current_user` checks
that the session in the token still exists, so logging out or revoking takes
effect on the next request, not when the access token expires. This costs one
Redis read per authenticated request.

**When Redis is unavailable, authentication fails closed.** Without Redis the
service cannot prove a session is valid, so protected endpoints, login and
refresh answer `503`. This is the opposite of what a pure cache should do (fall
back to the database); the membership cache planned later will fail open, and
the difference is intentional.

**Also in this change** (same area, same reasoning):

- `X-Organization-Id` is typed as a UUID: a malformed value is a `422`
  instead of a server error. A valid UUID the user is not a member of is
  still `403`, and it is the same `403` for an organization that does not
  exist.
- A token whose `sub` is not a UUID is a `401`.

## Consequences

**Positive**

- Sessions can be revoked, single logout and logout-all work, and reuse of a
  refresh token is detected.
- The refresh token no longer appears in URLs.
- The absolute session limit is enforced by Redis, not only by a claim.

**Negative**

- Authentication now depends on Redis being up (see above).
- One extra Redis read on every authenticated request.
- If Redis restarts without persistence, every user is logged out. This is
  accepted for now.
- A client that sends the same refresh request twice at once will lose its
  session: the second request looks like reuse. This is the usual cost of
  reuse detection.
- The per-user set can keep the `sid` of a session that already expired by
  TTL until the user's next logout-all, which cleans it. It does not affect
  validity, only the size of the set.
- Tokens issued before this change have no `sid` and stop working. There is
  no deployment yet, so nobody is affected.

## Future improvements

- Cache memberships in Redis with explicit invalidation (ADR 0001's future
  improvement), failing open.
- Rate limiting on login and refresh.
