# Phase 6 — evidence access reviews

Approved by the user on 2026-09-30. Depends on Phases 3–5.

## Bounded plan

1. Migration `005_reviews_changes.sql`: `change_requests` with the full SECURITY.md status vocabulary, version and idempotency; `review_campaigns` (rules, due date, frozen snapshot); `review_items` (grant under review, finding keys, frozen evidence, recommendation + basis, uncertainty, assigned reviewer, decision trail; a CHECK forces decider = assigned reviewer and a justification). RLS on all; runtime role has column-limited updates.
2. `domain/changes.py`: canonical remove-relationship targets (current effective grant/exposure edges only), idempotent creation, audited, state-machine transitions with optimistic versioning.
3. Routes: reviewers list, create campaign (`review:manage`, reviewer must hold `review:decide` and differ from the owner), list/view campaigns, decide (`review:decide`, assigned reviewer only, version-checked, one decision), list change requests.
4. Recommendation (RULE-BASED): REMOVE only for leavers or when every privileged target has complete-coverage non-use and nothing shows use; otherwise REVIEW. Never auto-KEEP. Uncertainty lists coverage limits, conditional access, unknown provenance and small peer samples.
5. Web: Access reviews page (campaign creation, campaign view, evidence, uncertainty, decision form, decision trail and linked proposal).
6. `scripts/provision_local_users.py`: idempotently adds SYNTHETIC reviewer/investigator/auditor/operator/learner/approver users to the loopback Keycloak and memberships (Keycloak-assigned IDs reconciled); `local_setup.py` includes them for fresh setups.

## Verification ledger (2026-09-30)

- `tests/api/test_reviews.py` (4): items carry grant/finding evidence, RULE-BASED REMOVE for Erick and coverage/peer-sample uncertainty; viewer and non-assigned admin cannot decide; invalid reviewer/rule 422; cross-environment 404; stale version 409; REMOVE creates a DRAFT `remove_relationship` proposal for `mem-erick-grp-finance-legacy` while Erick's access is unchanged; second decision 409; audit contains `review.decided` and `change.proposed`; unknown fields rejected.
- Playwright `reviews.spec.ts`: alex creates a campaign for Riley; Riley sees evidence and uncertainty, records REMOVE, sees the DRAFT proposal.
