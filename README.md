# IdentityGuardian AI

**Autonomous Identity Intelligence, Governance & Security Platform**

**Live showcase:** https://identityguardian.vercel.app · **Contact:** see the showcase page

Status: Phases 1–21 are implemented and tested locally against real Keycloak (OIDC + PKCE + TOTP) and PostgreSQL. They cover tenant isolation (RLS), independent approval, an append-only hash-chained audit, digital twin ingestion, effective-access lineage, privilege radar, defensive exposure paths, access reviews, what-if simulation, JIT and sandbox execution, machine and AI-agent governance, joiner/mover/leaver, a bitemporal time machine, a grounded local Ollama investigator, policy-as-code, IAM labs, a mock connector framework, evidence-cited reports, security hardening, performance work, packaging and invite-based registration. **All data is synthetic. Connectors are mock or sandbox only. The platform is not production-accepted**; see [docs/operations/production-acceptance.md](docs/operations/production-acceptance.md).

Identity access is scattered across directories, groups, policies and applications. IdentityGuardian AI explains who can reach a resource, why, what evidence supports that conclusion, and what would happen if access changed.

Investigate → explain → recommend → simulate → authorized human approval → controlled (sandbox) execution → audit. AI output is advisory and has no execution authority.

## Where to look

- Per-phase plans and verification ledgers: [docs/plans/](docs/plans/)
- Design: [architecture](ARCHITECTURE.md), [database](DATABASE.md), [graph](GRAPH.md), [security](SECURITY.md), [threat model](THREAT_MODEL.md), [roadmap](ROADMAP.md)
- Operations runbooks: [docs/operations/](docs/operations/)
- Showcase page source: [showcase/](showcase/)

Stack: React 19 + TypeScript + Vite, FastAPI, PostgreSQL 17 with row-level security, Keycloak, Ollama, pytest and Playwright.

## Demo and installation

[INSTALLATION.md](INSTALLATION.md) lists the verified local setup and its limitations. [DEMO.md](DEMO.md) defines the Contoso investigation; [LABS.md](LABS.md) defines exercises. Screenshots in [showcase/shots](showcase/shots) were captured from the running local build (`CAPTURE=1 npx playwright test tests/e2e/capture.spec.ts`). No fabricated screenshots are included.

## Contributing

Read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), [TESTING.md](TESTING.md) and [CHANGELOG.md](CHANGELOG.md). The original brief is [PROMPT.md](PROMPT.md). Each phase is gated on owner approval.
