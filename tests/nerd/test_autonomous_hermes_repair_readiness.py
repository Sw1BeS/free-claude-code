from __future__ import annotations

import json


def _items_by_id(registry: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in registry["items"]}  # type: ignore[index]


def test_hermes_repair_readiness_blocks_missing_runtime_bundle_sources(tmp_path):
    from scripts.nerd.autonomous.hermes_repair_readiness import (
        build_hermes_repair_readiness_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    hermes_agent_root = tmp_path / ".hermes" / "hermes-agent"
    runtime_bundle = hermes_agent_root / "ops" / "hermes-evolution"
    archive_bundle = (
        tmp_path
        / "hermes"
        / "archive"
        / "legacy_root"
        / "hermes-evolution-rollback-repo"
    )
    runtime_bundle.mkdir(parents=True)
    (runtime_bundle / "env").mkdir()
    (runtime_bundle / "state").mkdir()
    for relative in (
        "README.md",
        "compose/foundation.compose.yml",
        "runbooks/cutover-gates.md",
        "scripts/bootstrap_layout.sh",
        "scripts/validate_bundle.py",
        "systemd/hermes-evolution-foundation.service",
    ):
        path = archive_bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")

    registry = build_hermes_repair_readiness_registry(
        canonical_root=canonical_root,
        hermes_agent_root=hermes_agent_root,
        runtime_bundle_root=runtime_bundle,
        archive_bundle_root=archive_bundle,
        service_rows=[],
        systemd_link_rows=[],
        docker_rows=[],
    )

    items = _items_by_id(registry)
    layout = items["hermes-runtime-bundle-layout"]
    assert layout["status"] == "blocked"
    assert layout["risk"] == "high"
    assert layout["approval_level"] == "L3"
    assert layout["metadata"]["missing_runtime_paths"] == [
        "README.md",
        "compose",
        "runbooks",
        "scripts/bootstrap_layout.sh",
        "scripts/validate_bundle.py",
        "systemd",
    ]
    assert layout["metadata"]["restart_allowed"] is False
    assert layout["metadata"]["dry_run_commands"] == [
        "python -m scripts.nerd.autonomous.hermes_repair_readiness --check"
    ]
    assert layout["metadata"]["restore_plan"]["apply_requires_approval"] is True
    assert "rsync --dry-run" in layout["metadata"]["restore_plan"]["dry_run_command"]

    source = items["hermes-archive-restore-source"]
    assert source["status"] == "present"
    assert source["metadata"]["source_file_count"] == 6


def test_hermes_repair_readiness_reports_bad_systemd_links_and_missing_scripts(
    tmp_path,
):
    from scripts.nerd.autonomous.hermes_repair_readiness import (
        build_hermes_repair_readiness_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    hermes_agent_root = tmp_path / ".hermes" / "hermes-agent"
    runtime_bundle = hermes_agent_root / "ops" / "hermes-evolution"
    archive_bundle = tmp_path / "archive"
    runtime_bundle.mkdir(parents=True)
    (runtime_bundle / "scripts").mkdir()
    (runtime_bundle / "scripts" / "hermes_webhook_bridge.py").write_text(
        "# bridge\n", encoding="utf-8"
    )
    (archive_bundle / "scripts").mkdir(parents=True)
    (archive_bundle / "scripts" / "agency_department_report.py").write_text(
        "# report\n", encoding="utf-8"
    )

    registry = build_hermes_repair_readiness_registry(
        canonical_root=canonical_root,
        hermes_agent_root=hermes_agent_root,
        runtime_bundle_root=runtime_bundle,
        archive_bundle_root=archive_bundle,
        service_rows=[
            "hermes-webhook.service loaded active running",
            "hermes-agency-department-report.service loaded failed failed",
        ],
        systemd_link_rows=[
            "/etc/systemd/system/hermes-evolution-foundation.service -> "
            f"{runtime_bundle}/systemd/hermes-evolution-foundation.service"
        ],
        docker_rows=[
            "hermes-evolution-foundation-postgres-1 postgres:17-alpine Up 3 weeks (healthy)",
        ],
    )

    items = _items_by_id(registry)
    systemd = items["hermes-systemd-consistency"]
    assert systemd["status"] == "blocked"
    assert systemd["metadata"]["bad_unit_links"] == [
        {
            "source": "/etc/systemd/system/hermes-evolution-foundation.service",
            "target": str(
                runtime_bundle / "systemd" / "hermes-evolution-foundation.service"
            ),
        }
    ]
    assert (
        "hermes-agency-department-report.service loaded failed failed"
        in systemd["evidence"]
    )

    scripts = items["hermes-runtime-script-sources"]
    assert scripts["status"] == "blocked"
    assert scripts["metadata"]["missing_script_paths"] == [
        "scripts/moneygen_bounded.py",
        "scripts/nerdm_knowledge_sync_report.py",
        "scripts/postgres_readonly_mcp.py",
    ]
    assert scripts["metadata"]["available_archive_scripts"] == []

    containers = items["hermes-runtime-containers"]
    assert containers["status"] == "observed"
    assert containers["metadata"]["container_count"] == 1


def test_hermes_repair_readiness_prefers_detached_checkout_restore_source(tmp_path):
    from scripts.nerd.autonomous.hermes_repair_readiness import (
        build_hermes_repair_readiness_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    hermes_agent_root = tmp_path / ".hermes" / "hermes-agent"
    runtime_bundle = hermes_agent_root / "ops" / "hermes-evolution"
    archive_bundle = tmp_path / "archive"
    source_bundle = tmp_path / "detached" / "ops" / "hermes-evolution"
    runtime_bundle.mkdir(parents=True)
    archive_bundle.mkdir(parents=True)
    for relative in (
        "README.md",
        "compose/foundation.compose.yml",
        "runbooks/cutover-gates.md",
        "scripts/agency_department_report.py",
        "scripts/bootstrap_layout.sh",
        "scripts/validate_bundle.py",
        "systemd/hermes-evolution-foundation.service",
    ):
        path = source_bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# source\n", encoding="utf-8")

    registry = build_hermes_repair_readiness_registry(
        canonical_root=canonical_root,
        hermes_agent_root=hermes_agent_root,
        runtime_bundle_root=runtime_bundle,
        archive_bundle_root=archive_bundle,
        source_bundle_root=source_bundle,
        service_rows=[],
        systemd_link_rows=[],
        docker_rows=[],
    )

    items = _items_by_id(registry)
    source = items["hermes-detached-checkout-restore-source"]
    assert source["status"] == "present"
    assert source["metadata"]["source_file_count"] == 7

    layout = items["hermes-runtime-bundle-layout"]
    assert layout["metadata"]["selected_restore_source"] == str(source_bundle)
    assert str(source_bundle) in layout["metadata"]["restore_plan"]["dry_run_command"]

    scripts = items["hermes-runtime-script-sources"]
    assert scripts["metadata"]["available_source_scripts"] == []


def test_write_hermes_repair_readiness_registry_sorts_items_and_writes_json(tmp_path):
    from scripts.nerd.autonomous.hermes_repair_readiness import (
        write_hermes_repair_readiness_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    output = write_hermes_repair_readiness_registry(
        canonical_root=canonical_root,
        hermes_agent_root=tmp_path / "missing-agent",
        runtime_bundle_root=tmp_path / "missing-runtime",
        archive_bundle_root=tmp_path / "missing-archive",
        service_rows=[],
        systemd_link_rows=[],
        docker_rows=[],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    item_ids = [item["id"] for item in payload["items"]]
    assert output == canonical_root / "registry" / "hermes-repair-readiness.json"
    assert item_ids == sorted(item_ids)
    assert payload["canonical_root"] == str(canonical_root)
