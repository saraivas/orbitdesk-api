# 0008. Task list filters: narrowing visible_tasks, and indexes chosen by measurement

## Status

Accepted

## Context

`GET /tasks` returned every task the caller may see, page by page, with no
way to ask for "my tasks" or "everything in progress". Filters raise two
questions. The first is whether a filter can widen what the caller sees, for
example by filtering on another user's assignments. The second is what to
answer for a user id that is not a member. The list also orders by
`created_at` within one organization, and the only index on `tasks` was
`organization_id`. To return a page, Postgres read every task of the
organization and then sorted them.

## Decision

**Filters only narrow `visible_tasks`.** `status`, `assignee` and
`created_by` are added as conditions to the query that `visible_tasks`
returns (ADR 0004). Filtering by another user's assignments therefore cannot
show a task the caller may not see, and `total` counts the filtered tasks
through the same query. `assignee` and `created_by` accept a UUID or `me`.

**An unknown user is an empty list.** A user id that is not a member of the
organization, or that does not exist, gives `[]`, not a `404`. A `404` would
tell the caller whether that person belongs to the organization. A malformed
value is a `422`.

**Indexes chosen by measurement.** The indexes were chosen after running
`EXPLAIN ANALYZE` on a throwaway database with 200,000 tasks (20
organizations, run as a `member`):

- `ix_tasks_org_created (organization_id, created_at)` serves the unfiltered
  list. A page went from a bitmap scan over 9,234 rows, about 2.4 ms, to an
  index scan reading 51 rows, about 0.33 ms.
- `ix_tasks_org_status_created (organization_id, status, created_at)` serves
  the status filter. A page went from 3,042 rows read, about 1.5 ms, to 51
  rows, about 0.32 ms.
- `ix_tasks_organization_id` is dropped, because `ix_tasks_org_created` starts
  with the same column.

These are single local runs. At 10,000 tasks per organization every query
took under 4 ms with or without the indexes. The reason for the indexes is
that the rows read no longer grow with the organization. Speed at today's
size was not the reason.

## Consequences

**Positive**

- A client can build "my tasks" and per-status views without leaking hidden
  tasks.
- A page of the list or of a status filter reads one page of index entries.

**Negative**

- The two indexes cost about 18 MB per 200,000 tasks, and every write to
  `tasks` updates both.
- The `assignee` filter still reads the caller's assignments and then the
  tasks; its plan did not change and was not tuned.
- `OFFSET` pagination still reads and discards every row before the
  requested page. The indexes fix the order, not the offset. A cursor
  (`created_at`, `id`) would fix it if a large offset ever becomes a
  measured problem.
- The migration builds the indexes without `CONCURRENTLY`, so writes wait
  while they are built. This is acceptable with no deployment.
