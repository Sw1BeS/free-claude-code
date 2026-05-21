from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.models import InventoryItem, slugify
else:
    from .models import InventoryItem, slugify

KNOWN_SKILL_ROOTS = (
    Path("/root/.agents/plugins/skills"),
    Path("/root/.agents/skills"),
    Path("/root/.claude/skills"),
    Path("/root/.claude/skills/skills"),
    Path("/root/.codex/skills"),
    Path("/root/.hermes/skills"),
)

DOMAIN_KEYWORDS = {
    "wordpress": ("wordpress", "woocommerce"),
    "shopify": ("shopify",),
    "n8n": ("n8n",),
    "github": ("github", "git-pr", "pull-request"),
    "gitnexus": ("gitnexus",),
    "design": ("design", "ui-ux", "frontend", "stitch"),
    "security": ("security", "hacking", "pentest", "xss", "sast"),
    "data": ("data", "analytics", "database", "vector"),
    "obsidian": ("obsidian",),
    "telegram": ("telegram",),
    "scraping": ("crawl", "scrape", "firecrawl", "apify"),
    "chrome": ("chrome-extension", "chrome"),
    "mcp": ("mcp",),
    "agents": ("agent", "orchestration"),
    "finance": ("trading", "betting", "money", "monte-carlo"),
}


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_skill_file(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return {"name": path.parent.name}

    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = _strip_quotes(value)

    data.setdefault("name", path.parent.name)
    return data


def classify_domain(name: str, description: str) -> str:
    haystack = f"{name} {description}".lower()
    for domain, needles in DOMAIN_KEYWORDS.items():
        if any(needle in haystack for needle in needles):
            return domain
    return "general"


def scan_skill_roots(
    roots: list[Path] | tuple[Path, ...] = KNOWN_SKILL_ROOTS,
) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    seen_ids: set[str] = set()
    seen_paths: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for skill_file in sorted(root.rglob("SKILL.md")):
            resolved = skill_file.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            parsed = parse_skill_file(skill_file)
            name = parsed.get("name", skill_file.parent.name)
            description = parsed.get("description", "")
            risk = "low" if parsed.get("risk") in {"safe", "low"} else "unknown"
            domain = classify_domain(name, description)
            item_id = f"skill-{slugify(name)}"
            if item_id in seen_ids:
                item_id = f"{item_id}-{slugify(str(skill_file.parent))}"
            seen_ids.add(item_id)
            items.append(
                InventoryItem(
                    id=item_id,
                    name=name,
                    kind="skill",
                    status="present",
                    domain=domain,
                    risk=risk,
                    path=str(skill_file.parent),
                    evidence=[str(skill_file)],
                    recommended_action="normalize",
                    notes=description or None,
                )
            )
    return items
