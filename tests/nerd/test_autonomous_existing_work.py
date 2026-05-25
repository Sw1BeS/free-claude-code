from __future__ import annotations

import json


def test_existing_work_registry_classifies_known_roots(tmp_path):
    from scripts.nerd.autonomous.existing_work import build_existing_work_registry

    stack = tmp_path / "nerd-agency-stack"
    staging = tmp_path / "nerd-claude-free-staging"
    method = tmp_path / "nerd-method"
    n8n = stack / "n8n" / "v1-workflows"
    n8n.mkdir(parents=True)
    (n8n / "health.workflow.json").write_text('{"name": "health"}', encoding="utf-8")
    staging.mkdir()
    method.mkdir()

    registry = build_existing_work_registry(
        canonical_root=method,
        roots=[method, stack, staging],
    )

    ids = {item["id"] for item in registry["items"]}
    assert "root-nerd-method" in ids
    assert "workspace-nerd-claude-free-staging" in ids
    assert "runtime-nerd-agency-stack" in ids
    assert any(item["classification"] == "active_runtime" for item in registry["items"])
    assert any(item["kind"] == "workflow" for item in registry["items"])


def test_existing_work_registry_skips_missing_roots(tmp_path):
    from scripts.nerd.autonomous.existing_work import build_existing_work_registry

    registry = build_existing_work_registry(
        canonical_root=tmp_path / "nerd-method",
        roots=[tmp_path / "missing"],
    )

    assert registry["items"] == []
    assert registry["warnings"] == [f"missing root: {tmp_path / 'missing'}"]


def test_write_existing_work_registry_writes_json(tmp_path):
    from scripts.nerd.autonomous.existing_work import write_existing_work_registry

    canonical_root = tmp_path / "nerd-method"
    canonical_root.mkdir()

    output = write_existing_work_registry(
        canonical_root=canonical_root,
        roots=[canonical_root],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert output == canonical_root / "registry" / "existing-work.json"
    assert payload["items"][0]["id"] == "root-nerd-method"
