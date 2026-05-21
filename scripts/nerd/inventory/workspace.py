from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.git_utils import read_git_metadata
    from scripts.nerd.inventory.models import (
        InventoryItem,
        InventoryReport,
        Kind,
        Risk,
        Status,
        slugify,
    )
else:
    from .git_utils import read_git_metadata
    from .models import InventoryItem, InventoryReport, Kind, Risk, Status, slugify

SKIP_NAMES = {
    ".cache",
    ".npm",
    ".venv",
    "node_modules",
    "__pycache__",
}


def generated_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_path(path: Path) -> tuple[str, str, str]:
    name = path.name
    if name == "archive" or "archive" in name:
        return "archive", "archived", "medium"
    if name == "free-claude-code":
        return "repo", "legacy", "medium"
    if name == "nerd-claude-free-staging":
        return "repo", "staged", "low"
    if name.startswith(".") and name in {
        ".fcc",
        ".claude",
        ".codex",
        ".hermes",
        ".gitnexus",
    }:
        return "config", "active", "medium"
    if (path / ".git").exists():
        return "repo", "present", "medium"
    return "dir", "present", "unknown"


def _safe_size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.name in SKIP_NAMES:
            continue
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def scan_workspace(root: Path = Path("/root")) -> InventoryReport:
    items: list[InventoryItem] = []
    warnings: list[str] = []
    for child in sorted(root.iterdir(), key=lambda value: value.name):
        if child.name in SKIP_NAMES:
            continue
        try:
            kind, status, risk = classify_path(child)
            git = read_git_metadata(child)
            evidence = [str(child)]
            notes_parts = [f"size_bytes={_safe_size_bytes(child)}"]
            if git.is_repo:
                kind = "repo"
                if git.branch:
                    notes_parts.append(f"branch={git.branch}")
                if git.commit:
                    notes_parts.append(f"commit={git.commit}")
                notes_parts.append(f"dirty={str(git.dirty).lower()}")
                for remote_name, remote_url in git.remotes.items():
                    notes_parts.append(f"remote:{remote_name}={remote_url}")
                if git.warning:
                    warnings.append(f"{child}: {git.warning}")

            items.append(
                InventoryItem(
                    id=slugify(child.name),
                    name=child.name,
                    kind=cast(Kind, kind),
                    status=cast(Status, status),
                    domain="workspace",
                    risk=cast(Risk, risk),
                    path=str(child),
                    evidence=evidence,
                    recommended_action="review_later",
                    notes="; ".join(notes_parts),
                )
            )
        except OSError as exc:
            warnings.append(f"{child}: {exc}")

    return InventoryReport(generated_at=generated_at(), items=items, warnings=warnings)
