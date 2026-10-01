# Phase 12 — Time Machine

Approved by the user on 2026-09-30. Temporal foundation from Phase 2 onward.

## Bounded plan

1. Edges carry their knowledge time (`recorded_from`).
2. `domain/history.py`: reconstruct an identity's effective access at `effective_at` both as known at `known_at` and as known now; differences labelled LEARNED_LATER (with the late edges) or CORRECTED_LATER; an identity without evidence at the time is UNKNOWN (never projected backward; 404 only if it never appears); coverage notes (nothing ingested yet, partial last sync, rejected records, effective time before earliest evidence, knowledge time before first observation, no usage telemetry).
3. Migration `012_history.sql`: checksummed `historical_snapshots` (counts, graph version, coverage); verification replays from immutable evidence and reports MATCH/MISMATCH.
4. Routes (history:read): identity reconstruction (aware timestamps only, knowledge time not in the future), snapshot create/list/verify.
5. Web: Time machine page (local input, UTC display, side-by-side then/now, differences, coverage, snapshots with replay).

## Verification ledger (2026-09-30)

- `tests/api/test_history.py` (5): late evidence (grant recorded after the knowledge time) absent "then" and present "now" with TKT-LATE attribution; post-removal history keeps payroll at 2026-07-01 while today it is gone; Nina before joining and knowledge before any ingestion are UNKNOWN with coverage notes; equivalent instants across offsets/DST give identical results, naive timestamps and future knowledge times are 422, viewer 403; snapshot replay MATCH, then MISMATCH after simulated database-administrator tampering.
- Playwright `history.spec.ts` passed.
