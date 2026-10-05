# Invite-based registration — design

2026-10-05 · Design approved in chat by the user · Spec awaiting user review · Post-roadmap feature (Phase 21)

## Intent

A person should be able to register **their own credentials** (password and one-time code) and join an organization. **Access is never self-granted.** Credentials belong to the identity provider; the role and organization come only from an invite created by an org admin. Privileged invites also need an independent approver.

User decisions:
- Access model: invite link.
- Privileged roles (`org_admin`, `approver`, `operator`): a second person must approve.
- Delivery: the link is shown once and copied by the admin. Email sending stays PLANNED.
- Credentials are created on the IdP's own registration page (approach A). The app never sees passwords and holds no IdP admin credentials.

Success criteria:
1. An invited person opens the link, registers in Keycloak, sets up TOTP and lands in the app with exactly the invited role.
2. Every abuse case in "Negative tests" is refused and audited.
3. Existing login, tenant isolation and authorization matrix tests still pass.

## Flow

```
admin ──POST invites──► invite (ACTIVE | PENDING_APPROVAL) ──link shown once──► admin copies
approver ──POST invites/{id}/decision (privileged only, recent MFA, ≠ inviter)──► ACTIVE
invitee ──GET /invite/{token}──► landing page ──"Create account"──► GET /api/v1/auth/register?invite=…
   └► login_attempts row (+ invite_hash) ──► Keycloak /registrations (PKCE, state, nonce)
       └► Keycloak: choose password, CONFIGURE_TOTP required action
           └► /api/v1/auth/callback ──► redeem_invite(...) in one transaction ──► session ──► /
```

## Data

Migration `023_invites.sql`:

- `invites`:
  - `id`, `organization_id` (FK), `email_normalized` (lower-case, trimmed)
  - `roles text[]`: exactly one role, constrained to the existing role set
  - `token_hash` (unique, SHA-256 of a 32-byte random token)
  - `inviter_id`, `approver_id` (`CHECK approver_id IS NULL OR approver_id <> inviter_id`), `approved_at`
  - `digest`: canonical request, bound for approval
  - `status`: `PENDING_APPROVAL | ACTIVE | REDEEMED | REVOKED`
  - `expires_at` (72 h), `redeemed_by`, `redeemed_at`, `created_at`
  - "Expired" is computed from `expires_at`, never stored.
- RLS FORCE on `invites`, scoped by `app.org` like other tenant tables. `guardian_app` gets SELECT and INSERT, plus column-level UPDATE on `status, approver_id, approved_at`. No DELETE, and no UPDATE of `roles`, `email_normalized` or `organization_id`.
- `login_attempts.invite_hash text NULL`. This is a global private auth record, like the rest of that table.
- `redeem_invite(invite_hash, issuer, subject, display_name, email)` is a `SECURITY DEFINER` function with a fixed `search_path`, executable by `guardian_app` only. In one statement set it:
  1. Locks the invite (`FOR UPDATE`). It requires `ACTIVE` and an unexpired invite, and the email must match `email_normalized` when present.
  2. Finds or creates `users(issuer, subject)`. `guardian_app` keeps SELECT-only on `users`; the function is the only insert path besides the operator bootstrap.
  3. Refuses if a membership already exists for that user in that organization.
  4. Inserts the membership with the invite's roles, marks the invite `REDEEMED` with `redeemed_by`, and writes an `invite.redeemed` audit event.
  5. Returns the user id, or a fixed refusal reason (`invalid`, `expired`, `not_approved`, `email_mismatch`, `already_member`). Refusals are audited by the caller in the organization's scope. An unknown token has no organization, so it is logged without a tenant.

## API

Under `/api/v1/organizations/{org}`. All routes use the router-level session dependency, and membership is checked first.

| Route | Capability | Notes |
|---|---|---|
| `POST /invites` `{email, role, justification}` | `members:propose` (org_admin) | Returns `{invite, link}`. The link is returned **only in this response**. A privileged role → `PENDING_APPROVAL` |
| `GET /invites` | `members:read` | Never returns the token or its hash. Shows status and computed expiry |
| `POST /invites/{id}/decision` `{digest, decision}` | `members:approve` + recent MFA | Approver ≠ inviter (API and DB CHECK). Digest must match. Only `PENDING_APPROVAL` |
| `POST /invites/{id}/revoke` | `members:propose` | `ACTIVE` or `PENDING_APPROVAL` → `REVOKED` |

Public:
- `GET /api/v1/auth/register?invite=<token>` starts OIDC with `invite_hash` stored server-side. It redirects to `{issuer}/protocol/openid-connect/registrations` with the same PKCE, state and nonce, and scope `openid profile email`. A token that is unknown, used or expired gets the same generic page with no details (no oracle). Rate-limited per IP like other anonymous routes.
- `complete_login`: when the subject is unknown **and** the consumed login attempt carries an `invite_hash`, it calls `redeem_invite`. Otherwise it keeps today's 403. A known subject with an invite redeems too, which lets an existing user of another organization join a new one.

When redemption is refused at the callback, no session is created. The invitee gets 403 with a fixed message per reason ("This invite is no longer valid — ask your administrator for a new one" for invalid, expired or not approved; "Sign in with the email address the invite was sent to" for email mismatch; "You are already a member of this organization" for already a member). The Keycloak account remains, without app access.

Every mutation writes an audit event and an outbox row in the same transaction, as role changes already do.

## Identity provider (local Keycloak)

`local_setup.py` and the realm:
- `registrationAllowed: true`, `registrationEmailAsUsername: false`.
- Required action `CONFIGURE_TOTP` as default for new users. The existing `amr` mapper then emits `pwd` + `otp`.
- Password policy `length(12) and notUsername`.
- Brute-force detection stays on.

Existing realms are updated by `provision_local_users.py` (idempotent), so no re-bootstrap is needed.

Production: whether self-registration is allowed is the external IdP's decision (U4). Only `/registrations` support is needed. If the IdP lacks it, the invitee registers through the IdP's own process and then opens the link while signed in.

## Web

- **Members → Invites** panel:
  - Create form (email, role, justification).
  - A one-time link display with a copy button and the warning "shown once".
  - A list with status badges. Revoke for admins; Approve for approvers on privileged invites.
- `/invite/<token>` landing page: "You've been invited to join an organization", with **Create account** and **I already have an account** (signs in, then redeems).
- No organization name or role is shown before authentication, so a leaked link reveals little.
- Keyboard and mobile layouts follow the existing shell.

## Security

| Threat | Mitigation |
|---|---|
| Stolen or forwarded link | Single use, 72 h expiry, revocable. Email must match (see residual). Redemption is audited with the subject |
| Role tampering | Role read only from the stored invite. Request bodies and token claims are never trusted |
| Self-escalation via invite | Privileged roles need an approver ≠ inviter (DB CHECK) with recent MFA and a digest binding |
| Replay or double redeem | Row lock + `REDEEMED` in the same transaction as the membership insert |
| Enumeration | Hash-only storage. Generic response for every invalid token. Per-IP rate limit |
| Cross-tenant | RLS on invites. The definer function is narrow and takes no organization argument from the caller |
| Open IdP registration | Accounts without invites get 403 from the app. No membership exists without an invite or bootstrap |

**Residual risk.** Locally there is no SMTP, so `email_verified` is false and the email match is consistency only, not proof. Possession of the link is the real factor until email verification exists (PLANNED). THREAT_MODEL.md gets a row for the invite boundary.

## Negative tests (all must fail closed and be audited)

1. Redeem twice → second refused (`invalid`).
2. Expired invite → `expired`.
3. Revoked invite → `invalid`.
4. Privileged invite before approval → `not_approved`.
5. Inviter approves own invite → 403 (API) and CHECK violation (DB).
6. Approval with a stale digest → 409.
7. A body field `role`/`roles` on redeem or register is ignored; the membership role equals the invite's.
8. Viewer or investigator creates an invite → 403. Approver creates an invite → 403.
9. Org A admin lists, revokes or approves an org B invite → 404.
10. Email mismatch → `email_mismatch`.
11. Already a member of that organization → `already_member`, with roles unchanged.
12. Unknown subject without an invite → 403 (existing behavior preserved).
13. Unknown token at `/auth/register` → generic page, no Keycloak redirect state leaked.
14. `GET /invites` never contains a token or its hash.
15. The runtime role cannot UPDATE `invites.roles` or INSERT into `users` directly.

Plus the authorization matrix (new routes declared) and an E2E browser test. That test creates an invite as alex (with TOTP), registers a new synthetic user through real Keycloak, computes TOTP from the setup page, and lands in the app as viewer.

## Out of scope

Email sending (PLANNED); self-service organization creation; changing roles through invites (use role requests); SCIM or just-in-time provisioning from external IdPs; production IdP configuration.
