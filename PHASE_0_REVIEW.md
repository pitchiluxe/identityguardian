# IdentityGuardian AI — Phase 0 review

2026-09-30 · PROPOSED · Awaiting user review. This is a design package, not a running application.

The intended outcome is an evidence-driven IAM intelligence platform and isolated training environment. The integrated demonstration follows retained access from an employee's previous role through detection, explanation, exposure analysis, simulation, independent approval, sandbox execution and historical reconstruction.

## Proposed decisions

| Decision | Recommendation | Tradeoff |
|---|---|---|
| Delivery | Local-first; eventual Docker Compose | No cloud credentials; operator manages services |
| Application | React/TypeScript UI and Python FastAPI modular monolith | Clear API boundary and Python analysis; two languages |
| Data | PostgreSQL with temporal relational graph | Transactional evidence and grants; bounded traversal initially |
| Authentication | OIDC code flow with PKCE; local Keycloak | Standards-based MFA path; additional service |
| Jobs | PostgreSQL outbox and separate worker | Less infrastructure; requires leases/reconciliation |
| AI | Ollama provider adapter | Local evidence; quality depends on model/hardware |
| Execution | Sandbox first, independent human approval | Production adapters need separate review |
| History | Bitemporal facts and immutable source evidence | Distinguishes effective time from knowledge time; storage cost |

A full TypeScript stack reduces language overhead. Microservices with a dedicated graph database offer independent scaling but add consistency and operations costs. Recommend the modular monolith with replaceable interfaces until measurements justify separation.

Assumptions: one local deployment initially, organization isolation from Phase 1, deterministic synthetic fixtures, UTC storage, explicit display timezone, no hosted model by default. Versions will be selected, pinned and tested during implementation.

## Review documents

- [Architecture](ARCHITECTURE.md), [database](DATABASE.md), [graph](GRAPH.md)
- [Security](SECURITY.md), [threat model](THREAT_MODEL.md)
- [UI](UI.md), [AI](AI.md), [API](API.md), [connectors](INTEGRATIONS.md)
- [Requirements](REQUIREMENTS.md), [roadmap](ROADMAP.md), [foundation work packages](docs/plans/phase-1-foundation.md)
- [Demo](DEMO.md), [labs](LABS.md), [tests](TESTING.md)

## Exit criteria

- [x] Architecture, technology choices and repository structure documented.
- [x] Logical database, graph, threats and security boundaries documented.
- [x] Design system, phased acceptance roadmap and specialist responsibilities documented.
- [x] User review and approval (user approved in chat on 2026-09-30 and authorized proceeding through the roadmap).

Approval accepts the proposed direction and permits local Phase 1 work. It does not authorize production connections, deployment or real IAM changes. No application or security control is claimed implemented.
