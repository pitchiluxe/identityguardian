# IdentityGuardian AI — User Manual

> ## 📬 Need access, a new role, or help? Contact the administrator
>
> **Email: [erickomari243@gmail.com](mailto:erickomari243@gmail.com)** (Erick Omari, platform administrator)
>
> Nobody can give themselves access to IdentityGuardian AI. **Every account needs an invite from the administrator.** Send an email to **erickomari243@gmail.com** and include:
>
> 1. Your **full name**
> 2. The **email address** you will register with. It must match exactly.
> 3. The **role** you need (see [Roles](#3-roles--what-each-one-can-do)), or what you want to do if you are unsure
> 4. **Why** you need it, in one or two sentences
>
> You will receive a personal invite link. It works **once** and expires after **72 hours**.

---

## Contents

1. [What IdentityGuardian AI is](#1-what-identityguardian-ai-is)
2. [Getting access (new users)](#2-getting-access-new-users)
3. [Roles — what each one can do](#3-roles--what-each-one-can-do)
4. [Signing in](#4-signing-in)
5. [Using the workspace](#5-using-the-workspace)
6. [For the administrator: sending invitations](#6-for-the-administrator-sending-invitations)
7. [Changing someone's role](#7-changing-someones-role)
8. [Troubleshooting](#8-troubleshooting)
9. [Things to know](#9-things-to-know)

---

## 1. What IdentityGuardian AI is

IdentityGuardian AI is an identity security and IAM training platform. It answers questions such as:

- **Who can reach this resource, and why?** Every route through groups, roles and conditions, each backed by evidence.
- **What could go wrong?** Defensive exposure paths to sensitive resources.
- **What did access look like at an earlier time?** The time machine.
- **What would happen if we changed it?** The what-if simulator. Changes need a second person's approval.

All data in this environment is **synthetic** (the fictional company "Contoso Global Technologies"). The platform is never connected to real identity systems and never changes real access.

Public overview page: <https://identityguardian.vercel.app> · Source code: <https://github.com/pitchiluxe/identityguardian>

---

## 2. Getting access (new users)

> ⚠️ **You cannot sign up on your own.** If you click "Register" on the sign-in page without an invite link, your account will be created but you will see:
> *"Your account has no access to this platform yet…"*
> In that case, email **[erickomari243@gmail.com](mailto:erickomari243@gmail.com)** and ask for an invite for the email address you registered with.

### Step 1 — Request an invite

Email **[erickomari243@gmail.com](mailto:erickomari243@gmail.com)** with your name, email address, the role you need and the reason (see the box at the top).

### Step 2 — Open your invite link

The administrator sends you a link that looks like:

```
http://<platform-address>/invite/AbCdEf...
```

Open it in your browser. You will see **"You've been invited"** and two buttons.

### Step 3 — Choose the right button

| If… | Click |
|---|---|
| You have **never** created an account on this platform | **Create account** |
| You **already** registered (even if you were told you have no access) | **I already have an account** |

### Step 4 — Create your credentials (new accounts)

On the registration page:

1. Choose a **username**.
2. Enter **the same email address the invite was sent to**. A different email is refused.
3. Enter your first and last name.
4. Choose a **password of at least 12 characters** that does not contain your username.
5. Click **Register**.

### Step 5 — Set up your one-time code (required)

You will be asked to set up an **authenticator app**, such as Microsoft Authenticator, Google Authenticator or Authy:

1. Open the authenticator app on your phone and add a new account.
2. **Scan the QR code** on screen. If you cannot scan, click **"Unable to scan?"** and type in the key that is shown.
3. Enter the **6-digit code** the app shows, then click **Submit**.

From now on you sign in with **username + password + 6-digit code**. The code changes every 30 seconds.

### Step 6 — You're in

You land in the workspace with exactly the role in your invite. To get a different role later, email **[erickomari243@gmail.com](mailto:erickomari243@gmail.com)**.

---

## 3. Roles — what each one can do

Roles control what you can see and do. You only get the roles the administrator grants.

| Role | Can do | Typical person |
|---|---|---|
| **viewer** | Dashboard, identities and identity graph (read-only) | Stakeholder, observer |
| **investigator** | Everything a viewer can, plus effective access, findings, history and AI investigations. Can propose and simulate changes and request temporary (JIT) access | Security analyst |
| **reviewer** | Analysis pages, plus decide access reviews | Manager, data owner |
| **auditor** | Analysis pages, plus audit log and reports | Compliance, internal audit |
| **learner** | Labs only | Student, trainee |
| **approver** ⚠️ | Approve role changes, access changes, JIT and policies | Security lead |
| **operator** ⚠️ | Execute approved changes, run connector syncs, execute JIT | Platform operator |
| **org_admin** ⚠️ | Manage members and invites, connectors, reviews, policies, reports and labs | Platform administrator |

⚠️ = **privileged role.** Invites for these roles must be approved by a second person before the link works. Approving and executing also require a recent sign-in with your one-time code (within 5 minutes).

> Not sure which role to ask for? Email **[erickomari243@gmail.com](mailto:erickomari243@gmail.com)** and describe what you need to do. The administrator will choose the right role.

---

## 4. Signing in

1. Open the platform address (locally: <http://localhost:8000>).
2. Click **Sign in with your identity provider**.
3. Enter your username, password and 6-digit code.
4. Choose your **Organization** and **Environment** in the top bar. **Foundation sandbox** has the richest demo data.

To sign out, click the arrow icon next to your name in the top-right corner.

> **Approving or executing something?** The platform asks for a sign-in **within the last 5 minutes** that used your one-time code. If you see *"Recent verified MFA is required"*, sign out and sign in again.

---

## 5. Using the workspace

The left menu is grouped by purpose. Pages you are not authorized for say *"Restricted to authorized roles"*. To get access to them, email **[erickomari243@gmail.com](mailto:erickomari243@gmail.com)**.

| Group | Page | What it is for |
|---|---|---|
| Overview | **Dashboard** | Summary of the selected environment |
| | **Identities** | Searchable list of people, machines and agents; click one for its profile |
| | **Applications** | Applications and resources |
| | **Access** | Pick an identity to see **every** route to each entitlement, with evidence |
| | **Identity graph** | Visual map of relationships around one identity (type an ID in **Focus**) |
| Intelligence | **Privilege radar** | Retained or unused access, privilege creep |
| | **Attack paths** | Defensive view of potential exposure to sensitive resources |
| | **Investigations** | Ask questions of the evidence, optionally with local AI (advisory only) |
| | **Time machine** | What access looked like at a past date, as known then vs. now |
| Governance | **Access reviews** | Certify or flag access with evidence |
| | **JIT access** | Request and approve temporary access |
| | **Lifecycle** | Joiner / mover / leaver workflows |
| | **What-if simulator** | Preview the effect of a change before proposing it |
| | **Change requests** | Propose → independent approval → execute (sandbox only) |
| | **Policies** | Policy-as-code: write, test, simulate, approve, activate |
| Non-human | **Machine identities** / **AI agents** | Service accounts, credentials and AI agent permissions |
| Learning | **Labs** | Hands-on IAM exercises with hints and scoring |
| Operations | **Reports** | Evidence-cited reports and exports |
| | **Audit logs** | Who did what, when and why; tamper-evident |
| | **Integrations** | Mock and sandbox connectors and sync runs |
| | **Administration** | Members, role changes and **Invites** |

**Two-person rule:** consequential actions (role changes, access changes, privileged invites, policies) are proposed by one person and approved by a **different** person. Nobody can approve their own request.

---

## 6. For the administrator: sending invitations

> Only **org_admin** members can create invites. Only **approvers** can approve privileged ones.

### Create an invite

1. Sign in and open **Administration** (left menu, *Operations*).
2. Scroll to the **Invites** panel.
3. Fill in:
   - **Email** — the address the person will register with (exact match required)
   - **Role** — one role per invite (see [Roles](#3-roles--what-each-one-can-do))
   - **Justification** — why they need it (at least 8 characters; it is recorded in the audit log)
4. Click **Create invite**.
5. **Copy the link immediately.** It is shown **only once**. Use the **Copy link** button.

> 📧 **The platform does not send email.** Send the link yourself by email, Teams or chat. Only send it to the person it is for: whoever opens it first can use it.

**Message template you can send:**

> Hi \<name\>,
>
> You've been invited to IdentityGuardian AI as **\<role\>**.
>
> 1. Open this link (valid 72 hours, single use): **\<paste link\>**
> 2. Click **Create account** (or **I already have an account** if you registered before).
> 3. Register with **this email address: \<their email\>**, and use a password of at least 12 characters.
> 4. Set up the one-time code with an authenticator app when asked.
>
> Questions? Reply to me at erickomari243@gmail.com.

### Privileged invites (org_admin, approver, operator)

These start as **PENDING_APPROVAL**, and the link does **not** work yet.

1. A **different** person with the **approver** role signs in with a one-time code, within 5 minutes.
2. They open **Administration → Invites** and click **Approve** on the pending invite.
3. The status changes to **ACTIVE** and the link now works. Send it if you haven't already.

### Invite statuses

| Status | Meaning |
|---|---|
| **ACTIVE** | Link works; waiting for the person to use it |
| **PENDING_APPROVAL** | Privileged invite; needs an approver first |
| **REDEEMED** | Used; the person is now a member |
| **REVOKED** | Cancelled by an admin; link no longer works |
| **EXPIRED** | More than 72 hours old; create a new invite |

### Revoke an invite

If a link was sent to the wrong person, or is no longer needed, click **Revoke** next to it. The link stops working immediately.

### Someone says "This invite is no longer valid"

The link was already used, revoked, expired, or (for privileged roles) not approved yet. Check its status in **Invites** and create a new one if needed.

### Someone registered without an invite

They have an account but no access. Create an invite for **the email they registered with**. Tell them to open the link and click **I already have an account**.

---

## 7. Changing someone's role

Roles of existing members are changed in **Administration → Propose a platform role replacement**:

1. An **org_admin** selects the member, picks the new role and writes a justification, then submits.
2. A **different approver** clicks **Approve exact proposal**. A recent one-time-code sign-in is required.
3. An **operator** clicks **Execute approved role change**.

Members ask for role changes by emailing **[erickomari243@gmail.com](mailto:erickomari243@gmail.com)**.

---

## 8. Troubleshooting

| You see | What it means | What to do |
|---|---|---|
| *"Your account has no access to this platform yet…"* | You have an account but no invite was redeemed | Email **erickomari243@gmail.com** for an invite, then use **I already have an account** |
| *"This invite is no longer valid — ask your administrator for a new one"* | Link used, revoked, expired or not yet approved | Email **erickomari243@gmail.com** for a new link |
| *"Sign in with the email address the invite was sent to"* | Your account email differs from the invited one | Register or sign in with the invited email, or ask for a new invite to your email |
| *"You are already a member of this organization"* | You already have access | Just use **Sign in** |
| *"Restricted to authorized roles"* | Your role doesn't include that page | Email **erickomari243@gmail.com** to request a role |
| *"Recent verified MFA is required"* | Approve/execute needs a fresh sign-in with your code | Sign out, sign in again, retry within 5 minutes |
| One-time code rejected | Code expired or phone clock is off | Wait for the next code and check your phone's time is set automatically |
| *"Request limit reached; retry shortly"* | Too many requests per minute | Wait a minute |
| *"Database unavailable…"* | Server-side problem | Try again shortly; if it persists, email **erickomari243@gmail.com** |
| Lost your phone / authenticator | Can't produce codes | Email **erickomari243@gmail.com** to have your one-time code reset |

---

## 9. Things to know

- **Synthetic data only.** Contoso and every person in it are fictional. Nothing connects to real directories or applications.
- **AI is advisory.** The investigator answers from evidence with citations, but it can never approve or execute anything.
- **Everything is audited.** Invites, approvals, refusals and role changes appear in **Audit logs**.
- **Keep invite links private.** Each is a one-time key to an account with a specific role.
- **Email delivery of invites is not built in yet.** The administrator sends links manually.

---

**Administrator / contact:** Erick Omari — **[erickomari243@gmail.com](mailto:erickomari243@gmail.com)** · [LinkedIn](https://www.linkedin.com/in/erickomari/) · [GitHub](https://github.com/pitchiluxe)
