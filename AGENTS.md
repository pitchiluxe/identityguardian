# Development instructions

Current stage: Phase 0 review. Do not write product code until the user reviews and approves the package. PROMPT.md preserves the request; user instructions take precedence.

Before each phase: inspect architecture, identify dependencies, create bounded plan, implement, test, check security/regressions, document and commit phase-owned files. No uncontrolled pass across phases. Planned controls are not implemented controls.

Never fabricate IAM findings or AI outputs. Synthetic data must be labeled. AI has no execution authority. Preserve scope isolation, evidence and approval/version binding. Every control works or is DEMO/PLANNED. No credentials in Git.

Specialist roles in docs/agents define responsibilities, not authorization to spawn agents. Assign one owner per work package; coordinate shared contracts, read current files before editing, preserve others' changes. Handoffs list files, interfaces, tests and unresolved risks. Never reset unrelated work.
