from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import (
    DEFAULT_CANONICAL_ROOT,
    ExistingWorkItem,
    write_json,
)

DEFAULT_ROOTS = (
    Path("/root/nerd-method"),
    Path("/root/nerd-agency-stack"),
    Path("/root/nerd-claude-free-staging"),
    Path("/root/free-claude-code"),
    Path("/root/hermes"),
    Path("/root/nerd-method/tools/git-inspired"),
    Path("/root/nerd-method/operations/ruflo-workspace"),
    Path("/root/nerd-claude-free-staging/docs/nerd_inventory"),
)


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", cleaned)


def _base_item(path: Path, canonical_root: Path) -> ExistingWorkItem:
    name = path.name
    resolved = path.resolve()
    canonical_resolved = canonical_root.resolve()
    if resolved == canonical_resolved or name == "nerd-method":
        return ExistingWorkItem(
            id="root-nerd-method",
            name="NERD Method Canonical Root",
            kind="root",
            classification="active_runtime",
            status="active",
            path=str(path),
            domain="autonomous-core",
            risk="low",
            evidence=[str(path / "AGENTS.md"), str(path / "memory")],
            notes="Product root for Autonomous Core state and memory.",
        )
    if name == "nerd-agency-stack":
        return ExistingWorkItem(
            id="runtime-nerd-agency-stack",
            name="NERD Agency Stack",
            kind="runtime",
            classification="active_runtime",
            status="active",
            path=str(path),
            domain="runtime-stack",
            risk="low",
            evidence=[str(path / "nerd-os.actions.yaml")],
            notes="Domain stack and n8n/action registry runtime.",
        )
    if name == "nerd-claude-free-staging":
        return ExistingWorkItem(
            id="workspace-nerd-claude-free-staging",
            name="NERD Claude Free Staging",
            kind="workspace",
            classification="active_runtime",
            status="active",
            path=str(path),
            domain="free-claude-adapter",
            risk="low",
            evidence=[str(path / "scripts" / "nerd")],
            notes="Adapter workspace, not the OS root.",
        )
    if name == "free-claude-code":
        return ExistingWorkItem(
            id="legacy-free-claude-code",
            name="Free Claude Code Legacy Checkout",
            kind="workspace",
            classification="legacy_runtime",
            status="present",
            path=str(path),
            domain="free-claude-adapter",
            risk="medium",
            notes="Reference checkout retained as fallback.",
        )
    if name == "hermes":
        return ExistingWorkItem(
            id="candidate-hermes",
            name="Hermes",
            kind="runtime",
            classification="candidate_runtime",
            status="present",
            path=str(path),
            domain="autonomy",
            risk="medium",
            notes="Autopilot experiments must use shared policy before deeper activation.",
        )
    if name == "git-inspired":
        return ExistingWorkItem(
            id="source-cache-gitinspired",
            name="GitInspired Source Cache",
            kind="repo-cache",
            classification="source_cache",
            status="present",
            path=str(path),
            domain="research",
            risk="low",
            notes="Interested repositories are cached here before promotion.",
        )
    if name == "ruflo-workspace":
        return ExistingWorkItem(
            id="candidate-ruflo-workspace",
            name="Ruflo Workspace",
            kind="mcp-workspace",
            classification="candidate_runtime",
            status="present",
            path=str(path),
            domain="mcp",
            risk="medium",
            evidence=[str(path / ".mcp.json")],
            notes="MCP workspace candidate for controlled tool access.",
        )
    if name == "nerd_inventory":
        return ExistingWorkItem(
            id="report-cache-nerd-inventory",
            name="NERD Inventory Reports",
            kind="report-cache",
            classification="active_runtime",
            status="active",
            path=str(path),
            domain="inventory",
            risk="low",
            notes="Generated reports used by NERD OS and memory.",
        )
    return ExistingWorkItem(
        id=f"path-{slugify(name)}",
        name=name,
        kind="dir",
        classification="research_only",
        status="present",
        path=str(path),
        domain="general",
        risk="unknown",
    )


def _workflow_risk(path: Path) -> str:
    value = path.name.lower()
    if any(token in value for token in ("github", "cms", "commerce")):
        return "medium"
    return "low"


def _scan_workflows(root: Path) -> list[ExistingWorkItem]:
    workflows_dir = root / "n8n" / "v1-workflows"
    if root.name == "v1-workflows":
        workflows_dir = root
    if not workflows_dir.is_dir():
        return []

    items = []
    for workflow in sorted(workflows_dir.glob("*.json")):
        risk = _workflow_risk(workflow)
        items.append(
            ExistingWorkItem(
                id=f"workflow-{slugify(workflow.stem)}",
                name=workflow.stem.replace("-", " ").replace("_", " ").title(),
                kind="workflow",
                classification="active_runtime",
                status="active",
                path=str(workflow),
                domain="automations",
                risk=risk,  # type: ignore[arg-type]
                evidence=[str(workflow)],
                notes=(
                    "Visible workflow record. Medium-risk workflows require approval."
                    if risk == "medium"
                    else "Visible allowlisted workflow candidate."
                ),
            )
        )
    return items


def _scan_inventory_reports(root: Path) -> list[ExistingWorkItem]:
    reports_dir = root
    if root.name != "nerd_inventory":
        reports_dir = root / "docs" / "nerd_inventory"
    if not reports_dir.is_dir():
        return []
    return [
        ExistingWorkItem(
            id=f"inventory-report-{slugify(report.stem)}",
            name=report.stem.replace("-", " ").title(),
            kind="report",
            classification="active_runtime",
            status="active",
            path=str(report),
            domain="inventory",
            risk="low",
            evidence=[str(report)],
        )
        for report in sorted(reports_dir.glob("*.json"))
    ]


def _scan_gitinspired_children(root: Path) -> list[ExistingWorkItem]:
    if root.name != "git-inspired" or not root.is_dir():
        return []
    return [
        ExistingWorkItem(
            id=f"gitinspired-{slugify(child.name)}",
            name=child.name,
            kind="repo",
            classification="source_cache",
            status="present",
            path=str(child),
            domain="research",
            risk="unknown",
            evidence=[str(child)],
        )
        for child in sorted(path for path in root.iterdir() if path.is_dir())
    ]


def build_existing_work_registry(
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    roots: Iterable[Path] = DEFAULT_ROOTS,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    items: list[ExistingWorkItem] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()

    def append(item: ExistingWorkItem) -> None:
        if item.id in seen_ids:
            return
        seen_ids.add(item.id)
        items.append(item)

    for root in roots:
        root = Path(root)
        if not root.exists():
            warnings.append(f"missing root: {root}")
            continue
        append(_base_item(root, canonical_root))
        for child_item in _scan_workflows(root):
            append(child_item)
        for child_item in _scan_inventory_reports(root):
            append(child_item)
        for child_item in _scan_gitinspired_children(root):
            append(child_item)

    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": [
            item.to_dict()
            for item in sorted(items, key=lambda existing: (existing.kind, existing.id))
        ],
        "warnings": sorted(set(warnings)),
    }


def write_existing_work_registry(
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    roots: Iterable[Path] = DEFAULT_ROOTS,
) -> Path:
    output = Path(canonical_root) / "registry" / "existing-work.json"
    registry = build_existing_work_registry(canonical_root=canonical_root, roots=roots)
    return write_json(output, registry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write NERD existing-work registry.")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--root", dest="roots", type=Path, action="append")
    args = parser.parse_args(argv)

    output = write_existing_work_registry(
        canonical_root=args.canonical_root,
        roots=args.roots or DEFAULT_ROOTS,
    )
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
