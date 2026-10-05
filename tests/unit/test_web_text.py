"""Phase 22: the shell ships no planned-feature placeholders, and demo wording is dev-only."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "apps" / "web" / "src"


def test_no_planned_placeholders_in_web_source():
    text = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.tsx"))
    for needle in ("nav-planned", "is planned", "scheduled for Phase", "Planned for Phase"):
        assert needle not in text, needle


def test_demo_wording_is_gated_by_development_mode():
    for name in ("App.tsx", "pages/Integrations.tsx", "pages/index.tsx"):
        for number, line in enumerate((SRC / name).read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"synthetic|contoso", line, re.I):
                assert re.search(r"\bdev\b", line), f"{name}:{number} shows demo wording without a dev gate"
