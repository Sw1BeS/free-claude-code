from __future__ import annotations

import json


def _items_by_id(registry: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in registry["items"]}  # type: ignore[index]


def test_runtime_registry_classifies_hermes_root_and_failed_service(tmp_path):
    from scripts.nerd.autonomous.runtime_integrations import (
        build_runtime_integration_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    hermes_root = tmp_path / "hermes"
    gitinspired_root = canonical_root / "tools" / "git-inspired"
    (hermes_root / "core").mkdir(parents=True)
    (hermes_root / "core" / "status.json").write_text(
        '{"state": "running"}',
        encoding="utf-8",
    )
    (hermes_root / "infra" / "configs").mkdir(parents=True)
    (hermes_root / "infra" / "configs" / "config.yaml").write_text(
        "runtime: hermes\n",
        encoding="utf-8",
    )

    registry = build_runtime_integration_registry(
        canonical_root=canonical_root,
        hermes_root=hermes_root,
        gitinspired_root=gitinspired_root,
        service_rows=["hermes-knowledge-sync.service loaded failed failed"],
    )

    items = _items_by_id(registry)
    hermes = items["runtime-hermes"]
    assert hermes["classification"] == "active_runtime"
    assert hermes["status"] == "active"
    assert hermes["kind"] == "runtime"
    assert str(hermes_root / "core" / "status.json") in hermes["evidence"]
    assert str(hermes_root / "infra" / "configs" / "config.yaml") in hermes["evidence"]

    service = items["service-hermes-knowledge-sync"]
    assert service["status"] == "needs_attention"
    assert service["classification"] == "runtime_service"
    assert service["kind"] == "service"


def test_runtime_registry_classifies_gitinspired_integration_sources(tmp_path):
    from scripts.nerd.autonomous.runtime_integrations import (
        build_runtime_integration_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    gitinspired_root = canonical_root / "tools" / "git-inspired"
    for dirname in ("awesome-openclaw-skills", "ecc", "9router", "graphify"):
        (gitinspired_root / dirname).mkdir(parents=True)

    registry = build_runtime_integration_registry(
        canonical_root=canonical_root,
        hermes_root=tmp_path / "missing-hermes",
        gitinspired_root=gitinspired_root,
        service_rows=[],
    )

    items = _items_by_id(registry)
    openclaw = items["source-openclaw-skills"]
    assert openclaw["kind"] == "skillpack"
    assert openclaw["classification"] == "source_cache"
    assert openclaw["status"] == "present"

    ecc = items["migration-ecc-docs"]
    assert ecc["kind"] == "skillpack"
    assert ecc["classification"] == "migration_source"
    assert ecc["status"] == "present"

    router = items["runtime-9router"]
    assert router["kind"] == "model_router"
    assert router["classification"] == "model_router"
    assert router["status"] == "present"

    graphify = items["source-graphify"]
    assert graphify["kind"] == "model_tooling"
    assert graphify["classification"] == "model_source"
    assert graphify["status"] == "present"


def test_runtime_registry_includes_litellm_and_ollama_local_records(tmp_path):
    from scripts.nerd.autonomous.runtime_integrations import (
        build_runtime_integration_registry,
    )

    registry = build_runtime_integration_registry(
        canonical_root=tmp_path / "nerd-method",
        hermes_root=tmp_path / "missing-hermes",
        gitinspired_root=tmp_path / "missing-gitinspired",
        service_rows=[
            "litellm-local.service loaded active running",
            "ollama.service loaded inactive dead",
        ],
    )

    items = _items_by_id(registry)
    gateway = items["gateway-litellm-local"]
    assert gateway["kind"] == "model_gateway"
    assert gateway["classification"] == "model_gateway"
    assert gateway["status"] == "active"
    assert gateway["metadata"] == {"base_url": "http://127.0.0.1:44000/v1"}
    assert "source_url" not in gateway

    ollama = items["runtime-ollama"]
    assert ollama["kind"] == "local_llm_runtime"
    assert ollama["classification"] == "local_llm_runtime"
    assert ollama["status"] == "inactive"


def test_runtime_registry_marks_openwebui_optional_and_excludes_paperclip_active(
    tmp_path,
):
    from scripts.nerd.autonomous.runtime_integrations import (
        build_runtime_integration_registry,
    )

    registry = build_runtime_integration_registry(
        canonical_root=tmp_path / "nerd-method",
        hermes_root=tmp_path / "missing-hermes",
        gitinspired_root=tmp_path / "missing-gitinspired",
        service_rows=[
            "hermes-evolution-paperclip.service loaded active exited",
            "hermes-gateway.service loaded active running",
        ],
    )

    items = _items_by_id(registry)
    assert "service-hermes-evolution-paperclip" not in items
    assert items["integration-openwebui"]["classification"] == "optional_integration"
    assert items["integration-openwebui"]["metadata"]["role"] == "optional_chat_surface"
    assert items["integration-openwebui"]["metadata"]["core_shell"] is False
    assert items["integration-openwebui"]["metadata"]["approval_gated"] is True


def test_write_runtime_integration_registry_writes_valid_json(tmp_path):
    from scripts.nerd.autonomous.runtime_integrations import (
        write_runtime_integration_registry,
    )

    canonical_root = tmp_path / "nerd-method"
    hermes_root = tmp_path / "hermes"
    (hermes_root / "core").mkdir(parents=True)
    (hermes_root / "core" / "status.json").write_text("{}", encoding="utf-8")

    output = write_runtime_integration_registry(
        canonical_root=canonical_root,
        hermes_root=hermes_root,
        gitinspired_root=canonical_root / "tools" / "git-inspired",
        service_rows=[],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    item_ids = [item["id"] for item in payload["items"]]
    assert output == canonical_root / "registry" / "runtime-integrations.json"
    assert item_ids == sorted(item_ids)
    assert "runtime-hermes" in item_ids


def test_write_runtime_integration_registry_can_use_service_row_discovery(
    tmp_path,
    monkeypatch,
):
    from scripts.nerd.autonomous import runtime_integrations

    canonical_root = tmp_path / "nerd-method"
    hermes_root = tmp_path / "hermes"
    (hermes_root / "core").mkdir(parents=True)
    (hermes_root / "core" / "status.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        runtime_integrations,
        "discover_service_rows",
        lambda: ["hermes-gateway.service loaded active running"],
    )

    output = runtime_integrations.write_runtime_integration_registry(
        canonical_root=canonical_root,
        hermes_root=hermes_root,
        gitinspired_root=canonical_root / "tools" / "git-inspired",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    items = _items_by_id(payload)
    assert items["service-hermes-gateway"]["status"] == "active"
