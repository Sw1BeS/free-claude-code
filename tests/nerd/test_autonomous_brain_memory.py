from __future__ import annotations

import json


def _items_by_id(registry: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in registry["items"]}  # type: ignore[index]


def test_brain_memory_registry_collects_existing_brain_sources(tmp_path):
    from scripts.nerd.autonomous.brain_memory import build_brain_memory_registry

    canonical_root = tmp_path / "nerd-method"
    staging_root = tmp_path / "staging"
    hermes_root = tmp_path / "hermes"
    agency_root = canonical_root / "nerd-agency"
    obsidian_root = tmp_path / "obsidian-vault"
    knowledge_root = tmp_path / "srv-nerd-knowledge"

    (canonical_root / "memory" / "knowledge").mkdir(parents=True)
    (
        canonical_root / "memory" / "knowledge" / "nerd-method-operating-model.md"
    ).write_text("# Operating Model\n", encoding="utf-8")
    for queue in ("inbox", "tasks", "approvals"):
        queue_dir = canonical_root / "memory" / queue
        queue_dir.mkdir(parents=True, exist_ok=True)
        (queue_dir / f"{queue}_1.json").write_text(
            json.dumps({"id": f"{queue}_1"}), encoding="utf-8"
        )
    (canonical_root / "memory" / "artifacts").mkdir(parents=True, exist_ok=True)
    (canonical_root / "memory" / "artifacts" / "candidate_1.json").write_text(
        json.dumps({"id": "candidate_1", "promotion_status": "candidate"}),
        encoding="utf-8",
    )

    (staging_root / "scripts" / "nerd" / "agency").mkdir(parents=True)
    (staging_root / "scripts" / "nerd" / "agency" / "openwebui_seed.py").write_text(
        "# seed\n", encoding="utf-8"
    )
    (staging_root / "docs" / "nerd_inventory").mkdir(parents=True)
    (staging_root / "docs" / "nerd_inventory" / "nerd-method-brain.json").write_text(
        '{"items": [{"id": "brain-canonical-repo"}]}',
        encoding="utf-8",
    )
    (agency_root / "nerd-knowledge-base" / "repo-patterns").mkdir(parents=True)
    (agency_root / "nerd-knowledge-base" / "repo-patterns" / "patterns.md").write_text(
        "# Patterns\n", encoding="utf-8"
    )
    (hermes_root / "core").mkdir(parents=True)
    (hermes_root / "core" / "CEO_IDENTITY.md").write_text("# CEO\n", encoding="utf-8")
    (hermes_root / "core" / "objectives.json").write_text(
        '{"objectives": [{"id": "obj-1"}]}',
        encoding="utf-8",
    )
    (hermes_root / "core" / "status.json").write_text(
        '{"last_heartbeat": "2026-05-24 22:47:30"}',
        encoding="utf-8",
    )
    obsidian_root.mkdir()
    (obsidian_root / "note.md").write_text("# Note\n", encoding="utf-8")
    (knowledge_root / "10_state").mkdir(parents=True)
    (knowledge_root / "10_state" / "latest-system-status.md").write_text(
        "# Status\n", encoding="utf-8"
    )

    registry = build_brain_memory_registry(
        canonical_root=canonical_root,
        staging_root=staging_root,
        hermes_root=hermes_root,
        agency_root=agency_root,
        obsidian_root=obsidian_root,
        knowledge_root=knowledge_root,
    )

    items = _items_by_id(registry)
    assert items["brain-memory-root"]["status"] == "present"
    assert items["brain-memory-root"]["metadata"]["queue_counts"] == {
        "approvals": 1,
        "artifacts": 1,
        "inbox": 1,
        "knowledge": 1,
        "tasks": 1,
    }
    assert items["brain-operating-model"]["status"] == "present"
    assert items["brain-openwebui-seed"]["classification"] == "optional_legacy_adapter"
    assert items["brain-openwebui-seed"]["metadata"]["core_shell"] is False
    assert items["brain-openwebui-seed"]["metadata"]["approval_gated"] is True
    assert items["brain-nerd-inventory-pack"]["metadata"]["item_count"] == 1
    assert items["brain-knowledge-base"]["metadata"]["markdown_count"] == 1
    assert not any("paperclip" in json.dumps(item).lower() for item in items.values())
    assert items["brain-hermes-ceo-identity"]["status"] == "present"
    assert items["brain-hermes-objectives"]["metadata"]["objective_count"] == 1
    assert items["brain-hermes-status"]["metadata"]["last_heartbeat"] == (
        "2026-05-24 22:47:30"
    )
    assert items["brain-obsidian-vault"]["metadata"]["markdown_count"] == 1
    assert items["brain-srv-nerd-knowledge"]["metadata"]["markdown_count"] == 1


def test_write_brain_memory_registry_sorts_items_and_writes_json(tmp_path):
    from scripts.nerd.autonomous.brain_memory import write_brain_memory_registry

    canonical_root = tmp_path / "nerd-method"
    output = write_brain_memory_registry(
        canonical_root=canonical_root,
        staging_root=tmp_path / "missing-staging",
        hermes_root=tmp_path / "missing-hermes",
        agency_root=tmp_path / "missing-agency",
        obsidian_root=tmp_path / "missing-obsidian",
        knowledge_root=tmp_path / "missing-knowledge",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    item_ids = [item["id"] for item in payload["items"]]
    assert output == canonical_root / "registry" / "brain-memory.json"
    assert item_ids == sorted(item_ids)
    assert "brain-memory-root" in item_ids
    assert payload["canonical_root"] == str(canonical_root)
