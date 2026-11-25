# 0006. Editing and deleting tasks: 403 after visibility, and a hard delete

## Status

Accepted

## Context

ADR 0002 says who may edit a task: its creator, an assigned user or the
owner, and that being an admin does not grant editing. That boundary is
narrower than visibility: every member sees a standard task, but most of
them may not change it. ADR 0004 made a task the caller cannot see a `404`.
Editing and deleting need three more answers: what a caller gets for a task
they can see but not change, what a `PATCH` changes, and whether a deleted
task is kept.

## Decision

**Visibility first, then edit rights.** `PATCH /tasks/{id}` and
`DELETE /tasks/{id}` first look the task up through `visible_tasks`. A task
the caller cannot see is a `404`, the same as a missing one (ADR 0004). Only
then are edit rights checked (owner, creator or assignee), and failing them is
a `403`. A `403` here reveals nothing, because the caller can already see the
task. Checking edit rights first would turn a hidden confidential task into a
`403` and give its existence away.

**Who deletes.** Deleting needs the `task.delete` permission (owner and
admin) and the same edit boundary, so an admin deletes only tasks they created
or are assigned to, and the owner deletes any task.

**A `PATCH` changes only what is sent.** `title`, `description` and `status`
can be changed. A field left out stays as it is; `description: null` clears
the description; `title: null` and `status: null` are a `422`, since those
columns are required. The task `type` cannot be changed: switching between
standard and confidential changes who can see the task, which is a different
operation from editing it.

**Audit.** `task.updated` records the names of the changed fields, not their
values, because a title or description may be confidential and the audit log
has no visibility rules. A `PATCH` that changes nothing writes no entry.
`task.deleted` records the task type.

**Hard delete.** A deleted task and its assignments are removed in one
transaction. Unlike the organization (whose deletion will be a soft delete so
the audit log survives), the audit log has no foreign key to tasks, so the
`task.deleted` entry stays. A soft delete would make every query, including
`visible_tasks`, filter out deleted rows, and missing that filter once would
show deleted tasks.

## Consequences

**Positive**

- A hidden task stays hidden through editing and deleting, not only reading.
- Clients can clear the description without resending the whole task.
- The audit shows who changed or deleted what without copying its content.

**Negative**

- A deleted task cannot be restored; only the audit entry remains.
- Deleting a second time is a `404`. The state is the same either way, so
  `DELETE` stays idempotent, but clients see a different status code.
- Checking edit rights costs one extra query for the assignment.
