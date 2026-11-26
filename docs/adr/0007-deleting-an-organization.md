# 0007. Deleting an organization: a soft delete hidden at the membership check

## Status

Accepted

**Update:** the "Concurrent deletes" paragraph describes how Postgres handles
two deletes at once. The test only covers the `deleted_at IS NULL` guard, by
running two soft deletes one after the other; no test runs two concurrent
requests.

## Context

An owner who wants to leave can promote another member to owner and then
leave (ADR 0005). An owner who wants the organization gone had no way to do
it. Deleting an organization touches everything that points to it: tasks,
assignments, memberships and the audit log. ADR 0006 already said this
deletion would be a soft delete, so that the audit log survives. Three more
answers were needed: who may delete, how an accidental delete is avoided, and
how every query learns that the organization is gone.

## Decision

**Soft delete.** `organizations.deleted_at` is set and every row is kept:
tasks, assignments, memberships and audit entries. The audit log exists to
outlive the actions it records, and a hard delete would have to remove it or
break its foreign key.

**Hidden in one place.** Every organization-scoped route depends on
`get_current_membership` (ADR 0001). It now ignores memberships of deleted
organizations, so a request with a deleted organization's id gets the same
`403` as an organization the caller never belonged to. The response does not
reveal that it existed. Like `visible_tasks` (ADR 0004), the rule is in one
place that everything passes through, instead of a `deleted_at IS NULL`
filter in every query. `GET /organizations` reads `organizations` without
going through that check, so it filters deleted organizations itself.

**Who and how.** `DELETE /organization` deletes the organization of the
request (`X-Organization-Id`). It needs `organization.delete`, which only the
owner has (ADR 0002). The body must repeat the organization's name in
`confirm_name`, so a wrong click or script cannot delete it; a name that does
not match exactly is a `422`. The deletion writes an `organization.deleted`
audit entry in the same transaction.

**Concurrent deletes.** Two deletes can both pass the membership check before
either commits. The `UPDATE` only matches a row whose `deleted_at` is still
null, so the second one waits for the first's row lock, then matches nothing,
and answers the same `403` without writing a second audit entry.

## Consequences

**Positive**

- One filter hides all of a deleted organization's data from every route.
- The audit log, including the deletion itself, is kept.
- A restore would only have to clear `deleted_at`.

**Negative**

- Nothing is ever removed, so this does not satisfy a request to erase data
  (LGPD/GDPR). That would need a hard delete or anonymization later.
- There is no restore endpoint.
- Any new query that reads `organizations` or tenant data without going
  through `get_current_membership` must filter `deleted_at` itself.
- Members of a deleted organization keep their accounts and sessions; they
  only lose access to that organization.
