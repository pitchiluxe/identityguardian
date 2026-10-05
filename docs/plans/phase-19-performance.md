# Phase 19 — performance

Depends on Phase 18. Acceptance gate (ROADMAP): measured graph/database/load benchmarks, scoped cache invalidation, correct bounded results.

## Bounded plan

1. **Synthetic scale dataset**: `packages/fixtures/scale.py` builds 10,000 identities with ~103,000 relationships. It includes nested groups, cycles, conditional grants and denies. It is SYNTHETIC and not a realistic org chart.
2. **Benchmark harness**: `python -m scripts.benchmark` creates a dedicated SANDBOX environment in the bootstrapped organization. It bulk-loads the source, ingests it through the normal pipeline, measures engine and HTTP latencies (p50/p95/p99) and records hardware in `docs/performance/benchmark-*.json`. `--reuse` re-measures the latest benchmark environment without ingesting again. The HTTP phase needs the API started with a raised quota (`READ_LIMIT_PER_MINUTE=100000`). The default 60/min per-user limit correctly returns 429.
3. **Ingest**:
   - `Ingestor.prefetch()` bulk-loads existing state for large batches and connector jobs, replacing per-object lookups.
   - Per-object savepoints are removed. Every validation now runs before the first write, so a rejected object leaves no observation (`test_malformed_node_leaves_no_observation`).
   - Connector jobs reuse one prefetched ingestor across pages.
4. **Snapshot cache and scoped invalidation**:
   - A process-level LRU cache holds current-knowledge rows and built snapshots, keyed by environment and graph version.
   - Migration `021_graph_watermarks.sql` adds a trigger-maintained per-environment change counter. Any insert, update or delete on nodes, relationships or their revisions changes the version, whichever code path wrote it, so invalidation is scoped to the changed environment.
   - The runtime role can only read the counter. Historical (`known_at`) loads still aggregate revisions and are never cached.
   - A built snapshot is reused only until the next validity or expiry boundary.
5. **Correct bounded results**:
   - Depth and per-entitlement path bounds now prune one branch. Expansion and time bounds stop the whole search. Previously, the first over-deep branch aborted the entire traversal, so routes on other branches went missing.
   - `principals_for` is a single reverse search.
   - Deny closures are computed only when a deny exists on a found route's permission.
   - Usage and coverage for an effective-access result take two queries, not two per entitlement.
6. **Database**: migration `020_fk_indexes.sql` adds indexes supporting foreign-key checks. `manage.py analyze` refreshes planner statistics after bulk loads.

## Results (synthetic, local; see JSON for hardware and parameters)

Hardware: Windows 11, Intel 8 logical CPUs, 23.7 GiB RAM, PostgreSQL 17.7, Python 3.12, single uvicorn worker. Dataset: 21,420 nodes and 103,174 relationships in the measured environment. The development database also holds earlier benchmark copies and ~6,300 test environments, which slows organization-scoped scans.

| Measurement | 2026-10-01 baseline | Final (`benchmark-20261005T0254Z.json`) |
|---|---|---|
| Effective access, engine p50 / p95 / p99 | 36 / 59 / 166 ms, 200/200 partial (search aborted at first depth hit) | 66 / 94 / 1,494 ms, 149/200 partial (honest depth limit 8) |
| Who-can-access, engine p50 / p95 | 2,968 / 4,382 ms, 20/20 partial | 3,769 / 6,395 ms, 11/20 partial |
| Snapshot load, cached p50 / p95 | 573 / 1,429 ms | 1.8 / 431 ms |
| Snapshot load, uncached p50 | 3,723 ms | 13,979 ms (larger database; see limitations) |
| HTTP effective access, 10 concurrent, 300 requests | not measured (API unreachable) | p50 1,263 ms, p95 5,900 ms, p99 24,865 ms, 3.4 req/s |
| Ingest of 124,594 objects | 193 s (645 obj/s) | 448 s (278 obj/s) in `benchmark-20261005T0200Z.json`, run while the test suite was also running |

The baseline's lower effective-access latency came from incomplete work: it stopped at the first depth limit. The final numbers return every route within the bounds.

## Limitations (not resolved in this phase)

- Uncached snapshot loads scan the organization's revisions, and they slow as the database grows. Revisions carry no `environment_id`.
- HTTP tail latency is poor. A single Python process serializes CPU-bound graph walks under the GIL, and full-lineage responses are ~1.5 MB. Pagination, response trimming and multiple workers are candidates for Phase 20 sizing.
- Who-can-access time bounds cover traversal only. Summarizing thousands of principals can exceed the bound.
- The benchmark measures one machine with synthetic data. No production-scale or multi-node claim is made.

## Verification ledger (2026-10-05)

- New tests: `tests/unit/test_bounds.py` (4; the depth-prune tests fail against the previous `access.py`) and `tests/api/test_snapshot_cache.py` (7: cache equals uncached, invalidation on sync and on a direct SQL write, no cross-environment or cross-tenant reuse, and the runtime role cannot update, insert or call the watermark function).
- pytest (final, all Phase 19 changes): 244 passed. Playwright was not re-run in this phase; no web code changed.
- ruff check/format clean; secret scan 0 findings.
- Re-verification (2026-10-05, second session): ruff check/format clean. Three full pytest runs: 243 passed + 1 failed (`test_policies.py::test_reversion_is_a_new_reviewed_version`), 243 passed + 1 failed (`test_oidc.py::test_interrupted_exchange_consumes_state`), 244 passed. Both failing tests pass when run alone. The captured failure was a `PoolTimeout`: `error connecting ... connection timeout expired`, returned as 503. Loopback connect latency measured during a full run: p50 0.375 s, p99 8.1 s, max 9.2 s, against a 10 s `connect_timeout`. Idle: p50 0.145 s. Cause: slow PostgreSQL backend startup on Windows under 4-worker CPU load, plus a fresh pool per test app. Known flake, not resolved here. Options: share one app per xdist worker, or run with `-n 2`.
