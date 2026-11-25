# 0005. Membership management: who grants which role, and the last owner

## Status

Accepted

## Context

ADR 0002 fixed the roles and their permissions (`member.invite`,
`member.remove`, `member.update_role`) but there was no way to use them: the
only membership in an organization was the owner created at registration.
Managing members raises questions the permission strings do not answer:

1. Can an admin grant a role at or above their own?
2. What stops an organization from ending up with no owner?
3. What happens to a removed member's access and assignments?
4. What does adding an email that has no account reveal?

## Decision

**Endpoints.** `GET /members` (any member), `POST /members` with
`{email, role}` (`member.invite`), `PATCH /members/{user_id}` with `{role}`
(`member.update_role`, owner only) and `DELETE /members/{user_id}`
(`member.remove`, or anyone removing themselves to leave).

**Adding is auto-accept.** `POST /members` creates the membership at once for
a user who already has an account. There is no invitation step and no email.

**Who manages which role.** The owner manages every role. An admin adds and
removes only `member`; adding or removing an admin or an owner, and changing
any role, is the owner's. Nobody grants a role above their own.

**There is always at least one owner.** Demoting or removing an owner,
including an owner leaving, is refused with `409` if they are the last one.
The check counts the organization's owners with `SELECT ... FOR UPDATE`: two
requests that each demote one of the last two owners would otherwise both
count two and both pass. With the lock, the second waits for the first to
commit, counts again and sees one. An owner who wants to leave promotes
someone to owner first, then leaves; no extra operation is needed.

**Removing a member** deletes their task assignments in that organization in
the same transaction. Kept, they would give back access to confidential tasks
if the user were added again. Tasks they created stay. Access ends on the
next request, because the membership is checked on every request (ADR 0001);
sessions are not touched.

**Audit.** `member.invited` (with the role), `member.role_changed` (from and
to) and `member.removed` (with the role) are written through `record_audit`
in the same transaction as the change (ADR 0002).

## Consequences

**Positive**

- Roles can be used through the API, and tests no longer insert memberships
  directly.
- An organization cannot be left without an owner, also under concurrent
  requests.
- A removed member keeps no path back to confidential tasks.

**Negative**

- **User enumeration.** Adding an email without an account is a `404`, so
  anyone who registers (and becomes owner of their own organization) can
  learn whether an email has an account. This is a known limitation until
  pending invitations exist (see below).
- The owner check locks the organization's owner rows for the rest of the
  transaction, so concurrent role changes in one organization run one after
  another.
- An owner cannot delete the organization yet, so the only way out for a sole
  owner is to promote someone first.

## Future improvements

- **Pending invitations:** answer the same whether the email has an account
  or not, keep the invitation, and turn it into a membership when that email
  registers. This closes the enumeration above.
- **Deleting an organization** (owner only, confirmed by name), as a soft
  delete that keeps the audit log, in its own ADR.
- Invitation emails, sent from a background worker.
