from __future__ import annotations

import json
from pathlib import Path

from scripts.nerd.autonomous.agency_delivery import run_delivery

FAKE_SCREENSHOT_PNG = (
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082"
)


def _write_fake_browser(path: Path, *, write_png: bool = True, exit_code: int = 0) -> Path:
    png_line = (
        f"Path(screenshot).write_bytes(bytes.fromhex('{FAKE_SCREENSHOT_PNG}'))"
        if write_png
        else "pass"
    )
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "from pathlib import Path",
                "screenshot = ''",
                "for arg in sys.argv[1:]:",
                "    if arg.startswith('--screenshot='):",
                "        screenshot = arg.split('=', 1)[1]",
                "if screenshot:",
                f"    {png_line}",
                f"raise SystemExit({exit_code})",
                "",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_offline_landing_delivery_writes_artifacts_and_brain_store(tmp_path):
    result = run_delivery(
        "Create a landing page for an autonomous agency command desk.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
        browser_smoke=False,
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
        browser_smoke=False,
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
        browser_smoke=False,
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
    assert run_record["next_action"] == "configure_deploy_target"
    assert run_record["model"]["status"] in {"skipped", "fallback", "success"}
    assert run_record["verification"]["request_captured"] == "passed"
    assert run_record["verification"]["artifacts_written"] == "passed"
    assert run_record["verification"]["html_smoke"] == "passed"
    assert run_record["verification"]["asset_smoke"] == "passed"
    assert run_record["verification"]["browser_smoke"] == "not_run"
    assert run_record["verification"]["deploy_smoke"] == "blocked_missing_deployment_target"
    assert run_record["deployment"]["status"] == "deployment_ready"
    assert run_record["deployment"]["target_metadata"] == "missing"
    assert run_record["blocker"] == "Deployment target metadata is not configured."
    assert result["next_action"] == "configure_deploy_target"
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
        browser_smoke=False,
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
        browser_smoke=False,
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
        browser_smoke=False,
        auto_deploy=True,
    )

    run_record = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))

    assert run_record["task_id"].startswith("task_")
    assert result["task_id"] == run_record["task_id"]
    assert result["next_action"] == run_record["next_action"]


def test_landing_delivery_runs_browser_smoke_with_configured_command(
    tmp_path, monkeypatch
):
    fake_browser = _write_fake_browser(tmp_path / "fake-browser")
    monkeypatch.setenv("NERD_BROWSER_COMMAND", str(fake_browser))

    result = run_delivery(
        "Create a landing page for NERD agency browser smoke.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
        no_intake=True,
        browser_smoke=True,
        auto_deploy=False,
    )

    run_record = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))
    screenshot_path = Path(run_record["browser_smoke_artifact"])

    assert run_record["status"] == "success"
    assert run_record["verification"]["browser_smoke"] == "passed"
    assert screenshot_path.is_file()
    assert screenshot_path in {Path(path) for path in run_record["artifact_paths"]}
    assert result["verification"]["browser_smoke"] == "passed"


def test_landing_delivery_marks_missing_browser_as_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("NERD_BROWSER_COMMAND", str(tmp_path / "missing-browser"))

    result = run_delivery(
        "Create a landing page for NERD agency browser smoke.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
        no_intake=True,
        browser_smoke=True,
        auto_deploy=False,
    )

    run_record = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))

    assert run_record["status"] == "partial"
    assert run_record["verification"]["browser_smoke"] == "blocked_missing_browser"
    assert run_record["next_action"] == "configure_browser"
    assert run_record["blocker"] == "Browser smoke is blocked until browser tooling is available."
    assert "browser_smoke_artifact" not in run_record


def test_landing_delivery_auto_promotes_to_configured_static_target(tmp_path):
    public_root = tmp_path / "public-deliveries"
    targets_path = tmp_path / "system" / "deployment-targets.json"
    targets_path.parent.mkdir(parents=True)
    targets_path.write_text(
        json.dumps(
            {
                "schema_version": "nerd.deployment_targets.v1",
                "default_static_target": "unit-static",
                "targets": [
                    {
                        "id": "unit-static",
                        "provider": "nginx_static",
                        "status": "configured",
                        "artifact_kind": "static_site",
                        "local_root": str(public_root),
                        "public_base_url": "https://example.test/deliveries",
                        "auto_promote": True,
                        "credentials": "not_required",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_delivery(
        "Create a landing page for NERD agency public deployment.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
        no_intake=True,
        browser_smoke=False,
        auto_deploy=True,
    )

    run_record = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))
    public_site = public_root / result["run_id"] / "index.html"
    public_asset_dir = public_root / result["run_id"] / "assets"
    public_hero = public_asset_dir / "hero.png"

    assert public_site.is_file()
    assert oct((public_root / result["run_id"]).stat().st_mode & 0o777) == "0o755"
    assert oct(public_asset_dir.stat().st_mode & 0o777) == "0o755"
    assert oct(public_site.stat().st_mode & 0o777) == "0o644"
    assert oct(public_hero.stat().st_mode & 0o777) == "0o644"
    assert run_record["deployment"] == {
        "status": "deployed",
        "target_id": "unit-static",
        "provider": "nginx_static",
        "public_url": f"https://example.test/deliveries/{result['run_id']}/",
        "credentials": "not_required",
    }
    assert result["deployment"] == run_record["deployment"]
    assert result["next_action"] == "review_public_url"


def test_landing_delivery_does_not_auto_promote_by_default(tmp_path):
    public_root = tmp_path / "public-deliveries"
    targets_path = tmp_path / "system" / "deployment-targets.json"
    targets_path.parent.mkdir(parents=True)
    targets_path.write_text(
        json.dumps(
            {
                "schema_version": "nerd.deployment_targets.v1",
                "default_static_target": "unit-static",
                "targets": [
                    {
                        "id": "unit-static",
                        "provider": "nginx_static",
                        "status": "configured",
                        "artifact_kind": "static_site",
                        "local_root": str(public_root),
                        "public_base_url": "https://example.test/deliveries",
                        "auto_promote": True,
                        "credentials": "not_required",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_delivery(
        "Create a landing page for NERD agency deployment-ready handoff.",
        canonical_root=tmp_path,
        output_root=tmp_path / "deliveries",
        source="test",
        offline=True,
        no_intake=True,
        browser_smoke=False,
    )

    run_record = json.loads(Path(result["paths"]["run"]).read_text(encoding="utf-8"))

    assert not public_root.exists()
    assert run_record["deployment"] == {
        "status": "target_configured",
        "target_id": "unit-static",
        "provider": "nginx_static",
        "credentials": "not_required",
    }
    assert run_record["verification"]["deploy_smoke"] == "not_run"
    assert result["next_action"] == "review_or_deploy"
