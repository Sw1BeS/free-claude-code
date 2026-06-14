from __future__ import annotations

from pathlib import Path

from scripts.nerd.autonomous.agency_delivery import run_delivery


def test_offline_landing_delivery_writes_artifacts_and_brain_store(tmp_path):
    result = run_delivery(
        "Create a landing page for an autonomous agency command desk.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
    )

    assert result["status"] == "success"
    assert result["mode"] == "landing_page"
    assert Path(result["paths"]["run"]).is_file()
    assert Path(result["paths"]["site"]).is_file()
    assert (Path(result["paths"]["site"]).parent / "assets" / "hero.png").is_file()
    assert Path(result["intake"]["inbox_path"]).is_file()
    assert Path(result["intake"]["task_path"]).is_file()
    assert (tmp_path / "brain" / "brain.sqlite").is_file()
    assert (tmp_path / "memory" / "runs" / "agency-deliveries.jsonl").is_file()


def test_delivery_dry_run_does_not_write_artifacts(tmp_path):
    result = run_delivery(
        "Prepare an implementation plan for a repo cleanup.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        offline=True,
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["mode"] == "implementation"
    assert not (tmp_path / "deliveries").exists()
