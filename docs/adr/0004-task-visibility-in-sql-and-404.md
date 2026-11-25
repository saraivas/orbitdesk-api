# 0004. Task visibility is enforced in SQL, and a hidden task is a 404

## Status

Accepted

## Context

ADR 0002 decided who may see a task: the owner sees every task in the
organization; everyone else sees standard tasks, the tasks they created and
the tasks assigned to them. It did not decide where that rule runs or what a
caller gets for a task they may not see.

Reading tasks (`GET /tasks`, `GET /tasks/{id}`) needs both answers. Two
options were considered for where the rule runs:

1. Load the organization's tasks and filter them in Python.
2. Put the rule in the SQL query, so the database returns only visible tasks.

Option 1 breaks pagination (`LIMIT` cuts before the filter, so a page can come
back short), makes any count include hidden tasks unless it repeats the
filter, loads rows only to discard them, and needs every new endpoint to
remember to call the filter.

## Decision

**The rule is SQL, in one place.** `visible_tasks` in `app/routers/tasks.py`
builds the query: it always filters by the membership's organization and, for
anyone but the owner, adds `type = standard OR created_by = me OR EXISTS
(assignment to me)`. The list, its total and the detail all start from this
query, so they cannot disagree.

`EXISTS` is used instead of a `JOIN` on assignments, because a `JOIN` returns
a task once per assignee, which repeats it in the list and inflates the
total.

**A task the caller may not see is a `404`,** with the same body as a task
that does not exist or belongs to another organization. A `403` would confirm
that the task exists. This is the same reasoning as the identical `403` for an
unknown organization and someone else's organization (ADR 0003).

**The list returns a total** of the tasks the caller may see, counted from the
same query before the page is applied. It reveals nothing beyond what the
caller can already list.

## Consequences

**Positive**

- One rule for list, total and detail; a test of the list also guards the
  detail.
- Pagination and the total are correct, because filtering happens before
  `LIMIT` and `count`.
- Nothing in a response tells a caller that a hidden task exists.

**Negative**

- The rule lives in application code. A future query on `tasks` that does
  not start from `visible_tasks` would bypass it; only review and tests catch
  that.
- Listing costs two queries (the page and the total).
- `offset` pagination gets slower as the offset grows, since the database
  reads and discards the skipped rows. No measurement has been made.

## Future improvements

- PostgreSQL Row Level Security as defence in depth, so the database itself
  refuses rows a query forgot to filter. It needs the user and organization
  set on each connection, which has to be handled carefully with a
  connection pool.
- Keyset (cursor) pagination if large offsets become a measured problem.
