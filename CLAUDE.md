# CLAUDE.md

Context for AI assistants (and humans) working in this repository.

## What this is

`orbitdesk-api` is Project 2 of a public study series, after
[tasklane-api](https://github.com/saraivas/tasklane-api): a multi-tenant task
workspace API (FastAPI, SQLAlchemy 2, PostgreSQL, JWT implemented by hand).
It is backend only. It is a portfolio project, so what the README, the ADRs
and the diagrams say must be true. The owner reviews and merges every pull
request.

## The rule that matters most

**Documentation, diagrams and public text describe only what is implemented
and verified in the code.** Nothing is embellished or "planned" inside the
description of current behaviour.

- If the docs and the code disagree, say so. Then either fix the code (with a
  test and an ADR) or fix the docs, and state which one you chose and why.
- Do not claim a number, a test result, a performance gain or a deployment you
  did not measure or check.
- Planned work goes under "Known limitations" or an ADR's "Future
  improvements", never in the description of what exists.
- This is a public study project. Do not mention employers, clients or
  internal projects.

## Commands

```bash
cp .env.example .env
docker compose up -d db redis                                 # Postgres on :5433, Redis on :6380
docker compose exec db createdb -U orbitdesk orbitdesk_test   # once
alembic upgrade head                                          # dev database
uvicorn app.main:app --reload
pytest                                                        # uses TEST_DATABASE_URL and TEST_REDIS_URL
```

Test results for a pull request come from the `test` check of the CI
workflow (`.github/workflows/ci.yml`), which runs `pytest` against real
Postgres and Redis. The `@claude` review job has no database and cannot run
the suite: read that check instead of treating the results as unverified.

**Never point `TEST_DATABASE_URL` at a database you care about.** The test
fixtures create and drop every table on each test. `tests/conftest.py` refuses
to run unless the database name ends with `_test`. `DATABASE_URL` is the
application's database and the tests do not use it.

The same goes for Redis: the `redis_client` fixture flushes its whole database
before and after each test, so `TEST_REDIS_URL` must use a database number
other than 0 (the default is 15), and `tests/conftest.py` refuses to run
otherwise.

## Layout

- `app/main.py` creates the app and includes the routers.
- `app/routers/auth.py`, `app/routers/tasks.py`, `app/routers/members.py`,
  `app/routers/organizations.py` hold the endpoints.
- `app/deps.py` has `get_current_user`, `get_current_membership` (reads the
  `X-Organization-Id` header, see ADR 0001) and `require_permission`.
- `app/core/permissions.py` maps roles to permission strings (ADR 0002).
- `app/core/security.py` has password hashing and JWT creation and decoding.
- `app/core/config.py` reads the environment.
- `app/core/redis.py` builds the Redis client (`get_redis` dependency).
- `app/core/sessions.py` is the Redis session store (ADR 0003): create, rotate
  (atomic Lua script), check, revoke.
- `app/core/audit.py` adds audit entries to the caller's transaction
  (ADR 0002); it never commits.
- `app/models/`, `app/schemas/` hold SQLAlchemy models and Pydantic schemas.
- `alembic/versions/` holds migrations. `docs/adr/` holds the decisions.
- `tests/unit/` and `tests/integration/` (FastAPI `TestClient`).

## Multi-tenancy rules

- The organization of a request comes from the validated membership, never
  from the request body.
- Every query on tenant data filters by the membership's `organization_id`.
- Confidential tasks must never be returned, counted or cached outside their
  visibility rules (ADR 0002). Treat a leak between organizations as the worst
  kind of bug and cover it with a test.

## Conventions

- Follow the style of the file you are editing (indentation differs between
  files; `app/core/security.py` uses 2 spaces).
- Every behaviour change comes with tests. Check that a new test can fail:
  break the code on purpose and confirm the test catches it.
- Architecture decisions are ADRs in `docs/adr/`, numbered in order. Do not
  rewrite an old ADR. When it turns out to be wrong or outdated, add an
  `Update` note under its Status, keep the original text, and write a new
  ADR.
- A change that alters a flow updates the diagrams in `README.md` in the same
  pull request. Check Mermaid syntax before committing.
- Commit messages are in English, in the `feat:`, `fix:`, `docs:`, `test:`,
  `ci:` style, and explain why, not only what.
- Work on a branch and open a pull request. Do not push to `main`.
- No secrets in the repository. `.env` is ignored. `.env.example` has only
  placeholders.

## Current state

Implemented: registration (user, organization and owner membership), login,
the membership and permission checks, and `POST /tasks`. Login creates a
session in Redis; access tokens are checked against it on every request;
`POST /auth/refresh` takes the token in the JSON body, rotates it atomically,
detects reuse (which ends the session) and never outlives the 30-day session.
`POST /auth/logout` ends the caller's session and `POST /auth/logout-all`
ends all of the caller's sessions. Authentication answers `503` when Redis is
unavailable. An `X-Organization-Id` that is not a UUID is a `422`, and an
access token whose `sub` is not a UUID is a `401`. `POST /tasks` writes a
`task.created` audit entry in the same transaction as the task, through
`record_audit` in `app/core/audit.py` (it adds, never commits); the entry
keeps the task type, never the title. `GET /tasks` (with `limit`/`offset` and
a `total`) and `GET /tasks/{id}` return only the tasks the caller may see:
the rule is SQL in `visible_tasks`, shared by list, total and detail, and a
hidden task is a `404` like a missing one (ADR 0004). `GET /tasks` also
filters by `status`, `assignee` and `created_by` (a UUID or `me`); the filters
only narrow `visible_tasks`, the `total` counts filtered tasks, and an unknown
user is an empty list. `ix_tasks_org_created` and `ix_tasks_org_status_created`
serve the list order and the status filter (ADR 0008). `/members` lists,
adds (auto-accept, existing accounts only), changes roles and removes
members, and lets a member leave; an admin manages only `member`, and the
last owner can never be demoted or removed (`SELECT ... FOR UPDATE`, ADR
0005). Removing a member deletes their assignments in that organization.
`PATCH /tasks/{id}` (title, description, status; omitted fields unchanged) and
`DELETE /tasks/{id}` (hard delete, with its assignments) check visibility
first (`404`), then edit rights: owner, creator or assignee (`403`); deleting
also needs `task.delete`. A `PATCH` with an unknown or read-only field is a
`422`. A second concurrent `DELETE` of the same task is a `404` and writes no
second `task.deleted`. `task.updated` records changed field names, never
values (ADR 0006). `/tasks/{id}/assignees` lists (whoever sees the task),
assigns and unassigns (only the creator or the owner, ADR 0002); only members
of the same organization can be assigned, a duplicate is a `409` from
`uq_task_user_assignment`, and `task.assigned`/`task.unassigned` are audited.
`app/db/errors.py` (`violates`) turns a named constraint into a `409`.
`GET /organizations` lists the caller's organizations with their role in
each; it needs a login but no `X-Organization-Id`. `DELETE /organization`
(owner only, `organization.delete`) soft-deletes the request's organization
when `confirm_name` repeats its name exactly (else `422`): it sets
`deleted_at`, keeps every row and writes `organization.deleted`.
`get_current_membership` ignores deleted organizations, so every scoped route
answers the same `403` as for an unknown one, and `GET /organizations` leaves
them out (ADR 0007).

Not implemented yet, so it must not be described as existing: pending
invitations, invitation emails, restoring or hard-deleting an organization,
a README, rate limiting, caching, background jobs and deployment.

## Known limitations

- If Redis restarts without persistence, every session is lost (ADR 0003).
- A client that sends the same refresh request twice at once loses its
  session, because the second one looks like reuse.
- The Docker image runs as root and does not run migrations on start.
- The audit log has no visibility rules. An entry stores the task id and
  `type: "confidential"`, so it reveals that a confidential task exists.
  Nothing reads `AuditLog` today; any endpoint that does must apply the
  confidential-task rules of ADR 0002 first.
- Task visibility is enforced in application code only (ADR 0004). Any new
  query on `tasks` must start from `visible_tasks`, or it bypasses the rule.
- Migrations build indexes without `CONCURRENTLY`, so they block writes to
  the table while they run (ADR 0008). Fine with no deployment; a large live
  table would need `CONCURRENTLY` outside a transaction.
- A deleted organization is hidden only by `get_current_membership` and the
  filter in `GET /organizations` (ADR 0007). A new query that reads
  `organizations` or tenant data without that dependency must filter
  `deleted_at`. Deleted data is never erased, so an erasure request
  (LGPD/GDPR) cannot be met yet.
- Adding a member with an email that has no account is a `404`, so anyone can
  learn whether an email is registered (ADR 0005). Pending invitations would
  close this.
