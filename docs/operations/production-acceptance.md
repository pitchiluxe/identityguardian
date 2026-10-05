# Production acceptance checklist

**Status: NOT ACCEPTED.** Phase 20 delivers packaging and runbooks that were verified locally. Production acceptance is a decision for the project owner. Several gates below are open and this project cannot close them itself.

## Delivered and verified locally (see Phase 20 ledger)

- [x] Container image: non-root, read-only filesystem, healthcheck; TLS proxy; internal database network.
- [x] Secrets from mounted files; master-key rotation with audited re-wrap; withdrawn key fails closed.
- [x] Liveness/readiness probes, JSON logs, worker heartbeat, operator status with exit code.
- [x] Backup with checksum manifest, and an executed restore drill.
- [x] Deployment, monitoring, key-management and recovery runbooks.

## Open gates (owner decision required)

| Gate | Source | Required before production |
|---|---|---|
| Independent penetration test | U1 | Yes |
| Production IdP with TLS, hardened realm and enforced MFA | U4 | Yes |
| KMS/HSM for master and signing keys | U5 | Strongly recommended |
| Scheduled export of signed audit checkpoints and backups to write-once off-platform storage | U6 | Yes |
| DBA separation; superuser access restricted | U7 | Yes |
| Gateway or distributed rate limiting | U8 | Recommended at scale |
| Separate database for LAB environments | U11 | Recommended |
| Image vulnerability scan in CI and base images pinned by digest | U12 | Yes. See the ledger for what was performed locally |
| Cross-source identity correlation design | U3 | Before connecting more than one real source |
| Real connectors (each separately approved) | ROADMAP 16 | Out of scope; only mock and sandbox providers exist |
| Capacity: multi-worker sizing, pagination of large lineage responses | Phase 19 limitations | Measure on target hardware |

The project performs no real IAM changes and connects to no production systems. AI output is advisory and has no execution authority.
