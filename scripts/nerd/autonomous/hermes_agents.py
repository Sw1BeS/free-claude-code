from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json

DEFAULT_HERMES_ROOT = Path("/root/hermes")
DEFAULT_NERD_AGENCY_ROOT = Path("/root/nerd-method/nerd-agency")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", cleaned) or "unknown"


def _safe_read_json(path: Path, default: object) -> object:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return default


def _objectives(path: Path) -> list[dict[str, object]]:
    payload = _safe_read_json(path, {})
    if isinstance(payload, dict) and isinstance(payload.get("objectives"), list):
        return [item for item in payload["objectives"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _status(path: Path) -> dict[str, object]:
    payload = _safe_read_json(path, {})
    return payload if isinstance(payload, dict) else {}


def _priority_risk(priority: str) -> str:
    return "medium" if priority.lower() in {"high", "urgent", "p0", "p1"} else "low"


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
    return item


def _path_status(path: Path) -> str:
    return "present" if path.exists() else "missing"


def build_hermes_agents_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    hermes_root: Path = DEFAULT_HERMES_ROOT,
    nerd_agency_root: Path = DEFAULT_NERD_AGENCY_ROOT,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    hermes_root = Path(hermes_root)
    nerd_agency_root = Path(nerd_agency_root)

    core = hermes_root / "core"
    ceo_identity = core / "CEO_IDENTITY.md"
    objectives_file = core / "objectives.json"
    status_file = core / "status.json"
    mirror_core = (
        nerd_agency_root / "nerd-departments" / "nerd-system-development" / "core"
    )

    objectives = _objectives(objectives_file)
    status = _status(status_file)
    last_heartbeat = status.get("last_heartbeat")
    active_departments = status.get("active_departments")
    if not isinstance(active_departments, list):
        active_departments = []

    ceo_status = "active" if ceo_identity.is_file() or last_heartbeat else "missing"
    items: list[dict[str, object]] = [
        _item(
            id="hermes-agent-ceo",
            name="Hermes CEO",
            kind="agent",
            classification="strategic_agent",
            status=ceo_status,
            risk="medium",
            path=ceo_identity,
            evidence=[
                str(path)
                for path in (ceo_identity, status_file, objectives_file)
                if path.exists()
            ],
            metadata={
                "adapter_type": "hermes_local",
                "autonomy_level": "L1",
                "model_profile": "ops_fast",
                "last_heartbeat": last_heartbeat,
                "active_departments": active_departments,
                "objective_count": len(objectives),
            },
            notes="Read-only bridge for the existing Hermes CEO identity, status, and objective state.",
        ),
        _item(
            id="hermes-status",
            name="Hermes Status",
            kind="state_file",
            classification="runtime_status",
            status=_path_status(status_file),
            risk="medium",
            path=status_file,
            evidence=[str(status_file)] if status_file.exists() else [],
            metadata={
                "last_heartbeat": last_heartbeat,
                "active_departments": active_departments,
            },
            notes="Hermes heartbeat state. Registry generation does not touch the runtime.",
        ),
        _item(
            id="hermes-objectives",
            name="Hermes Objective Set",
            kind="objective_set",
            classification="objective_backlog",
            status=_path_status(objectives_file),
            risk="medium",
            path=objectives_file,
            evidence=[str(objectives_file)] if objectives_file.exists() else [],
            metadata={"objective_count": len(objectives)},
            notes="Hermes objective backlog parsed into individual canonical records.",
        ),
        _item(
            id="hermes-agency-core-mirror",
            name="NERD Agency Hermes Core Mirror",
            kind="mirror",
            classification="agency_core_mirror",
            status=_path_status(mirror_core),
            risk="medium",
            path=mirror_core,
            evidence=[str(mirror_core)] if mirror_core.exists() else [],
            metadata={
                "file_count": sum(1 for item in mirror_core.glob("*") if item.is_file())
                if mirror_core.is_dir()
                else 0
            },
            notes="Mirror of Hermes core material under the NERD agency tree.",
        ),
    ]

    for objective in objectives:
        objective_id = str(
            objective.get("id") or slugify(str(objective.get("title") or "objective"))
        )
        title = str(objective.get("title") or objective_id)
        status_value = str(objective.get("status") or "unknown")
        priority = str(objective.get("prio") or objective.get("priority") or "")
        items.append(
            _item(
                id=f"hermes-objective-{slugify(objective_id)}",
                name=title,
                kind="objective",
                classification="hermes_objective",
                status=status_value,
                risk=_priority_risk(priority),
                path=objectives_file,
                evidence=[str(objectives_file)],
                metadata={
                    "objective_id": objective_id,
                    "department": objective.get("dept") or objective.get("department"),
                    "priority": priority,
                    "description": objective.get("description"),
                    "dispatched_at": objective.get("dispatched_at"),
                },
                notes="Existing Hermes objective exposed as a read-only NERD OS agent/task record.",
            )
        )

    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_hermes_agents_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    hermes_root: Path = DEFAULT_HERMES_ROOT,
    nerd_agency_root: Path = DEFAULT_NERD_AGENCY_ROOT,
) -> Path:
    output = Path(canonical_root) / "registry" / "hermes-agents.json"
    registry = build_hermes_agents_registry(
        canonical_root=canonical_root,
        hermes_root=hermes_root,
        nerd_agency_root=nerd_agency_root,
    )
    return write_json(output, registry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write NERD Hermes agents registry.")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--hermes-root", type=Path, default=DEFAULT_HERMES_ROOT)
    parser.add_argument(
        "--nerd-agency-root", type=Path, default=DEFAULT_NERD_AGENCY_ROOT
    )
    args = parser.parse_args(argv)
    output = write_hermes_agents_registry(
        canonical_root=args.canonical_root,
        hermes_root=args.hermes_root,
        nerd_agency_root=args.nerd_agency_root,
    )
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
