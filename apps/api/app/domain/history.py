"""Time Machine (DATABASE.md "History").

effective_at = when access applied at the source; known_at = what the platform knew then.
`effective_at=t, known_at=now` is best current knowledge of the past; `known_at=k` is what was
known at k. Missing history is UNKNOWN: current state is never projected backward.
"""

from datetime import datetime, timezone

from ..jsonutil import dumps
from ..security import digest
from .access import effective_access
from .graph import Snapshot, load, node_json


def checksum(snap: Snapshot) -> str:
    nodes = sorted((n.id, n.name, n.status, dumps(n.attributes)) for n in snap.nodes.values())
    edges = sorted(e.id for e in snap.edges)
    return digest(dumps(dict(nodes=nodes, edges=edges)))


def coverage(conn, environment_id, effective_at, known_at):
    first = conn.execute(
        "SELECT min(received_at) AS first FROM observations WHERE environment_id=%s",
        (environment_id,),
    ).fetchone()["first"]
    earliest = conn.execute(
        "SELECT min(rr.valid_from) AS earliest FROM relationship_revisions rr JOIN relationships r "
        "ON r.id=rr.relationship_id WHERE r.environment_id=%s AND rr.recorded_from<=%s",
        (environment_id, known_at),
    ).fetchone()["earliest"]
    runs = conn.execute(
        "SELECT finished_at, status, coverage, rejected FROM sync_runs WHERE environment_id=%s "
        "AND finished_at<=%s ORDER BY finished_at DESC LIMIT 20",
        (environment_id, known_at),
    ).fetchall()
    usage = conn.execute(
        "SELECT t.name AS target, c.covered_from, c.covered_to, c.completeness FROM usage_coverage c "
        "JOIN twin_nodes t ON t.id=c.target_node WHERE c.environment_id=%s AND c.covered_from<=%s "
        "AND c.covered_to>%s",
        (environment_id, effective_at, effective_at),
    ).fetchall()
    notes = []
    if not runs:
        notes.append("Nothing had been ingested by the knowledge time: every answer is UNKNOWN.")
    elif runs[0]["coverage"] != "complete_authoritative":
        notes.append(
            "The latest sync before the knowledge time was partial; absences are not proof."
        )
    if any(r["status"] != "SUCCEEDED" for r in runs):
        notes.append("Some syncs before the knowledge time were partial or rejected records.")
    if earliest and effective_at < earliest:
        notes.append(
            f"The effective time precedes the earliest source evidence ({earliest.date()}): "
            "state at that time is UNKNOWN."
        )
    if first and known_at < first:
        notes.append("The knowledge time precedes the first observation in this environment.")
    if not usage:
        notes.append("No usage telemetry covers the effective time; usage is UNKNOWN.")
    return dict(
        first_observation=first,
        earliest_effective_evidence=earliest,
        syncs_before_known_at=runs,
        usage_coverage_at_effective_time=usage,
        notes=notes,
    )


def _entries(snap, identity, conn):
    if identity not in snap.nodes:
        return None
    return {
        ((e["resource"] or {}).get("id"), (e["permission"] or {}).get("id"), e["action"]): e
        for e in effective_access(snap, identity, conn)["entries"]
    }


def _name(entry):
    target = entry["resource"] or entry["permission"]
    return f"{target['name']} · {entry['permission']['name'] if entry['permission'] else entry['action']}"


def reconstruct(conn, environment_id, external_id, effective_at, known_at):
    now = datetime.now(timezone.utc)
    then = load(conn, environment_id, effective_at, known_at)
    current = load(conn, environment_id, effective_at, now)
    found = then.by_external(external_id) or current.by_external(external_id)
    if found:
        node_id, name = found.id, found.name
    else:  # exists in the twin but not effective at t: report UNKNOWN, never absent
        row = conn.execute(
            "SELECT n.id, r.name FROM twin_nodes n JOIN node_revisions r ON r.node_id=n.id "
            "WHERE n.environment_id=%s AND n.external_id=%s ORDER BY r.recorded_from DESC LIMIT 1",
            (environment_id, external_id),
        ).fetchone()
        if not row:
            raise KeyError(external_id)
        node_id, name = str(row["id"]), row["name"]
    known_then, known_now = _entries(then, node_id, conn), _entries(current, node_id, conn)
    differences = []
    if known_then is not None and known_now is not None:
        for key, entry in known_now.items():
            if key not in known_then:
                late = [
                    h["edge"]
                    for p in entry["paths"]
                    for h in p["hops"]
                    if h["edge"].get("recorded_from")
                    and datetime.fromisoformat(h["edge"]["recorded_from"]) > known_at
                ]
                differences.append(
                    dict(
                        entitlement=_name(entry),
                        kind="LEARNED_LATER",
                        explanation="Evidence recorded after the knowledge time "
                        "(late evidence) shows this access applied.",
                        late_edges=late,
                    )
                )
        for key, entry in known_then.items():
            if key not in known_now:
                differences.append(
                    dict(
                        entitlement=_name(entry),
                        kind="CORRECTED_LATER",
                        explanation="Knowledge at the time showed this access; later "
                        "evidence corrected it.",
                    )
                )

    def view(snap, entries):
        if entries is None:
            return dict(
                status="UNKNOWN",
                reason="No evidence of this identity at the effective time "
                "according to this knowledge.",
                entitlements=[],
            )
        n = snap.nodes[node_id]
        return dict(
            status="KNOWN",
            identity=node_json(n),
            entitlements=[
                dict(
                    entitlement=_name(e),
                    decision=e["decision"],
                    routes=len(e["paths"]),
                    paths=e["paths"],
                )
                for e in sorted(entries.values(), key=_name)
            ],
        )

    return dict(
        identity=dict(external_id=external_id, name=name),
        effective_at=effective_at.isoformat(),
        known_at=known_at.isoformat(),
        timezone="UTC",
        as_known_then=view(then, known_then),
        as_known_now=view(current, known_now),
        differences=differences,
        coverage=coverage(conn, environment_id, effective_at, known_at),
        graph_versions=dict(then=then.version, now=current.version),
    )
