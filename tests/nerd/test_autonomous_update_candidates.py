from __future__ import annotations

import json


def _items_by_id(registry: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in registry["items"]}  # type: ignore[index]


def test_update_candidates_registry_blocks_fragile_hermes_update(tmp_path):
    from scripts.nerd.autonomous.update_candidates import (
        build_update_candidates_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    hermes_agent_root = tmp_path / ".hermes" / "hermes-agent"
    hermes_agent_root.mkdir(parents=True)
    runtime_bundle = hermes_agent_root / "ops" / "hermes-evolution"
    runtime_bundle.mkdir(parents=True)
    (runtime_bundle / "state").mkdir()

    registry = build_update_candidates_registry(
        canonical_root=canonical_root,
        hermes_agent_root=hermes_agent_root,
        runtime_bundle_root=runtime_bundle,
        staging_root=tmp_path / "staging",
        stack_root=tmp_path / "stack",
        service_rows=[
            "hermes-gateway.service loaded active running",
            "hermes-perpetual-autonomy.service loaded activating auto-restart",
            "ollama.service loaded activating auto-restart",
        ],
    )

    items = _items_by_id(registry)
    hermes = items["update-hermes-agent-runtime"]
    assert hermes["status"] == "blocked"
    assert hermes["risk"] == "high"
    assert hermes["approval_level"] == "L3"
    assert hermes["metadata"]["missing_bundle_paths"] == [
        "README.md",
        "compose",
        "runbooks",
        "scripts",
        "systemd",
    ]
    assert (
        "hermes-perpetual-autonomy.service loaded activating auto-restart"
        in hermes["evidence"]
    )

    ollama = items["update-ollama-runtime"]
    assert ollama["status"] == "deferred"
    assert ollama["risk"] == "medium"
    assert ollama["approval_level"] == "L2"


def test_update_candidates_registry_marks_read_only_refreshes_safe(tmp_path):
    from scripts.nerd.autonomous.update_candidates import (
        build_update_candidates_registry,
    )

    staging_root = tmp_path / "staging"
    stack_root = tmp_path / "stack"
    (staging_root / "scripts" / "nerd").mkdir(parents=True)
    (staging_root / "scripts" / "nerd" / "generate_inventory.py").write_text(
        "# inventory\n", encoding="utf-8"
    )
    registry = build_update_candidates_registry(
        canonical_root=tmp_path / "nerd-method",
        hermes_agent_root=tmp_path / "missing-hermes-agent",
        runtime_bundle_root=tmp_path / "missing-runtime-bundle",
        staging_root=staging_root,
        stack_root=stack_root,
        service_rows=[],
    )

    items = _items_by_id(registry)
    inventory = items["refresh-nerd-inventory"]
    assert inventory["kind"] == "refresh"
    assert inventory["status"] == "safe_check"
    assert inventory["approval_level"] == "L1"
    assert inventory["risk"] == "low"

    assert "refresh-openwebui-seed-dry-run" not in items

    registries = items["refresh-autonomous-registries"]
    assert (
        "python -m scripts.nerd.autonomous.hermes_repair_readiness"
        in (registries["metadata"]["check_commands"])
    )


def test_write_update_candidates_registry_sorts_items_and_writes_json(tmp_path):
    from scripts.nerd.autonomous.update_candidates import (
        write_update_candidates_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    output = write_update_candidates_registry(
        canonical_root=canonical_root,
        hermes_agent_root=tmp_path / "missing-hermes-agent",
        runtime_bundle_root=tmp_path / "missing-runtime-bundle",
        staging_root=tmp_path / "missing-staging",
        stack_root=tmp_path / "missing-stack",
        service_rows=[],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    item_ids = [item["id"] for item in payload["items"]]
    assert output == canonical_root / "registry" / "update-candidates.json"
    assert item_ids == sorted(item_ids)
    assert payload["canonical_root"] == str(canonical_root)
