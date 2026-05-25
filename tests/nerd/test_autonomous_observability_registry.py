from __future__ import annotations

import json


def test_observability_registry_summarizes_runs_and_runtime_attention(tmp_path):
    from scripts.nerd.autonomous.observability_registry import (
        build_observability_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    registry_dir = canonical_root / "registry"
    run_log = canonical_root / "memory" / "reports" / "nerd-os-runs.jsonl"
    registry_dir.mkdir(parents=True)
    run_log.parent.mkdir(parents=True)
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": ['
        '{"id": "runtime-hermes", "status": "active"},'
        '{"id": "service-hermes-webhook", "status": "needs_attention"}'
        "]}",
        encoding="utf-8",
    )
    run_log.write_text(
        "\n".join(
            [
                '{"timestamp": "2026-05-25T01:00:00Z", "action_id": "ok", "exit_code": 0, "duration_ms": 50}',
                '{"timestamp": "2026-05-25T01:05:00Z", "action_id": "bad", "exit_code": 1, "duration_ms": 70}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    registry = build_observability_registry(canonical_root=canonical_root)

    items = {str(item["id"]): item for item in registry["items"]}  # type: ignore[index]
    runs = items["observability-run-log"]
    runtime = items["observability-runtime-attention"]
    assert runs["status"] == "needs_attention"
    assert runs["metadata"]["run_count"] == 2
    assert runs["metadata"]["failed_runs"] == 1
    assert runtime["status"] == "needs_attention"
    assert runtime["metadata"]["attention_count"] == 1
    assert not any("paperclip" in json.dumps(item).lower() for item in items.values())


def test_write_observability_registry_sorts_items_and_writes_json(tmp_path):
    from scripts.nerd.autonomous.observability_registry import (
        write_observability_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    output = write_observability_registry(canonical_root=canonical_root)

    payload = json.loads(output.read_text(encoding="utf-8"))
    item_ids = [item["id"] for item in payload["items"]]
    assert output == canonical_root / "registry" / "observability-events.json"
    assert item_ids == sorted(item_ids)
    assert "observability-run-log" in item_ids
