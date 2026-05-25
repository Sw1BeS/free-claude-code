from __future__ import annotations


def test_autonomous_core_report_contains_canonical_root(tmp_path):
    from scripts.nerd.inventory.autonomous_core import build_autonomous_core_report

    report = build_autonomous_core_report(tmp_path)
    ids = {item.id for item in report.items}

    assert "autonomous-core-canonical-root" in ids
    assert any(item.domain == "autonomous-core" for item in report.items)
    assert "autonomous-core-runtime-integrations" in ids


def test_autonomous_core_report_marks_high_risk_lab_gated(tmp_path):
    from scripts.nerd.inventory.autonomous_core import build_autonomous_core_report

    report = build_autonomous_core_report(tmp_path)
    lab_item = next(item for item in report.items if item.id == "autonomous-core-lab")

    assert lab_item.risk == "high"
    assert lab_item.recommended_action == "review_later"
    assert lab_item.classification == "high-risk-disabled"
