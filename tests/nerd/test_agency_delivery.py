from __future__ import annotations

import json
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


def test_offline_landing_delivery_uses_nerd_palette3_visual_system(tmp_path):
    result = run_delivery(
        "Создай лендос для агентства NERD, которое показывает автономные задачи, деплой и второй мозг.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
    )

    html = Path(result["paths"]["site"]).read_text(encoding="utf-8")
    html_lower = html.lower()

    assert "#080b11" in html_lower
    assert "#22c55e" in html_lower
    assert "#6d50b6" in html_lower
    assert "--paper" not in html_lower
    assert "#f6f0e6" not in html_lower
    assert "#fffaf0" not in html_lower
    assert "coral" not in html_lower
    assert "delivery criteria" in html_lower


def test_delivery_run_record_contains_verification_and_idempotency_metadata(tmp_path):
    result = run_delivery(
        (
            "Create a NERD agency landing page. "
            "api_key=sk-test-secret-value password=do-not-render "
            "Authorization: Bearer abc.def.ghi"
        ),
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
    )

    run_record = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))
    serialized = json.dumps(run_record, ensure_ascii=False)

    assert run_record["id"] == result["run_id"]
    assert run_record["kind"] == "agency_delivery"
    assert run_record["status"] == "success"
    assert run_record["task_id"]
    assert run_record["artifact_paths"]
    assert run_record["site_path"]
    assert run_record["idempotency_key"]
    assert run_record["next_action"] == "review_or_deploy"
    assert run_record["model"]["status"] in {"skipped", "fallback", "success"}
    assert run_record["verification"]["request_captured"] == "passed"
    assert run_record["verification"]["artifacts_written"] == "passed"
    assert run_record["verification"]["html_smoke"] == "passed"
    assert run_record["verification"]["asset_smoke"] == "passed"
    assert run_record["verification"]["browser_smoke"] == "not_run"
    assert result["next_action"] == "review_or_deploy"
    assert "sk-test-secret-value" not in serialized
    assert "do-not-render" not in serialized
    assert "abc.def.ghi" not in serialized
    assert "Bearer" not in serialized


def test_delivery_dry_run_reports_planned_verification_without_writes(tmp_path):
    result = run_delivery(
        "Prepare an implementation plan for a repo cleanup.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        offline=True,
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["mode"] == "implementation"
    assert result["model"]["status"] == "skipped"
    assert result["verification"]["request_captured"] == "planned"
    assert result["verification"]["artifacts_written"] == "planned"
    assert result["verification"]["html_smoke"] == "not_applicable"
    assert result["verification"]["asset_smoke"] == "not_applicable"
    assert result["verification"]["browser_smoke"] == "not_run"
    assert result["idempotency_key"]
    assert result["next_action"] == "review_or_run"
    assert not (tmp_path / "deliveries").exists()


def test_landing_without_static_site_marks_site_smoke_not_applicable(tmp_path):
    result = run_delivery(
        "Create a landing page for NERD agency but skip static site generation.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
        build_static_site=False,
    )

    run_record = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))

    assert run_record["status"] == "success"
    assert run_record["site_path"] is None
    assert run_record["verification"]["html_smoke"] == "not_applicable"
    assert run_record["verification"]["asset_smoke"] == "not_applicable"
    assert run_record["next_action"] == "review_artifacts"
    assert result["next_action"] == "review_artifacts"


def test_delivery_synthesizes_task_id_when_intake_disabled(tmp_path):
    result = run_delivery(
        "Prepare an implementation plan for NERD agency delivery records.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
        no_intake=True,
    )

    run_record = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))

    assert run_record["task_id"].startswith("task_")
    assert result["task_id"] == run_record["task_id"]
    assert result["next_action"] == run_record["next_action"]
