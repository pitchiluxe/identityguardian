"""Phase 13 unit checks: allowlisted intents, claim validation, endpoint policy."""

import pytest

from apps.api.app.ai import intents
from apps.api.app.ai.provider import validate_endpoint
from apps.api.app.ai.validate import validate

IDS = {"erick mensah": "idn-erick", "erick": "idn-erick", "tom becker": "idn-tom", "tom": "idn-tom"}
TARGETS = {"payroll · simulated": "res-payroll", "payroll": "res-payroll", "erp": "app-erp"}


@pytest.mark.parametrize(
    "question,name",
    [
        ("What can Erick access?", "effective_access"),
        ("Why does Erick have access to payroll?", "lineage"),
        ("Who can access payroll?", "who_can_access"),
        ("Show ownerless service accounts", "ownerless_machines"),
        ("Any dormant admins?", "dormant_admins"),
        ("What exposure paths start from Erick?", "exposure_paths"),
        ("Does Erick keep access from his previous role?", "prior_role_access"),
        ("Who is Tom?", "identity_status"),
    ],
)
def test_supported_intents(question, name):
    assert intents.parse(question, IDS, TARGETS).name == name


@pytest.mark.parametrize(
    "question",
    [
        "Delete Erick's payroll access",
        "Run SQL to list users",
        "Show Erick's password",
        "Approve the pending change",
        "What is the weather?",
        "Compare Erick and Tom",
    ],
)
def test_unsupported_or_mutating_requests_need_clarification(question):
    assert isinstance(intents.parse(question, IDS, TARGETS), intents.Clarification)


FACTS = [
    dict(
        id="F1",
        text="Erick Mensah has ALLOW access to Payroll · SIMULATED via Finance-Legacy; "
        "ticket TKT-1042.",
        evidence_ids=["e1"],
    ),
    dict(
        id="F2",
        text="Observed uses of Payroll · SIMULATED by Erick Mensah: 0 within telemetry coverage.",
        evidence_ids=["e2"],
    ),
]
CATALOG = {"erick mensah", "tom becker", "payroll · simulated", "finance-legacy"}


def test_validator_accepts_grounded_and_rejects_fabrication():
    output = {
        "insufficient_evidence": False,
        "claims": [
            {
                "text": "Erick Mensah can configure payroll through Finance-Legacy (TKT-1042).",
                "type": "fact",
                "citations": ["F1"],
            },
            {
                "text": "Erick Mensah used payroll 0 times in coverage.",
                "type": "fact",
                "citations": ["F2"],
            },
            {"text": "Erick Mensah has 7 routes to payroll.", "type": "fact", "citations": ["F1"]},
            {"text": "Tom Becker also has access.", "type": "fact", "citations": ["F1"]},
            {"text": "Remove the grant.", "type": "recommendation", "citations": ["F9"]},
            {"text": "Erick is risky.", "type": "inference", "citations": []},
            {"text": "x", "type": "opinion", "citations": ["F1"]},
        ],
    }
    accepted, rejected = validate(output, FACTS, CATALOG)
    assert [a["text"][:19] for a in accepted] == ["Erick Mensah can co", "Erick Mensah used p"]
    reasons = " | ".join(r["reason"] for r in rejected)
    for expected in [
        "Unsupported number",
        "Names not in cited evidence",
        "Citation not in evidence",
        "Uncited claim",
        "Unknown claim type",
    ]:
        assert expected in reasons
    schema_error = [dict(claim=None, reason="Output does not match the required schema")]
    assert validate("not json", FACTS, CATALOG) == ([], schema_error)


def test_model_endpoint_policy():
    validate_endpoint("http://127.0.0.1:11434", "qwen2.5:7b", set())
    with pytest.raises(ValueError):
        validate_endpoint("http://169.254.169.254", "qwen2.5:7b", set())
    with pytest.raises(ValueError):
        validate_endpoint("http://127.0.0.1:11434", "deepseek-v4-pro:cloud", set())
    with pytest.raises(ValueError):
        validate_endpoint("http://127.0.0.1:11434", "gemma4:31b-cloud", set())
