from __future__ import annotations

import json


def _items_by_id(registry: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in registry["items"]}  # type: ignore[index]


def test_hermes_agents_registry_reads_identity_status_and_objectives(tmp_path):
    from scripts.nerd.autonomous.hermes_agents import build_hermes_agents_registry

    canonical_root = tmp_path / "nerd-method"
    hermes_root = tmp_path / "hermes"
    nerd_agency_root = canonical_root / "nerd-agency"
    core = hermes_root / "core"
    core.mkdir(parents=True)
    (core / "CEO_IDENTITY.md").write_text("# CEO Strategic Identity\n", encoding="utf-8")
    (core / "status.json").write_text(
        json.dumps(
            {
                "last_heartbeat": "2026-05-24 22:47:30.436817",
                "active_departments": ["dev"],
            }
        ),
        encoding="utf-8",
    )
    (core / "objectives.json").write_text(
        json.dumps(
            {
                "objectives": [
                    {
                        "id": "obj-001",
                        "title": "Directory Architecture Consolidation",
                        "dept": "dev",
                        "status": "in_progress",
                        "prio": "high",
                        "description": "Consolidate directories.",
                    },
                    {
                        "id": "obj-016",
                        "title": "Market Research Automation",
                        "dept": "research",
                        "status": "pending",
                        "prio": "medium",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    mirror_core = (
        nerd_agency_root / "nerd-departments" / "nerd-system-development" / "core"
    )
    mirror_core.mkdir(parents=True)
    (mirror_core / "CEO_IDENTITY.md").write_text("# Mirror\n", encoding="utf-8")

    registry = build_hermes_agents_registry(
        canonical_root=canonical_root,
        hermes_root=hermes_root,
        nerd_agency_root=nerd_agency_root,
    )

    items = _items_by_id(registry)
    ceo = items["hermes-agent-ceo"]
    assert ceo["classification"] == "strategic_agent"
    assert ceo["status"] == "active"
    assert ceo["metadata"]["last_heartbeat"] == "2026-05-24 22:47:30.436817"
    assert ceo["metadata"]["objective_count"] == 2
    assert ceo["metadata"]["active_departments"] == ["dev"]

    objective = items["hermes-objective-obj-001"]
    assert objective["kind"] == "objective"
    assert objective["status"] == "in_progress"
    assert objective["risk"] == "medium"
    assert objective["metadata"]["department"] == "dev"
    assert items["hermes-objective-obj-016"]["status"] == "pending"
    assert items["hermes-agency-core-mirror"]["status"] == "present"


def test_hermes_agents_registry_handles_missing_core_safely(tmp_path):
    from scripts.nerd.autonomous.hermes_agents import build_hermes_agents_registry

    registry = build_hermes_agents_registry(
        canonical_root=tmp_path / "nerd-method",
        hermes_root=tmp_path / "missing-hermes",
        nerd_agency_root=tmp_path / "missing-agency",
    )

    items = _items_by_id(registry)
    assert items["hermes-agent-ceo"]["status"] == "missing"
    assert items["hermes-agent-ceo"]["risk"] == "medium"
    assert "hermes-objectives" in items
    assert items["hermes-objectives"]["status"] == "missing"


def test_write_hermes_agents_registry_sorts_items_and_writes_json(tmp_path):
    from scripts.nerd.autonomous.hermes_agents import write_hermes_agents_registry

    canonical_root = tmp_path / "nerd-method"
    output = write_hermes_agents_registry(
        canonical_root=canonical_root,
        hermes_root=tmp_path / "missing-hermes",
        nerd_agency_root=tmp_path / "missing-agency",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    item_ids = [item["id"] for item in payload["items"]]
    assert output == canonical_root / "registry" / "hermes-agents.json"
    assert item_ids == sorted(item_ids)
    assert payload["canonical_root"] == str(canonical_root)
