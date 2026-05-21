from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.git_utils import ahead_behind
    from scripts.nerd.inventory.models import InventoryItem, InventoryReport, slugify
    from scripts.nerd.inventory.workspace import generated_at
else:
    from .git_utils import ahead_behind
    from .models import InventoryItem, InventoryReport, slugify
    from .workspace import generated_at


def static_claudecore_components() -> list[dict[str, str]]:
    return [
        {
            "path": "api",
            "domain": "api",
            "notes": "FastAPI routes, admin UI, request handling, runtime lifecycle.",
        },
        {
            "path": "cli",
            "domain": "cli",
            "notes": "fcc-server, fcc-claude, process/session handling.",
        },
        {
            "path": "config",
            "domain": "config",
            "notes": "Settings, provider config, constants, logging.",
        },
        {
            "path": "providers",
            "domain": "providers",
            "notes": (
                "Kimi, NVIDIA NIM, Wafer, OpenRouter, DeepSeek, Fireworks, "
                "Z.ai, OpenCode, local providers."
            ),
        },
        {
            "path": "messaging",
            "domain": "messaging",
            "notes": "Discord/Telegram command and session layer.",
        },
        {
            "path": "core",
            "domain": "core",
            "notes": "Anthropic request/stream conversion and shared primitives.",
        },
        {
            "path": "scripts/nerd",
            "domain": "nerd",
            "notes": "NERD wrappers, migration utilities, inventory tooling.",
        },
        {
            "path": "docs",
            "domain": "docs",
            "notes": "Runbooks, specs, plans, generated inventory reports.",
        },
    ]


def _branch_notes(staging_dir: Path, legacy_dir: Path) -> str:
    staged = ahead_behind(staging_dir, "HEAD", "upstream/main")
    legacy = ahead_behind(legacy_dir, "HEAD", "origin/main")
    return (
        f"staged_ahead={staged['ahead']}; staged_behind={staged['behind']}; "
        f"legacy_ahead={legacy['ahead']}; legacy_behind={legacy['behind']}"
    )


def build_claudecore_codemap(
    staging_dir: Path = Path("/root/nerd-claude-free-staging"),
    legacy_dir: Path = Path("/root/free-claude-code"),
) -> InventoryReport:
    items: list[InventoryItem] = []
    for component in static_claudecore_components():
        rel_path = component["path"]
        full_path = staging_dir / rel_path
        items.append(
            InventoryItem(
                id=f"codemap-{slugify(rel_path)}",
                name=rel_path,
                kind="dir",
                status="present" if full_path.exists() else "missing",
                domain=component["domain"],
                risk="low",
                path=str(full_path),
                evidence=[str(full_path)] if full_path.exists() else [],
                recommended_action="keep" if full_path.exists() else "review_later",
                notes=component["notes"],
            )
        )

    items.append(
        InventoryItem(
            id="codemap-upstream-status",
            name="ClaudeCore upstream status",
            kind="repo",
            status="staged",
            domain="upstream",
            risk="medium",
            path=str(staging_dir),
            evidence=[str(staging_dir), str(legacy_dir)],
            recommended_action="review_later",
            notes=_branch_notes(staging_dir, legacy_dir),
        )
    )
    return InventoryReport(generated_at=generated_at(), items=items)
