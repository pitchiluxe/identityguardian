"""Phase 19 benchmark: 10,000 identities / ~100,000 relationships of SYNTHETIC data.

Creates a dedicated SANDBOX environment in the bootstrapped organization, bulk-loads the sandbox
source, ingests it through the normal pipeline, then measures engine and HTTP latencies.
Results (with hardware details) are written to docs/performance/. Local development only.

The HTTP phase sends more reads than the default per-user quota (60/min) allows; start the API
for benchmarking with a raised quota, e.g. READ_LIMIT_PER_MINUTE=100000. `--reuse` measures the
most recent benchmark environment again instead of loading and ingesting a new copy.
"""

import argparse
import ctypes
import json
import os
import platform
import random
import secrets
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from apps.api.app.db import Database
from apps.api.app.domain import graph
from apps.api.app.domain.access import effective_access, principals_for
from apps.api.app.domain.exposure import attack_paths
from apps.api.app.domain.ingest import run_sync
from apps.api.app.security import digest
from packages.fixtures.scale import build

ROOT = Path(__file__).resolve().parents[1]
ORG = UUID("10000000-0000-4000-8000-000000000001")


def percentiles(samples):
    ordered = sorted(samples)

    def pick(p):
        return round(
            ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))] * 1000, 1
        )

    return dict(
        n=len(ordered),
        p50_ms=pick(50),
        p95_ms=pick(95),
        p99_ms=pick(99),
        mean_ms=round(statistics.mean(ordered) * 1000, 1),
        max_ms=round(max(ordered) * 1000, 1),
    )


def hardware():
    class Memory(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("load", ctypes.c_ulong),
            ("total", ctypes.c_ulonglong),
            ("avail", ctypes.c_ulonglong),
            ("tp", ctypes.c_ulonglong),
            ("ap", ctypes.c_ulonglong),
            ("tv", ctypes.c_ulonglong),
            ("av", ctypes.c_ulonglong),
            ("ae", ctypes.c_ulonglong),
        ]

    total = None
    if platform.system() == "Windows":
        memory = Memory()
        memory.length = ctypes.sizeof(Memory)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
        total = round(memory.total / 2**30, 1)
    return dict(
        os=platform.platform(),
        processor=platform.processor(),
        logical_cpus=os.cpu_count(),
        ram_gib=total,
        python=platform.python_version(),
    )


def load_source(url, env, objects):
    with psycopg.connect(url) as conn:
        with conn.cursor().copy(
            "COPY sandbox_objects(organization_id,environment_id,object_id,object_type,"
            "body,version) FROM STDIN"
        ) as copy:
            for i, obj in enumerate(objects, 1):
                copy.write_row((ORG, env, obj["id"], obj["type"], Jsonb(obj), i))
        conn.execute(
            "SELECT setval('sandbox_version_seq', greatest((SELECT max(version) FROM sandbox_objects), "
            "(SELECT last_value FROM sandbox_version_seq)))"
        )


def http_load(base, token, csrf, identities, concurrency, requests):
    def one(external):
        started = time.perf_counter()
        response = client.get(f"{base}/identities/{external}/access")
        response.raise_for_status()
        return time.perf_counter() - started

    with httpx.Client(timeout=60, cookies={"ig_session": token}) as client:
        client.get(f"{base}/identities/{identities[0]}/access").raise_for_status()  # warm
        picks = [random.choice(identities) for _ in range(requests)]
        with ThreadPoolExecutor(concurrency) as pool:
            return list(pool.map(one, picks))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--identities", type=int, default=10_000)
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--http", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--reuse", action="store_true", help="reuse latest benchmark environment")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    migration, runtime = os.environ["MIGRATION_DATABASE_URL"], os.environ["DATABASE_URL"]
    random.seed(11)
    results = dict(
        date=datetime.now(timezone.utc).isoformat(), hardware=hardware(), parameters=vars(args)
    )
    env = uuid4()
    with psycopg.connect(migration) as conn:
        results["postgres"] = conn.execute("SHOW server_version").fetchone()[0]
        if args.reuse:
            env = conn.execute(
                "SELECT e.id FROM environments e JOIN sync_runs s ON s.environment_id=e.id "
                "WHERE e.organization_id=%s AND e.kind='SANDBOX' AND s.status='SUCCEEDED' "
                "AND e.name LIKE 'Scale benchmark %%' ORDER BY s.finished_at DESC LIMIT 1",
                (ORG,),
            ).fetchone()[0]
        else:
            conn.execute(
                "INSERT INTO environments(id,organization_id,name,kind) VALUES(%s,%s,%s,'SANDBOX')",
                (env, ORG, f"Scale benchmark {datetime.now(timezone.utc):%Y-%m-%d %H:%M}"),
            )
    objects = build(identities=args.identities)
    results["dataset"] = dict(
        objects=len(objects),
        relationships=sum(o["type"] == "relationship" for o in objects),
        nodes=sum(o["type"] == "node" for o in objects),
    )
    db = Database(runtime, max_size=12)
    if args.reuse:
        results["ingest"] = dict(reused_environment=str(env))
    else:
        started = time.perf_counter()
        load_source(migration, env, objects)
        results["bulk_source_load_s"] = round(time.perf_counter() - started, 1)
        started = time.perf_counter()
        with db.transaction(ORG) as conn:
            environment = conn.execute("SELECT * FROM environments WHERE id=%s", (env,)).fetchone()
            run = run_sync(conn, environment, None, full=True)
        elapsed = time.perf_counter() - started
        results["ingest"] = dict(
            seconds=round(elapsed, 1),
            objects_per_second=round(run["observed"] / elapsed),
            status=run["status"],
            created=run["created"],
            rejected=run["rejected"],
        )
    print("ingested", results["ingest"], flush=True)
    started = time.perf_counter()
    with psycopg.connect(migration, autocommit=True) as conn:
        for table in (
            "twin_nodes",
            "node_revisions",
            "relationships",
            "relationship_revisions",
            "observations",
        ):
            conn.execute(f"ANALYZE {table}")  # noqa: S608 - fixed table names
    results["analyze_s"] = round(time.perf_counter() - started, 1)

    with db.transaction(ORG) as conn:
        cold = []
        for _ in range(3):
            t0 = time.perf_counter()
            snap = graph.load(conn, env, use_cache=False)
            cold.append(time.perf_counter() - t0)
        results["snapshot_load_uncached"] = percentiles(cold)
        warm = []
        graph.load(conn, env)
        for _ in range(10):
            t0 = time.perf_counter()
            snap = graph.load(conn, env)
            warm.append(time.perf_counter() - t0)
        results["snapshot_load_cached"] = percentiles(warm)
        results["snapshot"] = dict(nodes=len(snap.nodes), edges=len(snap.edges))
        identities = [n.id for n in snap.nodes.values() if n.kind == "identity"]
        externals = [snap.nodes[i].external_id for i in identities]
        timings, partial = [], 0
        for identity in random.sample(identities, args.samples):
            t0 = time.perf_counter()
            result = effective_access(snap, identity, conn)
            timings.append(time.perf_counter() - t0)
            partial += not result["complete"]
        results["effective_access"] = dict(percentiles(timings), partial_results=partial)
        resources = [n.id for n in snap.nodes.values() if n.kind == "resource"]
        timings, partial = [], 0
        for resource in random.sample(resources, 20):
            t0 = time.perf_counter()
            result = principals_for(snap, resource)
            timings.append(time.perf_counter() - t0)
            partial += not result["complete"]
        results["who_can_access"] = dict(percentiles(timings), partial_results=partial)
        timings = []
        for identity in random.sample(identities, 20):
            t0 = time.perf_counter()
            graph.neighborhood(snap, identity, 2, 150)
            timings.append(time.perf_counter() - t0)
        results["neighbourhood_depth2"] = percentiles(timings)
        t0 = time.perf_counter()
        exposure = attack_paths(snap, conn, identities[0], None, 2, 100)
        results["attack_paths_single_source"] = dict(
            seconds=round(time.perf_counter() - t0, 2),
            complete=exposure["complete"],
            paths=len(exposure["paths"]),
        )

    user, token = uuid4(), secrets.token_urlsafe(32)
    csrf = digest("csrf:" + token)
    with psycopg.connect(migration) as conn:
        conn.execute(
            "INSERT INTO users VALUES(%s,'benchmark',%s,'Benchmark Investigator')", (user, user)
        )
        conn.execute(
            "INSERT INTO memberships(organization_id,user_id,roles) VALUES(%s,%s,%s)",
            (ORG, user, ["investigator"]),
        )
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at,auth_time,amr) "
            "VALUES(%s,%s,%s,now()+interval '30 minutes',%s,ARRAY['pwd'])",
            (digest(token), user, digest(csrf), time.time()),
        )
    try:
        base = f"{args.http}/api/v1/organizations/{ORG}/environments/{env}"
        started = time.perf_counter()
        samples = http_load(base, token, csrf, externals, args.concurrency, args.requests)
        wall = time.perf_counter() - started
        results["http_effective_access"] = dict(
            percentiles(samples),
            concurrency=args.concurrency,
            throughput_rps=round(len(samples) / wall, 1),
        )
    except httpx.HTTPStatusError as exc:
        results["http_effective_access"] = dict(error=f"HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        results["http_effective_access"] = dict(error=f"{type(exc).__name__}: API not reachable")
    finally:
        with psycopg.connect(migration) as conn:
            conn.execute("DELETE FROM sessions WHERE user_id=%s", (user,))
            conn.execute("UPDATE memberships SET active=false WHERE user_id=%s", (user,))
    db.close()
    out = ROOT / "docs" / "performance"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"benchmark-{datetime.now(timezone.utc):%Y%m%dT%H%M}Z.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    print(json.dumps(results, indent=2, default=str))
    print("written", path)


if __name__ == "__main__":
    main()
