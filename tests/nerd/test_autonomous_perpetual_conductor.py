from __future__ import annotations

import json


def test_perpetual_conductor_runs_registry_supervision_cycle(tmp_path):
    from scripts.nerd.autonomous.perpetual_conductor import (
        ConductorConfig,
        run_cycle,
        write_evidence,
    )

    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "hermes-agents.json").write_text(
        '{"items": [{"id": "hermes-agent-ceo", "status": "active"}]}',
        encoding="utf-8",
    )
    (registry_dir / "brain-memory.json").write_text(
        '{"items": [{"id": "brain-memory-root", "status": "present"}]}',
        encoding="utf-8",
    )
    (registry_dir / "workflows-registry.json").write_text(
        '{"items": [{"id": "workflow-brain-intake-n8n", "status": "dry_run_ready"}]}',
        encoding="utf-8",
    )
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": ['
        '{"id": "runtime-hermes", "status": "active"},'
        '{"id": "integration-openwebui", "status": "optional", '
        '"metadata": {"core_shell": false}}'
        "]}",
        encoding="utf-8",
    )
    (registry_dir / "update-candidates.json").write_text(
        '{"items": [{"id": "update-hermes", "status": "candidate"}]}',
        encoding="utf-8",
    )
    config = ConductorConfig(
        canonical_root=tmp_path,
        report_dir=tmp_path / "reports",
        dry_run=True,
        max_cycles=1,
    )
    record = run_cycle(config)
    path = write_evidence(config.report_dir, record)

    payload = json.loads(path.read_text(encoding="utf-8"))
    latest = json.loads(
        (config.report_dir / "autonomy-supervisor-latest.json").read_text()
    )
    assert payload["action"] == "nerd_os_registry_supervision"
    assert payload["dry_run"] is True
    assert payload["openwebui_core_shell"] is False
    assert payload["counts"]["hermes_agents"] == 1
    assert "decommissioned" not in payload["counts"]
    assert latest["action"] == "nerd_os_registry_supervision"
