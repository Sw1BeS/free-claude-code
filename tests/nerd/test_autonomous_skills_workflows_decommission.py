from __future__ import annotations

import json


def _items_by_id(registry: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in registry["items"]}  # type: ignore[index]


def test_skills_registry_seeds_core_skill_records(tmp_path):
    from scripts.nerd.autonomous.skills_registry import build_skills_registry

    registry = build_skills_registry(canonical_root=tmp_path / "nerd-method")

    items = _items_by_id(registry)
    assert items["skill-memory-curation"]["status"] == "approved"
    assert items["skill-memory-curation"]["risk_level"] == "low"
    assert items["skill-hermes-operations"]["category"] == "operations"
    assert not any("paperclip" in json.dumps(item).lower() for item in items.values())


def test_workflows_registry_seeds_internal_n8n_and_webhook_records(tmp_path):
    from scripts.nerd.autonomous.workflows_registry import build_workflows_registry

    registry = build_workflows_registry(canonical_root=tmp_path / "nerd-method")

    items = _items_by_id(registry)
    assert items["workflow-brain-intake-n8n"]["source"] == "n8n"
    assert items["workflow-brain-intake-n8n"]["dry_run_available"] is True
    assert items["workflow-hermes-gateway-events"]["source"] == "webhook"
    assert items["workflow-openwebui-seed-legacy"]["status"] == "legacy_optional"
    assert not any("paperclip" in json.dumps(item).lower() for item in items.values())
