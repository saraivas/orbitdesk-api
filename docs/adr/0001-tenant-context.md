# 0001. Tenant context resolved per-request via header, not embedded in JWT

## Context

Unlike tasklane-api, where a task belongs directly to a user, orbitdesk-api
introduces organizations: a user can belong to multiple organizations, and
tasks belong to an organization, not to a user directly. The system needs
to know, on every request, which organization the caller is currently
acting within.

Two approaches were considered:

1. Embed `organization_id` in the JWT at login time, fixed for the token's
   lifetime. Simpler to implement, but requires re-authentication (or
   multiple concurrent token pairs) to switch organizations.
2. Keep the JWT scoped to user identity only; resolve the active
   organization per request from a client-supplied header
   (`X-Organization-Id`), validated against a `Membership` table.

Option 2 was deliberately chosen over the simpler option 1, even though
it adds real complexity (an extra validation query per request), because
it reflects how real multi-tenant SaaS products actually need to behave
(a user in multiple organizations switching between them without
re-authenticating), and because building the more realistic, harder
version is more valuable for learning than defaulting to the easier path.

## Decision

Use approach 2. The JWT continues to carry only `sub` (user id), exactly as
in tasklane-api. Every request that needs organization context reads
`X-Organization-Id` from the request header and validates it against the
`Membership` table (user must have an active membership in that
organization) before proceeding.

## Consequences

**Positive**

- A user belonging to multiple organizations can switch between them
  without re-authenticating.
- Auth (JWT issuance/validation) stays exactly as validated in
  tasklane-api; no new complexity is introduced into the token lifecycle
  itself.
- Revoking a user's access to a specific organization takes effect
  immediately on the next request, without waiting for token expiry.

**Negative**

- Every organization-scoped request pays the cost of an extra query (or
  cache lookup) to validate membership, instead of reading it for free
  from an already-verified token.
- Requires a composite index on `Membership(user_id, organization_id)` to
  keep that per-request check fast.
- Clients must remember to send the header on every organization-scoped
  request; forgetting it is a client-side bug, not something the token
  itself prevents.

## Future improvements

If per-request membership lookups become a measurable performance cost,
caching the user's membership list (invalidated on membership change)
would remove most of the added query cost without reverting to embedding
tenant state in the token.
