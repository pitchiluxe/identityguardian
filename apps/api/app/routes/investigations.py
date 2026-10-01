"""Phase 13: grounded natural-language investigator (read-only, advisory)."""

import time
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..ai import intents
from ..ai.planner import CAPABILITY, plan
from ..ai.provider import ProviderUnavailable
from ..ai.validate import SCHEMA, prompt, validate
from ..jsonutil import dumps
from ..jsonutil import jsonb as Jsonb
from ..scope import envelope, scoped
from ..security import digest
from .twin import ENV, snapshot_for

router = APIRouter(prefix="/api/v1/organizations/{org}")


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=4, max_length=500)
    use_model: bool = True


def ai_quota(scope, settings):
    window = int(time.time() // 60)
    bucket = digest(f"ai:{scope.user_id}") + "ai"
    count = scope.conn.execute(
        "INSERT INTO rate_limits VALUES(%s,%s,1) ON CONFLICT(bucket) DO UPDATE SET window_id=excluded.window_id,"
        "count=CASE WHEN rate_limits.window_id=excluded.window_id THEN rate_limits.count+1 ELSE 1 END "
        "RETURNING count",
        (bucket, window),
    ).fetchone()["count"]
    if count > settings.ai_limit_per_minute:
        raise HTTPException(429, "AI investigation limit reached; retry shortly")


def catalog(snap):
    names = {
        n.name.lower(): n.external_id
        for n in snap.nodes.values()
        if n.kind in {"identity", "application", "resource", "group", "role", "tool"}
    }
    identities = {
        n.name.lower(): n.external_id for n in snap.nodes.values() if n.kind == "identity"
    }
    identities.update(
        {
            n.external_id.removeprefix("idn-"): n.external_id
            for n in snap.nodes.values()
            if n.kind == "identity"
        }
    )
    targets = {k: v for k, v in names.items() if not v.startswith("idn-")}
    for node in snap.nodes.values():  # short aliases: "payroll" for "Payroll · SIMULATED", "erp"
        if node.kind in {"application", "resource", "tool"}:
            targets.setdefault(node.name.split(" · ")[0].lower(), node.external_id)
            targets.setdefault(
                node.external_id.split("-", 1)[-1].replace("-", " "), node.external_id
            )
    return names, identities, targets


def summary(bundle):
    return [
        dict(text=f["text"], type="fact", citations=[f["id"]], evidence_ids=f["evidence_ids"])
        for f in bundle["facts"]
    ]


@router.post(ENV + "/investigations/query")
def investigate(org: UUID, env: UUID, body: Question, request: Request):
    settings, provider = request.app.state.settings, request.app.state.llm
    with scoped(request, org, env, "investigation:run") as scope:
        ai_quota(scope, settings)
        snap = snapshot_for(scope)
        names, identities, targets = catalog(snap)
        parsed = intents.parse(body.question, identities, targets)
        record = dict(
            question=body.question,
            model=None,
            model_version=None,
            latency_ms=None,
            claims=[],
            rejected=[],
        )
        if isinstance(parsed, intents.Clarification):
            result = dict(
                record,
                status="CLARIFICATION",
                clarification=parsed.reason,
                supported_intents=parsed.supported,
                intent=None,
                bundle=None,
            )
            store(scope, result, {"clarification": parsed.reason}, {})
            return envelope(scope, result)
        needed = CAPABILITY[parsed.name]
        if needed not in scope.caps:
            raise HTTPException(403, f"Your role cannot run '{parsed.name}' investigations")
        bundle = plan(parsed, snap, scope.conn, scope.env_id).as_dict()
        intent = dict(name=parsed.name, params=parsed.params)
        deterministic = summary(bundle)
        status, claims, rejected = "FALLBACK", deterministic, []
        reason = None
        if not bundle["facts"]:
            status, claims = "INSUFFICIENT", []
        elif not body.use_model:
            reason = "Model explanation not requested"
        elif provider is None:
            status, reason = "AI_UNAVAILABLE", request.app.state.llm_error or "AI disabled"
        else:
            try:
                output, latency = provider.complete(prompt(body.question, bundle), SCHEMA)
                record.update(
                    model=f"{provider.name}:{provider.model}",
                    model_version=provider.version(),
                    latency_ms=latency,
                )
                accepted, rejected = validate(output, bundle["facts"], set(names))
                if accepted:
                    status = "VALIDATED" if not rejected else "PARTIAL"
                    claims = accepted
                elif output.get("insufficient_evidence"):
                    status, reason = "INSUFFICIENT", "Model reported insufficient evidence"
                    claims = deterministic
                else:
                    reason = "All model claims failed validation; showing the deterministic evidence summary"
            except ProviderUnavailable as exc:
                status, reason = "AI_UNAVAILABLE", f"AI unavailable ({exc}); evidence summary shown"
        result = dict(
            record,
            status=status,
            intent=intent,
            bundle=bundle,
            claims=claims,
            rejected=rejected,
            note=reason,
            disclosure="Advisory. Claims cite deterministic evidence; citation validity does "
            "not prove semantic truth. The model cannot change access.",
        )
        store(scope, result, intent, bundle)
        return envelope(
            scope,
            result,
            snapshot=snap,
            completeness="complete" if bundle["complete"] else "partial",
            evidence_ids=[e for f in bundle["facts"] for e in f["evidence_ids"]],
        )


def store(scope, result, intent, bundle):
    scope.conn.execute(
        "INSERT INTO investigations(id,organization_id,environment_id,user_id,question,intent,bundle_digest,"
        "bundle,status,model,model_version,latency_ms,claims,rejected) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            uuid4(),
            scope.org,
            scope.env_id,
            scope.user_id,
            result["question"],
            Jsonb(intent),
            digest(dumps(bundle)),
            Jsonb(bundle),
            result["status"],
            result["model"],
            result["model_version"],
            result["latency_ms"],
            Jsonb(result["claims"]),
            Jsonb(result["rejected"]),
        ),
    )


@router.get(ENV + "/investigations")
def history(org: UUID, env: UUID, request: Request):
    with scoped(request, org, env, "investigation:run") as scope:
        return envelope(
            scope,
            scope.conn.execute(
                "SELECT id, question, status, model, model_version, latency_ms, created_at FROM investigations "
                "WHERE environment_id=%s AND user_id=%s ORDER BY created_at DESC LIMIT 20",
                (env, scope.user_id),
            ).fetchall(),
        )
