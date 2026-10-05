"""Phase 22: the shell ships no planned-feature placeholders, and demo wording is dev-only."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "apps" / "web" / "src"
# Development-only or training-by-design files; everything else must be production-clean.
DEV_ONLY = {"DevTools.tsx", "Labs.tsx"}
DEMO = re.compile(r"synthetic|contoso|\bErick\b|fixture", re.I)


def test_no_planned_placeholders_in_web_source():
    text = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.tsx"))
    for needle in ("nav-planned", "is planned", "scheduled for Phase", "Planned for Phase"):
        assert needle not in text, needle


def test_demo_wording_is_gated_by_development_mode():
    for path in SRC.rglob("*.tsx"):
        if path.name in DEV_ONLY:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.strip()
            if code.startswith("//") or "attributes.synthetic" in code:
                continue  # comments, and tags driven by the data's own synthetic flag
            if DEMO.search(code):
                assert re.search(r"\bdev\b", code), (
                    f"{path.name}:{number} demo wording without dev gate"
                )


def test_missing_mode_is_treated_as_production():
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "mode === 'development'" in app and "mode !== 'production'" not in app
