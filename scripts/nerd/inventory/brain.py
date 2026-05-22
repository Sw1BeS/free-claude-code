from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.models import (
        Action,
        InventoryItem,
        InventoryReport,
        Kind,
        Risk,
        Status,
    )
    from scripts.nerd.inventory.workspace import generated_at
else:
    from .models import Action, InventoryItem, InventoryReport, Kind, Risk, Status
    from .workspace import generated_at


def _local_status(path: Path) -> str:
    return "present" if path.exists() else "investigate"


def _item(
    *,
    item_id: str,
    name: str,
    kind: str,
    status: str,
    domain: str,
    risk: str,
    action: str,
    path: Path | None = None,
    source_url: str | None = None,
    notes: str | None = None,
) -> InventoryItem:
    evidence = []
    if path is not None and path.exists():
        evidence.append(str(path))
    if source_url is not None:
        evidence.append(source_url)
    return InventoryItem(
        id=item_id,
        name=name,
        kind=cast(Kind, kind),
        status=cast(Status, status),
        domain=domain,
        risk=cast(Risk, risk),
        path=str(path) if path else None,
        source_url=source_url,
        evidence=evidence,
        recommended_action=cast(Action, action),
        notes=notes,
    )


def build_brain_report(
    workspace_root: Path,
    agency_stack_dir: Path,
    staging_dir: Path,
    nerd_method_dir: Path,
    obsidian_vault_dir: Path,
) -> InventoryReport:
    items: list[InventoryItem] = []
    warnings: list[str] = []

    markdown_notes = (
        sorted(obsidian_vault_dir.rglob("*.md")) if obsidian_vault_dir.exists() else []
    )
    if len(markdown_notes) < 2:
        warnings.append(
            f"{obsidian_vault_dir}: fewer than two Markdown notes found for the brain surface"
        )
    if not (nerd_method_dir / ".git").is_dir():
        warnings.append(f"{nerd_method_dir}: not a git repository")

    items.extend(
        [
            _item(
                item_id="brain-canonical-repo",
                name="Brain Canonical Repo",
                kind="repo",
                status=_local_status(staging_dir),
                domain="brain-source",
                risk="medium",
                action="keep",
                path=staging_dir,
                notes="Versioned implementation source for NERD-METHOD inventory and sync scripts",
            ),
            _item(
                item_id="brain-runtime-stack",
                name="Brain Runtime Stack",
                kind="dir",
                status=_local_status(agency_stack_dir),
                domain="brain-runtime",
                risk="medium",
                action="keep",
                path=agency_stack_dir,
                notes="Live runtime target for Mission Control and local brain services",
            ),
            _item(
                item_id="brain-nerd-method",
                name="NERD Method Knowledge",
                kind="repo",
                status=_local_status(nerd_method_dir),
                domain="brain-knowledge",
                risk="medium",
                action="normalize",
                path=nerd_method_dir,
                notes="Knowledge repo expected to hold normalized NERD-METHOD operating material",
            ),
            _item(
                item_id="brain-openwebui-knowledge",
                name="Open WebUI Knowledge Surface",
                kind="service",
                status="investigate",
                domain="brain-surface",
                risk="medium",
                action="normalize",
                source_url="https://agency.umanoff-analytics.space",
                notes="Public knowledge surface; verify seeded docs through controlled sync",
            ),
            _item(
                item_id="brain-obsidian-vault",
                name="Obsidian Vault",
                kind="dir",
                status=_local_status(obsidian_vault_dir),
                domain="brain-surface",
                risk="low",
                action="normalize",
                path=obsidian_vault_dir,
                notes=f"markdown_note_count={len(markdown_notes)}",
            ),
            _item(
                item_id="brain-gitnexus",
                name="GitNexus Code Graph",
                kind="service",
                status="active",
                domain="brain-codegraph",
                risk="low",
                action="keep",
                source_url="http://127.0.0.1:4173",
                notes="Internal loopback code graph service",
            ),
            _item(
                item_id="brain-n8n",
                name="n8n Automation",
                kind="service",
                status="active",
                domain="brain-automation",
                risk="medium",
                action="keep",
                source_url="http://127.0.0.1:5678",
                notes="Internal loopback automation service",
            ),
            _item(
                item_id="brain-langfuse",
                name="Langfuse Observability",
                kind="service",
                status="active",
                domain="brain-observability",
                risk="low",
                action="keep",
                source_url="http://127.0.0.1:3300",
                notes="Internal loopback observability service",
            ),
        ]
    )

    sync_targets = {
        "brain-sync-openwebui-seed": (
            "Open WebUI Seed Script",
            staging_dir / "scripts" / "nerd" / "agency" / "openwebui_seed.py",
        ),
        "brain-sync-inventory": (
            "Inventory Generator",
            staging_dir / "scripts" / "nerd" / "generate_inventory.py",
        ),
        "brain-sync-stack-seed": (
            "Runtime Open WebUI Seed Script",
            agency_stack_dir / "scripts" / "seed-openwebui.sh",
        ),
    }
    for item_id, (name, path) in sync_targets.items():
        items.append(
            _item(
                item_id=item_id,
                name=name,
                kind="config",
                status=_local_status(path),
                domain="brain-sync",
                risk="medium",
                action="keep",
                path=path,
                notes="Deterministic brain sync target",
            )
        )

    _ = workspace_root
    return InventoryReport(generated_at=generated_at(), items=items, warnings=warnings)
