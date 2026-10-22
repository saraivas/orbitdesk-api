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
- `app/routers/auth.py`, `app/routers/tasks.py` hold the endpoints.
- `app/deps.py` has `get_current_user`, `get_current_membership` (reads the
  `X-Organization-Id` header, see ADR 0001) and `require_permission`.
- `app/core/permissions.py` maps roles to permission strings (ADR 0002).
- `app/core/security.py` has password hashing and JWT creation and decoding.
- `app/core/config.py` reads the environment.
- `app/core/redis.py` builds the Redis client (`get_redis` dependency).
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
refresh, the membership and permission checks, and `POST /tasks`. A Redis
client, its docker-compose and CI services and the test fixtures also exist,
but nothing in the application reads or writes Redis yet.

Not implemented yet, so it must not be described as existing: reading,
updating or deleting tasks, task assignment, audit log writes (the model
exists, nothing writes to it), a README, sessions and token revocation (ADR
0003 is only proposed), rate limiting, caching, background jobs and
deployment.

## Known limitations

- `POST /auth/refresh` takes the token as a query parameter, does not check
  that the user still exists and does not issue a new refresh token.
- An `X-Organization-Id` that is not a UUID causes a server error.
- The Docker image runs as root and does not run migrations on start.
