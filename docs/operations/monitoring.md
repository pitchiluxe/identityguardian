# Monitoring runbook

## Probes

| Endpoint | Meaning | Database | Exposure |
|---|---|---|---|
| `GET /api/v1/health` | Liveness: the process answers | No | Public; returns `{"status":"ok"}` only |
| `GET /api/v1/ready` | Readiness: database reachable and every shipped migration applied | One count query | Internal; the proxy answers 404 from outside. Returns 503 with a fixed reason (`database unavailable` or `migrations pending`) and no connection details |

Both probes are exempt from per-user rate limits, so orchestrator polling cannot exhaust a user's quota.

The worker has no HTTP port. It touches `WORKER_HEARTBEAT_FILE` after every loop, and its healthcheck fails when the file is older than 60 s.

## Logs

`LOG_FORMAT=json` (the image default) writes one JSON object per line with `time` (UTC), `level`, `logger`, `message`, `correlation_id` (on request errors) and `exception`. Every API response carries `X-Correlation-ID`, so match a user-reported ID against the logs. Database errors are logged with their correlation ID, and clients receive only a generic 503.

## Operator status

```
docker compose -f infra/compose.production.yaml run --rm migrate python scripts/manage.py status --verify-audit
```

The status command prints counts only, never tenant content: applied and missing migrations, outbox backlog, age of the oldest pending event, events retried five or more times, and organizations whose audit hash chain is broken. It exits 1 on any problem, so it can drive an alert.

| Signal | Suggested alert | First action |
|---|---|---|
| `/api/v1/ready` 503 for more than 2 min | Page | Check the `postgres` health, then `migrate` exit status |
| `outbox_oldest_pending_seconds` above 300 | Ticket | Worker health and logs. Leases expire after 30 s, so a crashed worker's events are re-delivered |
| `outbox_retrying_events` above 0 | Ticket | Search the worker logs for the organization and correlation |
| `audit_chains_broken` not empty | Security incident | Preserve the database. Compare with exported signed checkpoints (U6) |
| Proxy 413/429 spike | Watch | Possible abuse. Rate limits are per application database (U8) |

No metrics backend is bundled. The probes, JSON logs and status exit code are the integration points.
