# Phase 13 — grounded local AI investigator

Approved by the user on 2026-09-30. Depends on Phases 3, 5 and 12.

## Bounded plan

1. `ai/intents.py`: deterministic parsing into eight allowlisted read-only intents (identity status, effective access, lineage, who can access, ownerless machines, dormant administrators, exposure paths, previous-role access). Mutating, command, secret or ambiguous questions return a clarification and run no query.
2. `ai/planner.py`: capability check per intent before retrieval; deterministic engines produce an evidence bundle of numbered facts (F1…), each with evidence IDs; bounded (25 facts) with completeness notes.
3. `ai/provider.py`: Ollama adapter (default local `qwen2.5:7b`, temperature 0, JSON-schema output). Endpoint must be loopback or explicitly allowlisted; `:cloud`/`-cloud` models are refused so evidence never leaves the machine. Errors become "AI unavailable".
4. `ai/validate.py`: claims must be typed (fact/inference/recommendation), cite existing fact IDs, use only numbers and tenant names present in the cited facts; otherwise rejected with a reason. System prompt marks evidence as data, not instructions.
5. Route `POST …/investigations/query` (`investigation:run`, 5/minute/user): statuses VALIDATED, PARTIAL, FALLBACK (deterministic summary), AI_UNAVAILABLE, INSUFFICIENT, CLARIFICATION; every answer carries an advisory disclosure; investigations stored separately from evidence (migration 013) with model and digest version.
6. Web: Investigations / AI assistant page with examples, answer claims and citations, rejected claims, evidence bundle and history.

## Verification ledger (2026-09-30)

- `tests/unit/test_ai.py` (16): supported intents; mutating/command/secret/ambiguous questions clarified; validator rejects invented numbers, foreign names, unknown citations, uncited claims, unknown types and non-schema output; endpoint policy refuses metadata IP and cloud models.
- `tests/api/test_investigations.py` (7): grounded lineage answer VALIDATED with evidence IDs; fabricated citations/numbers fall back to the deterministic summary; injected instructions in source data stay inside the evidence block with an advisory disclosure; offline model keeps evidence available (AI_UNAVAILABLE); unsupported requests never reach the model; viewer 403, other-environment 404, AI rate limit 429; a real local `qwen2.5:7b` call (skipped when Ollama is not running) produced only citations from the bundle.
- Verification corrected a sentence-final number parsing bug and added short target aliases ("payroll", "erp").
- Playwright `investigate.spec.ts` passed (evidence fallback without the model; mutating request clarified).
- Limitation: grounding checks prove citation consistency, not truth; untrusted source text quoted in evidence can still be restated. Output remains advisory.
