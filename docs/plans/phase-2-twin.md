# Phase 2 — digital twin, ingestion and explorer

Approved by the user on 2026-09-30 ("proceed to the end of this build"). Depends on Phase 1.

## Bounded plan

1. Migration `003_twin.sql`: sandbox source objects, connectors, sync runs, immutable observations, twin nodes, bitemporal node/relationship revisions (`valid_*` source-effective, `recorded_*` knowledge time, gist exclusion against overlapping current revisions), usage events, telemetry coverage, employment events. FORCE RLS on all; runtime role is insert-only on evidence and may only close knowledge intervals.
2. `packages/fixtures/contoso.py`: deterministic SYNTHETIC Contoso source (434 objects; alternate-path variant adds one).
3. `domain/types.py`: GRAPH.md relationship vocabulary, endpoint-kind validation, classification.
4. `domain/ingest.py`: seed sandbox (LAB/SANDBOX only) → read by cursor → digest-idempotent observations → twin records. Partial syncs never imply absence; only full authoritative reads close absent relationships, marked `end_inferred`.
5. `domain/graph.py`: snapshot at (effective_at, known_at) with graph version; bounded undirected neighbourhood with hub collapse.
6. Routes (`routes/twin.py`): environments, seed, sync, sync runs, summary, paginated identities, node profile with history and evidence IDs, neighbours, applications. Envelope with correlation, snapshot and completeness.
7. Web: modular shell (environment selector, freshness), Identities, profile, Identity graph (SVG + equivalent accessible table), Applications, Integrations.

## Acceptance (ROADMAP gate)

Deterministic import, duplicate replay safety, clickable typed graph, tenant isolation.

## Verification ledger (2026-09-30)

- `tests/api/test_twin.py` (9): deterministic counts; full replay = 434 unchanged / 0 created; capability and PRODUCTION refusal; cross-tenant and cross-environment 404 plus runtime-role RLS check; provenance (TKT-1042) and attribute history (Finance → IT, effective-time query); explorer bounds, truncation flag and preserved group cycle; source removal is bitemporal (current gone, past retained, known-at-before still open); invalid relationship rejected without partial writes; partial sync never tombstones while full authoritative sync does (`end_inferred`); cursor pagination.
- Full pytest 44 passed; Playwright 6 passed including `twin.spec.ts` (admin seeds/syncs/follows Erick's provenance into the graph; viewer cannot seed/sync).
- Limitations: environment-level scope only (no per-resource viewer scopes yet); sync runs inline in the request (moved to jobs in Phase 16).
