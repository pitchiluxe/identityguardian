# Requirements traceability

Source: PROMPT.md. All product capabilities are planned; this phase supplies their design.

| User requirement | Design owner | Delivery |
|---|---|---|
| Digital twin and interactive relationships | GRAPH.md, DATABASE.md, UI.md | 2 |
| Access origin and evidence chain | GRAPH.md | 3 |
| Privilege accumulation and timeline | DATABASE.md, DEMO.md | 4 |
| Defensive exposure paths | GRAPH.md, THREAT_MODEL.md | 5 |
| Evidence access review and uncertainty | AI.md, UI.md, SECURITY.md | 6,13 |
| What-if dependencies/lockouts | GRAPH.md, SECURITY.md | 7 |
| JIT approval/expiry/revocation | SECURITY.md | 8 |
| Machine identity governance | DATABASE.md | 9 |
| AI-agent identity registry | DATABASE.md | 10 |
| Explainable risk story | GRAPH.md, AI.md | 4–6 |
| Joiner/mover/leaver controls | ROADMAP.md, DEMO.md | 11 |
| Historical reconstruction | DATABASE.md, GRAPH.md | 12 |
| Grounded natural-language investigator | AI.md | 13 |
| Policy generation/test/approval | ROADMAP.md | 14 |
| Contoso labs and Ollama instructor | LABS.md, AI.md | 15 |
| Sandbox-first enterprise connectors | INTEGRATIONS.md | 2,16 |
| Reports and exports | ROADMAP.md, API.md | 17 |
| Security, audit, authorization | SECURITY.md, THREAT_MODEL.md, TESTING.md | 1 onward; hardening 18 |
| Performance and packaging | ARCHITECTURE.md, ROADMAP.md | 19–20 |
| Navigation and real controls | UI.md | shell 1; incremental |
| Documentation and specialist instructions | README.md, docs/agents/README.md | 0; maintained every phase |

Dashboard metrics are query-derived: total/human/machine/agent/privileged identities, dormant/orphaned accounts and service accounts, pending reviews, temporary privileges, policy violations, creep/exposure findings, attack paths and JML events. Each count shares stated scope/snapshot and links supporting records.

Origin vocabulary: direct assignment, group/nested membership, role, RBAC, ABAC, temporary privilege, application role, legacy entitlement, delegation, manager approval, automated provisioning and unknown/orphaned. Store observed source separately from inferred explanation; unknown provenance stays unknown.
