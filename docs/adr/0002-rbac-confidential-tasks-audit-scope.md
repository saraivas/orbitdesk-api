# 0002. RBAC with fixed roles, confidential task visibility, and state-change-only audit logging

## Status

Accepted

## Context

orbitdesk-api needs to answer three related but distinct questions:

1. What can a member do within an organization in general (create tasks,
   invite people, etc.)?
2. Who can see and edit a _specific_ task, given that some tasks are
   sensitive and shouldn't be visible to every member?
3. What level of activity needs to be recorded for accountability?

Two access control models were considered for question 1: RBAC (role-based,
a fixed enum of roles) and ABAC (attribute-based, permissions computed from
multiple runtime attributes). A dynamic, database-backed role/permission
system (separate `Role` and `Permission` tables, editable at runtime) was
also considered.

## Decision

**Role hierarchy (RBAC, fixed in code):** `owner > admin > member`.

- `owner`: full control over everything in the organization, always,
  including tasks created or assigned to others.
- `admin`: can invite/remove members, but has no special access to another
  user's confidential tasks beyond what task-level rules grant them.
- `member`: baseline participant.

Permissions are mapped in code (`app/core/permissions.py`) as a dictionary
of role → set of permission strings (e.g. `"task.create"`,
`"member.invite"`), not as a database table. This was a deliberate choice:
the role set is small, fixed, and not something individual organizations
need to customize — a dynamic role/permission system would add real
complexity (extra tables, joins on every permission check, no simple table
to audit visually) without a matching need. If customer-specific custom
roles ever become a real requirement, this is the point where migrating to
a database-backed model would be justified.

**Task-level visibility and editing (a small, deliberate use of
ABAC-style reasoning layered on top of RBAC):** general role does not
fully determine access to a specific task. Tasks have a `type`
(`standard` or `confidential`). Visibility and edit rights depend on the
combination of role, task type, task creator, and task assignment — not
role alone:

- `owner` sees and edits everything, unconditionally.
- `standard` tasks are visible to every member of the organization.
- `confidential` tasks are visible only to: the task's creator, users
  assigned to it, and the owner. Notably, `admin` has no automatic
  visibility into another admin's or member's confidential task — this
  intentionally differs from admin's broader organizational permissions
  (e.g. inviting members), reflecting a real-world case where project
  managers in the same organization may need confidentiality from each
  other.
- Editing follows the same access boundary as visibility: only the
  creator, an assigned user, or the owner can edit a task. A general
  `admin` role does not grant edit rights to a task the admin didn't
  create and isn't assigned to.
- Only `owner` and `admin` roles can create `confidential` tasks; `member`
  can only create `standard` tasks (enforced via a separate
  `task.create_confidential` permission).
- Assignment (adding/removing a user from a task) can only be performed by
  the task's creator or the owner — not by any admin, and not by other
  assignees.

**Audit logging scope:** `AuditLog` records state-changing actions only
(`task.created`, `task.updated`, `task.deleted`, `task.assigned`,
`task.unassigned`, `member.invited`, `member.removed`,
`member.role_changed`). Read access (`task.viewed`) is explicitly _not_
logged.

## Consequences

**Positive**

- Permission logic stays centralized and readable (`has_permission(role,
"task.delete")` reads as intent, not as a hardcoded role comparison
  repeated across routes).
- The confidential/standard split and creator/assignee-based access gives
  real, non-trivial access control to reason about and test — closer to
  how real multi-tenant products handle sensitive data than a flat
  "admin sees everything" model would.
- Keeping audit logging to state changes avoids a write on every read
  operation, and keeps `AuditLog` growth proportional to actual activity
  rather than to traffic. Access is already captured indirectly: knowing
  who was granted access (`task.assigned`) is what matters for
  accountability, not how many times they subsequently viewed it.

**Negative**

- Task-level access checks are more complex than a pure role check —
  every task read/write needs to evaluate creator, assignment, and type
  together, not just look up a role.
- If organizational needs ever require per-customer custom roles, the
  fixed-role design needs a real migration to a database-backed
  role/permission model, not just a code change.
- If a future requirement demands proof of who _viewed_ sensitive data
  (e.g. regulatory compliance), this design would need a new access-log
  mechanism added — it does not exist today, by design, given no such
  requirement exists yet.

## Future improvements

- If a role/permission system needs to become customer-configurable,
  introduce `Role` and `RolePermission` tables and migrate
  `ROLE_PERMISSIONS` from code into data, without changing how
  `has_permission` is called elsewhere.
- If read-level audit ever becomes necessary, add it as a separate,
  intentionally scoped mechanism (e.g. only for `confidential` tasks, not
  every read) rather than logging every GET request indiscriminately.
