# IdentityGuardian AI

**Autonomous Identity Intelligence, Governance & Security Platform**

Status: Phase 1 local foundation implemented and tested on loopback: OIDC login (Keycloak), opaque sessions/CSRF, PostgreSQL row-level tenant isolation, independent platform-role approval, append-only audit, outbox worker and an accessible shell. Identity ingestion, graph, AI, connectors and every later-phase capability remain PLANNED.

Identity access is scattered across directories, groups, policies and applications. IdentityGuardian AI is designed to explain who can reach a resource, why, what evidence supports that conclusion, and what would happen if access changed.

Investigate → explain → recommend → simulate → authorized human approval → controlled execution → audit. Initial execution is simulated only.

## Review the design

Start with [PHASE_0_REVIEW.md](PHASE_0_REVIEW.md). Supporting documents: [architecture](ARCHITECTURE.md), [database](DATABASE.md), [graph](GRAPH.md), [security](SECURITY.md), [threat model](THREAT_MODEL.md), [roadmap](ROADMAP.md), [requirements](REQUIREMENTS.md).

## Planned capabilities

Interactive digital twin, access lineage, privilege creep, defensive exposure paths, evidence-backed reviews, what-if simulation, temporary privilege workflows, machine and agent governance, lifecycle controls, historical reconstruction, grounded local AI, policy proposals and guided IAM labs.

Proposed stack: React/TypeScript, FastAPI, PostgreSQL, local Keycloak and Ollama. Concepts demonstrated: RBAC, contextual ABAC, nested grants, separation of duties, PAM, IGA, JML, SCIM and SAML/OIDC troubleshooting. See [AI.md](AI.md), [UI.md](UI.md), [API.md](API.md) and [INTEGRATIONS.md](INTEGRATIONS.md).

## Demo and installation

[INSTALLATION.md](INSTALLATION.md) lists the verified local setup and its limitations. [DEMO.md](DEMO.md) defines the Contoso investigation; [LABS.md](LABS.md) defines exercises. Future verified captures belong in [screenshots](docs/screenshots/README.md) and [videos](docs/videos/README.md). No fabricated screenshots are included.

## Contributing

Read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [TESTING.md](TESTING.md) and [CHANGELOG.md](CHANGELOG.md). The original brief is [PROMPT.md](PROMPT.md). Each later phase is gated on user approval.
