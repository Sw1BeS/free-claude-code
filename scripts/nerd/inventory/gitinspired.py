from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.models import (
        Action,
        InventoryItem,
        InventoryReport,
        Status,
        slugify,
    )
    from scripts.nerd.inventory.workspace import generated_at
else:
    from .models import Action, InventoryItem, InventoryReport, Status, slugify
    from .workspace import generated_at

SKIP_DIR_NAMES = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".npm",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
MAX_EVIDENCE = 8


@dataclass(frozen=True)
class GitInspiredRepo:
    name: str
    source_url: str
    domain: str
    aliases: tuple[str, ...]
    notes: str = ""


GITINSPIRED_REPOS = (
    GitInspiredRepo(
        "awesome-claude-skills",
        "https://github.com/travisvn/awesome-claude-skills",
        "skills",
        ("awesome-claude-skills", "claude-skills"),
    ),
    GitInspiredRepo(
        "OpenMythos",
        "https://github.com/kyegomez/OpenMythos",
        "agents",
        ("openmythos",),
    ),
    GitInspiredRepo(
        "awesome-design-systems",
        "https://github.com/alexpate/awesome-design-systems",
        "design",
        ("awesome-design-systems", "design-systems"),
    ),
    GitInspiredRepo(
        "Awesome-Hacking",
        "https://github.com/Hack-with-Github/Awesome-Hacking",
        "security",
        ("awesome-hacking", "hacking"),
    ),
    GitInspiredRepo(
        "awesome-openclaw-skills",
        "https://github.com/VoltAgent/awesome-openclaw-skills",
        "skills",
        ("awesome-openclaw-skills", "openclaw"),
    ),
    GitInspiredRepo(
        "open-design",
        "https://github.com/nexu-io/open-design",
        "design",
        ("open-design",),
    ),
    GitInspiredRepo(
        "ECC",
        "https://github.com/affaan-m/ECC",
        "claude",
        ("ecc", "everything-claude-code"),
    ),
    GitInspiredRepo(
        "awesome-copilot",
        "https://github.com/github/awesome-copilot",
        "github",
        ("awesome-copilot", "copilot"),
    ),
    GitInspiredRepo(
        "OpenJarvis",
        "https://github.com/open-jarvis/OpenJarvis",
        "agents",
        ("openjarvis", "jarvis"),
    ),
    GitInspiredRepo(
        "9router",
        "https://github.com/decolua/9router",
        "routing",
        ("9router",),
    ),
    GitInspiredRepo(
        "notebooklm-skill",
        "https://github.com/PleasePrompto/notebooklm-skill",
        "google",
        ("notebooklm", "notebooklm-skill"),
    ),
    GitInspiredRepo(
        "openui",
        "https://github.com/thesysdev/openui",
        "ui",
        ("openui", "open-ui"),
    ),
    GitInspiredRepo(
        "GitNexus",
        "https://github.com/abhigyanpatwari/GitNexus",
        "gitnexus",
        ("gitnexus",),
    ),
    GitInspiredRepo(
        "CloakBrowser",
        "https://github.com/CloakHQ/CloakBrowser",
        "browser-automation",
        ("cloakbrowser", "cloak-browser", "cloak"),
        "Playwright/Puppeteer-compatible stealth browser; high-risk automation candidate that should remain disabled by default until policy reviewed.",
    ),
    GitInspiredRepo(
        "ruflo",
        "https://github.com/ruvnet/ruflo",
        "agents",
        ("ruflo", "ruvflo", "claude-flow"),
        "Multi-agent orchestration candidate for Claude Code with MCP, server, plugin, memory, and swarm capabilities.",
    ),
    GitInspiredRepo(
        "codegraph",
        "https://github.com/colbymchenry/codegraph",
        "code-graph",
        ("codegraph", "code-graph"),
        "Local code knowledge graph candidate with CLI/MCP tools for search, context, callers, and impact analysis.",
    ),
    GitInspiredRepo(
        "cc-switch",
        "https://github.com/farion1231/cc-switch",
        "desktop-control",
        ("cc-switch", "ccswitch"),
        "Desktop all-in-one assistant candidate for Claude Code, Codex, OpenCode, OpenClaw, Gemini CLI, and Hermes Agent workflows.",
    ),
    GitInspiredRepo(
        "notebooklm-py",
        "https://github.com/teng-lin/notebooklm-py",
        "google",
        ("notebooklm-py", "notebooklm", "notebook-lm"),
        "Unofficial NotebookLM Python API, CLI, and agent skill candidate for bulk import/export and research automation.",
    ),
    GitInspiredRepo(
        "agency-agents",
        "https://github.com/msitarzewski/agency-agents",
        "agents",
        ("agency-agents",),
        "Agent-role pack candidate for reusable role definitions; not a runtime service.",
    ),
    GitInspiredRepo(
        "dify",
        "https://github.com/langgenius/dify",
        "agents",
        ("dify",),
    ),
    GitInspiredRepo(
        "hackingtool",
        "https://github.com/Z4nzu/hackingtool",
        "security",
        ("hackingtool",),
    ),
    GitInspiredRepo(
        "ui-ux-pro-max-skill",
        "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill",
        "design",
        ("ui-ux-pro-max", "ui-ux"),
    ),
    GitInspiredRepo(
        "mattpocock-skills",
        "https://github.com/mattpocock/skills",
        "skills",
        ("mattpocock",),
    ),
    GitInspiredRepo(
        "composio-awesome-claude-skills",
        "https://github.com/ComposioHQ/awesome-claude-skills",
        "skills",
        ("composio", "awesome-claude-skills"),
    ),
    GitInspiredRepo(
        "crawl4ai",
        "https://github.com/unclecode/crawl4ai",
        "scraping",
        ("crawl4ai", "crawl"),
    ),
    GitInspiredRepo(
        "spec-kit",
        "https://github.com/github/spec-kit",
        "github",
        ("spec-kit",),
    ),
    GitInspiredRepo(
        "successor-agent",
        "https://github.com/lyc-aon/successor-agent",
        "agents",
        ("successor-agent",),
    ),
    GitInspiredRepo(
        "MiroFish",
        "https://github.com/666ghj/MiroFish",
        "agents",
        ("mirofish",),
    ),
    GitInspiredRepo(
        "TradingAgents",
        "https://github.com/TauricResearch/TradingAgents",
        "finance",
        ("tradingagents", "trading-agents"),
    ),
    GitInspiredRepo(
        "n8n-workflows",
        "https://github.com/Zie619/n8n-workflows",
        "n8n",
        ("n8n-workflows", "n8n"),
    ),
    GitInspiredRepo(
        "graphify",
        "https://github.com/safishamsi/graphify",
        "knowledge",
        ("graphify",),
    ),
)


def _name_tokens(name: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", name.lower()) if token}


def _matches_alias(name: str, aliases: tuple[str, ...]) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    tokens = _name_tokens(name)
    for alias in aliases:
        normalized_alias = re.sub(r"[^a-z0-9]+", "-", alias.lower()).strip("-")
        if not normalized_alias:
            continue
        if len(normalized_alias) <= 4:
            if normalized_alias in tokens or normalized == normalized_alias:
                return True
            continue
        if normalized_alias in normalized:
            return True
    return False


def _find_evidence(aliases: tuple[str, ...], search_roots: list[Path]) -> list[str]:
    evidence: list[str] = []
    for root in search_roots:
        if not root.exists():
            continue
        for current_root, dir_names, file_names in os.walk(root):
            dir_names[:] = [name for name in dir_names if name not in SKIP_DIR_NAMES]
            candidates = [*(Path(current_root) / name for name in dir_names)]
            candidates.extend(Path(current_root) / name for name in file_names)
            for child in candidates:
                if len(evidence) >= MAX_EVIDENCE:
                    return sorted(evidence)
                if _matches_alias(child.name, aliases):
                    evidence.append(str(child))
            if len(evidence) >= MAX_EVIDENCE:
                return sorted(evidence)
    return sorted(evidence)


def classify_candidate(
    repo: GitInspiredRepo, search_roots: list[Path]
) -> InventoryItem:
    evidence = _find_evidence(repo.aliases, search_roots)
    if evidence:
        status = "present"
        action = "normalize"
        notes = "Local evidence found; review before installing anything new."
    else:
        status = "missing"
        action = "install_later"
        notes = "No strong local evidence found in configured search roots."

    return InventoryItem(
        id=f"gitinspired-{slugify(repo.name)}",
        name=repo.name,
        kind="candidate",
        status=cast(Status, status),
        domain=repo.domain,
        risk="unknown",
        source_url=repo.source_url,
        evidence=evidence,
        recommended_action=cast(Action, action),
        notes=repo.notes or notes,
    )


def build_gitinspired_catalog(
    repos: tuple[GitInspiredRepo, ...] | list[GitInspiredRepo] = GITINSPIRED_REPOS,
    search_roots: list[Path] | None = None,
) -> InventoryReport:
    roots = search_roots or [
        Path("/root/.agents/plugins/skills"),
        Path("/root/.agents/skills"),
        Path("/root/.claude/skills"),
        Path("/root/.hermes/skills"),
        Path("/root/free-claude-code"),
        Path("/root/nerd-method"),
        Path("/root/hermes"),
    ]
    return InventoryReport(
        generated_at=generated_at(),
        items=[classify_candidate(repo, roots) for repo in repos],
    )
