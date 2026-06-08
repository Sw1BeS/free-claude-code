from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json
from scripts.nerd.brain.store import build_brain_store_snapshot, brain_db_path

DEFAULT_STAGING_ROOT = Path("/root/nerd-claude-free-staging")
DEFAULT_HERMES_ROOT = Path("/root/hermes")
DEFAULT_AGENCY_ROOT = Path("/root/nerd-method/nerd-agency")
DEFAULT_OBSIDIAN_ROOT = Path("/root/obsidian-vault")
DEFAULT_KNOWLEDGE_ROOT = Path("/srv/nerd-knowledge")


def _safe_read_json(path: Path, default: object) -> object:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return default


def _count_files(path: Path, pattern: str) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for item in path.rglob(pattern) if item.is_file())


def _count_json_records(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def _items_count_from_bundle(path: Path) -> int:
    payload = _safe_read_json(path, {})
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return len(payload["items"])
    return 0


def _objectives_count(path: Path) -> int:
    payload = _safe_read_json(path, {})
    if isinstance(payload, dict) and isinstance(payload.get("objectives"), list):
        return len(payload["objectives"])
    return 0


def _status_metadata(path: Path) -> dict[str, object]:
    payload = _safe_read_json(path, {})
    if not isinstance(payload, dict):
        return {}
    metadata: dict[str, object] = {}
    if payload.get("last_heartbeat"):
        metadata["last_heartbeat"] = payload["last_heartbeat"]
    if isinstance(payload.get("active_departments"), list):
        metadata["active_departments"] = payload["active_departments"]
    return metadata


def _item(
    *,
    id: str,
    name: str,
    kind: str,
    classification: str,
    status: str,
    risk: str,
    notes: str,
    path: Path | str | None = None,
    evidence: Iterable[str] = (),
    metadata: dict[str, object] | None = None,
    source_url: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": id,
        "name": name,
        "kind": kind,
        "classification": classification,
        "status": status,
        "risk": risk,
        "evidence": sorted({value for value in evidence if value}),
        "notes": notes,
    }
    if path is not None:
        item["path"] = str(path)
    if metadata is not None:
        item["metadata"] = metadata
    if source_url is not None:
        item["source_url"] = source_url
    return item


def _path_item(
    *,
    id: str,
    name: str,
    kind: str,
    classification: str,
    path: Path,
    risk: str,
    notes: str,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    exists = path.exists()
    return _item(
        id=id,
        name=name,
        kind=kind,
        classification=classification,
        status="present" if exists else "missing",
        risk=risk,
        path=path,
        evidence=[str(path)] if exists else [],
        metadata=metadata,
        notes=notes if exists else f"{notes} Expected path was not found.",
    )


def build_brain_memory_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    hermes_root: Path = DEFAULT_HERMES_ROOT,
    agency_root: Path = DEFAULT_AGENCY_ROOT,
    obsidian_root: Path = DEFAULT_OBSIDIAN_ROOT,
    knowledge_root: Path = DEFAULT_KNOWLEDGE_ROOT,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    staging_root = Path(staging_root)
    hermes_root = Path(hermes_root)
    agency_root = Path(agency_root)
    obsidian_root = Path(obsidian_root)
    knowledge_root = Path(knowledge_root)

    memory_root = canonical_root / "memory"
    queue_counts = {
        "approvals": _count_json_records(memory_root / "approvals"),
        "artifacts": _count_json_records(memory_root / "artifacts"),
        "inbox": _count_json_records(memory_root / "inbox"),
        "knowledge": _count_files(memory_root / "knowledge", "*.md"),
        "tasks": _count_json_records(memory_root / "tasks"),
    }
    operating_model = memory_root / "knowledge" / "nerd-method-operating-model.md"
    openwebui_seed = staging_root / "scripts" / "nerd" / "agency" / "openwebui_seed.py"
    inventory_pack = staging_root / "docs" / "nerd_inventory" / "nerd-method-brain.json"
    knowledge_base = agency_root / "nerd-knowledge-base"
    hermes_core = hermes_root / "core"
    ceo_identity = hermes_core / "CEO_IDENTITY.md"
    objectives = hermes_core / "objectives.json"
    status = hermes_core / "status.json"
    brain_store = build_brain_store_snapshot(canonical_root)

    items = [
        _item(
            id="brain-store-db",
            name="NERD Brain Store",
            kind="database",
            classification="canonical_brain_store",
            status=str(brain_store.get("status") or "missing"),
            risk="medium",
            path=brain_db_path(canonical_root),
            evidence=[str(brain_db_path(canonical_root))]
            if brain_db_path(canonical_root).is_file()
            else [],
            metadata={
                "schema_version": brain_store.get("schema_version"),
                "source_count": brain_store.get("source_count", 0),
                "episode_count": brain_store.get("episode_count", 0),
                "candidate_count": brain_store.get("candidate_count", 0),
                "approved_count": brain_store.get("approved_count", 0),
                "last_episode_at": brain_store.get("last_episode_at"),
            },
            notes=(
                "DB-backed second brain store. JSON registries remain mirrors "
                "for agents and UI surfaces."
            ),
        ),
        _path_item(
            id="brain-memory-root",
            name="NERD Method Writable Memory",
            kind="memory_root",
            classification="canonical_memory",
            path=memory_root,
            risk="medium",
            metadata={"queue_counts": queue_counts},
            notes="Canonical writable memory for inbox, tasks, approvals, reports, knowledge, prompts, runs, and artifacts.",
        ),
        _path_item(
            id="brain-operating-model",
            name="NERD Method Operating Model",
            kind="knowledge_doc",
            classification="operating_model",
            path=operating_model,
            risk="low",
            notes="Primary operating model loaded into the shared brain.",
        ),
        _path_item(
            id="brain-openwebui-seed",
            name="Open WebUI Optional Seed Script",
            kind="seed_tool",
            classification="optional_legacy_adapter",
            path=openwebui_seed,
            risk="medium",
            metadata={
                "core_shell": False,
                "approval_gated": True,
                "role": "optional_chat_surface",
            },
            notes=(
                "Deterministic seed/sync tool retained for optional Open WebUI "
                "chat/model surface only; it is not the NERD OS shell."
            ),
        ),
        _path_item(
            id="brain-nerd-inventory-pack",
            name="Generated NERD Brain Inventory Pack",
            kind="knowledge_pack",
            classification="generated_inventory",
            path=inventory_pack,
            risk="low",
            metadata={"item_count": _items_count_from_bundle(inventory_pack)},
            notes="Generated knowledge pack used by Open WebUI and the OS brain surfaces.",
        ),
        _path_item(
            id="brain-knowledge-base",
            name="NERD Agency Knowledge Base",
            kind="knowledge_base",
            classification="agency_knowledge",
            path=knowledge_base,
            risk="medium",
            metadata={"markdown_count": _count_files(knowledge_base, "*.md")},
            notes="Existing agency knowledge base with repo patterns, analyses, skills, and task material.",
        ),
        _path_item(
            id="brain-hermes-ceo-identity",
            name="Hermes CEO Identity",
            kind="knowledge_doc",
            classification="hermes_identity",
            path=ceo_identity,
            risk="medium",
            notes="Hermes strategic identity and constraints.",
        ),
        _path_item(
            id="brain-hermes-objectives",
            name="Hermes Objectives",
            kind="state_file",
            classification="hermes_objectives",
            path=objectives,
            risk="medium",
            metadata={"objective_count": _objectives_count(objectives)},
            notes="Hermes objective backlog/state source.",
        ),
        _path_item(
            id="brain-hermes-status",
            name="Hermes Runtime Status",
            kind="state_file",
            classification="hermes_status",
            path=status,
            risk="medium",
            metadata=_status_metadata(status),
            notes="Hermes heartbeat and active-department status source.",
        ),
        _path_item(
            id="brain-obsidian-vault",
            name="Obsidian Vault",
            kind="vault",
            classification="personal_vault",
            path=obsidian_root,
            risk="low",
            metadata={"markdown_count": _count_files(obsidian_root, "*.md")},
            notes="Local Obsidian vault candidate. Sparse vaults remain registered but not treated as canonical.",
        ),
        _path_item(
            id="brain-srv-nerd-knowledge",
            name="NERD Knowledge Ops Vault",
            kind="knowledge_vault",
            classification="ops_knowledge",
            path=knowledge_root,
            risk="medium",
            metadata={"markdown_count": _count_files(knowledge_root, "*.md")},
            notes="Existing rich ops/state/runbook vault discovered during brain audit.",
        ),
    ]

    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_brain_memory_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    hermes_root: Path = DEFAULT_HERMES_ROOT,
    agency_root: Path = DEFAULT_AGENCY_ROOT,
    obsidian_root: Path = DEFAULT_OBSIDIAN_ROOT,
    knowledge_root: Path = DEFAULT_KNOWLEDGE_ROOT,
) -> Path:
    output = Path(canonical_root) / "registry" / "brain-memory.json"
    registry = build_brain_memory_registry(
        canonical_root=canonical_root,
        staging_root=staging_root,
        hermes_root=hermes_root,
        agency_root=agency_root,
        obsidian_root=obsidian_root,
        knowledge_root=knowledge_root,
    )
    return write_json(output, registry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write NERD brain and memory registry."
    )
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--staging-root", type=Path, default=DEFAULT_STAGING_ROOT)
    parser.add_argument("--hermes-root", type=Path, default=DEFAULT_HERMES_ROOT)
    parser.add_argument("--agency-root", type=Path, default=DEFAULT_AGENCY_ROOT)
    parser.add_argument("--obsidian-root", type=Path, default=DEFAULT_OBSIDIAN_ROOT)
    parser.add_argument("--knowledge-root", type=Path, default=DEFAULT_KNOWLEDGE_ROOT)
    args = parser.parse_args(argv)
    output = write_brain_memory_registry(
        canonical_root=args.canonical_root,
        staging_root=args.staging_root,
        hermes_root=args.hermes_root,
        agency_root=args.agency_root,
        obsidian_root=args.obsidian_root,
        knowledge_root=args.knowledge_root,
    )
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
