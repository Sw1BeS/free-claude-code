#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.nerd.inventory.brain import build_brain_report
    from scripts.nerd.inventory.cms import build_cms_candidate_report
    from scripts.nerd.inventory.codemap import build_claudecore_codemap
    from scripts.nerd.inventory.gitinspired import build_gitinspired_catalog
    from scripts.nerd.inventory.mission_control import build_mission_control_report
    from scripts.nerd.inventory.models import InventoryReport
    from scripts.nerd.inventory.render import render_report_markdown, write_report_pair
    from scripts.nerd.inventory.skills import KNOWN_SKILL_ROOTS, scan_skill_roots
    from scripts.nerd.inventory.workspace import generated_at, scan_workspace
else:
    from .inventory.brain import build_brain_report
    from .inventory.cms import build_cms_candidate_report
    from .inventory.codemap import build_claudecore_codemap
    from .inventory.gitinspired import build_gitinspired_catalog
    from .inventory.mission_control import build_mission_control_report
    from .inventory.models import InventoryReport
    from .inventory.render import render_report_markdown, write_report_pair
    from .inventory.skills import KNOWN_SKILL_ROOTS, scan_skill_roots
    from .inventory.workspace import generated_at, scan_workspace


def write_backlog(output_dir: Path) -> None:
    lines = [
        "# Next Phase Backlog",
        "",
        "1. Harden unified brain sync across NERD reports, Open WebUI knowledge, Obsidian, GitNexus, n8n, and runtime manifests.",
        (
            "2. Normalize installed WordPress, Shopify, n8n, NotebookLM, "
            "Obsidian, GitHub, data, and security skills into an activation manifest."
        ),
        "3. Install/evaluate P0 CMS connectors: WordPress agent-skills, WordPress MCP Adapter, Shopify AI Toolkit, Shopify Dev MCP, Shopify CLI, and Theme Check.",
        "4. Design the WordPress/CMS workbench layer.",
        "5. Design the Shopify commerce layer.",
        "6. Design the n8n/MCP connector library.",
        "7. Design Mac companion install, sync, and task routing.",
        "8. Design data ingestion and automatic triage.",
        "9. Design commercialization and prompt/product library.",
        "10. Split high-risk security research into defensive, legal, opt-in modules only.",
        "",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "next-phase-backlog.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate NERD workspace inventory reports."
    )
    parser.add_argument("--workspace-root", type=Path, default=Path("/root"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/nerd_inventory"))
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=Path("/root/nerd-claude-free-staging"),
    )
    parser.add_argument(
        "--legacy-dir",
        type=Path,
        default=Path("/root/free-claude-code"),
    )
    parser.add_argument(
        "--agency-stack-dir",
        type=Path,
        default=Path("/root/nerd-agency-stack"),
    )
    parser.add_argument(
        "--nerd-method-dir",
        type=Path,
        default=Path("/root/nerd-method"),
    )
    parser.add_argument(
        "--obsidian-vault-dir",
        type=Path,
        default=Path("/root/obsidian-vault"),
    )
    parser.add_argument("--skip-real-skills", action="store_true")
    parser.add_argument("--skip-real-gitinspired-search", action="store_true")
    args = parser.parse_args(argv)

    workspace_report = scan_workspace(args.workspace_root)
    skill_roots = [] if args.skip_real_skills else list(KNOWN_SKILL_ROOTS)
    skills_report = InventoryReport(
        generated_at=generated_at(),
        items=scan_skill_roots(skill_roots),
    )
    gitinspired_roots = [
        args.workspace_root / ".agents" / "plugins" / "skills",
        args.workspace_root / ".agents" / "skills",
        args.workspace_root / ".claude" / "skills",
        args.workspace_root / ".hermes" / "skills",
        args.workspace_root / ".gitnexus",
        args.workspace_root / "free-claude-code",
        args.workspace_root / "nerd-method",
        args.workspace_root / "hermes",
    ]
    if args.skip_real_gitinspired_search:
        gitinspired_roots = [args.workspace_root / "__empty__"]
    gitinspired_report = build_gitinspired_catalog(search_roots=gitinspired_roots)
    codemap_report = build_claudecore_codemap(args.staging_dir, args.legacy_dir)
    cms_report = build_cms_candidate_report()
    mission_report = build_mission_control_report(args.agency_stack_dir)
    brain_report = build_brain_report(
        args.workspace_root,
        args.agency_stack_dir,
        args.staging_dir,
        args.nerd_method_dir,
        args.obsidian_vault_dir,
    )

    write_report_pair(
        args.output_dir, "workspace-map", "Workspace Map", workspace_report
    )
    write_report_pair(
        args.output_dir, "skills-inventory", "Skills Inventory", skills_report
    )
    write_report_pair(
        args.output_dir,
        "gitinspired-catalog",
        "GitInspired Catalog",
        gitinspired_report,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "claudecore-codemap.md").write_text(
        render_report_markdown("ClaudeCore Codemap", codemap_report),
        encoding="utf-8",
    )
    write_report_pair(
        args.output_dir,
        "cms-candidates",
        "CMS And Commerce Candidates",
        cms_report,
    )
    write_report_pair(
        args.output_dir,
        "mission-control-stack",
        "Mission Control Stack",
        mission_report,
    )
    write_report_pair(
        args.output_dir,
        "nerd-method-brain",
        "NERD Method Brain",
        brain_report,
    )
    write_backlog(args.output_dir)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
