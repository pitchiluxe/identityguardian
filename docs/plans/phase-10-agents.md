# Phase 10 — AI-agent registry

Approved by the user on 2026-09-30. Depends on Phase 9.

## Bounded plan

1. Fixture: resource data classifications (payroll, financial, customer-data, source-code, backups); declared agent scopes (`allowed_tools`, `allowed_data`, `prohibited_data`); agent activity telemetry with coverage. Fixture-count assertions now derive from the fixture.
2. `domain/agents.py`: registry profile (owner, department, model, purpose, maximum privilege, credential scope, expiry, declared vs effective tools/data from the lineage engine, excess, prohibited reach, observed activity). Rules `agents-2026.09-1`: AGENT_PROHIBITED_DATA (critical), AGENT_SCOPE_EXCEEDED, AGENT_REGISTRATION_EXPIRED/EXPIRING while entitlements remain.
3. Routes: `GET …/agents` with `tool` and `data_classification` capability queries and effective time; `GET …/agents/{id}/activity?from&to` (history:read, ≤366-day window, coverage statement).
4. Web: AI agents page with declared/effective comparison, expiry and activity, and capability filters.

## Verification ledger (2026-09-30)

- `tests/api/test_agents.py` (5): declared vs effective for the support agent, no findings by default; tool/data queries; an injected payroll membership produces AGENT_PROHIBITED_DATA (critical) and AGENT_SCOPE_EXCEEDED with evidence; EXPIRING at 2026-12-10 and EXPIRED (critical) at 2027-01-05; activity window, inverted window 422, non-agent 422, viewer 403.
- Playwright `agents.spec.ts` passed.
