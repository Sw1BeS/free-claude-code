from __future__ import annotations

from dataclasses import dataclass

from .models import InventoryItem, InventoryReport, Risk, slugify
from .workspace import generated_at


@dataclass(frozen=True)
class CmsCandidate:
    name: str
    source_url: str
    domain: str
    integration: str
    risk: Risk
    priority: str
    notes: str


CMS_CANDIDATES = (
    CmsCandidate(
        "WordPress agent-skills",
        "https://github.com/WordPress/agent-skills",
        "wordpress",
        "skillpack",
        "low",
        "p0",
        "Official WordPress-oriented skills; install selected packs for wp-playground, block/theme/plugin development, REST, WP-CLI, performance, PHPStan, and WP design system.",
    ),
    CmsCandidate(
        "WordPress MCP Adapter",
        "https://github.com/WordPress/mcp-adapter",
        "wordpress",
        "plugin-mcp",
        "medium",
        "p0",
        "Official Abilities API to MCP bridge; prefer as primary WordPress MCP path with explicit public abilities.",
    ),
    CmsCandidate(
        "WordPress MCP Adapter Guide",
        "https://developer.wordpress.org/news/2026/02/from-abilities-to-ai-agents-introducing-the-wordpress-mcp-adapter/",
        "wordpress",
        "docs",
        "low",
        "p0",
        "Canonical install and exposure guide for WordPress MCP Adapter with Claude Code/Cursor/VS Code client examples.",
    ),
    CmsCandidate(
        "docdyhr mcp-wordpress",
        "https://github.com/docdyhr/mcp-wordpress",
        "wordpress",
        "mcp",
        "medium",
        "p2",
        "Third-party TypeScript WordPress MCP with broad content/site tool coverage; evaluate after official adapter.",
    ),
    CmsCandidate(
        "Automattic wordpress-agent-skills",
        "https://github.com/Automattic/wordpress-agent-skills",
        "wordpress",
        "claude-plugin",
        "high",
        "p1",
        "Experimental Automattic prototypes for block themes and Studio MCP; keep beta-gated.",
    ),
    CmsCandidate(
        "mcp-wp organization",
        "https://github.com/mcp-wp",
        "wordpress",
        "mcp-wpcli",
        "high",
        "p3",
        "Historic community hub; useful for reference, but some projects are archived.",
    ),
    CmsCandidate(
        "Elementor MCP",
        "https://github.com/msrbuilds/elementor-mcp",
        "elementor",
        "plugin-mcp",
        "medium",
        "p1",
        "Elementor-specific MCP surface for page design automation; isolate per-client credentials.",
    ),
    CmsCandidate(
        "MCP Abilities Elementor",
        "https://github.com/bjornfix/mcp-abilities-elementor",
        "elementor",
        "plugin-mcp",
        "medium",
        "p1",
        "Elementor abilities exposed through the WordPress Abilities/MCP architecture; evaluate alongside Elementor MCP.",
    ),
    CmsCandidate(
        "Shopify AI Toolkit",
        "https://github.com/Shopify/shopify-ai-toolkit",
        "shopify",
        "plugin-skillpack",
        "medium",
        "p0",
        "Official Shopify AI plugin/skills with docs, schemas, validation, and store execution patterns; account for telemetry opt-out.",
    ),
    CmsCandidate(
        "Shopify AI Toolkit Docs",
        "https://shopify.dev/docs/apps/build/ai-toolkit",
        "shopify",
        "docs",
        "low",
        "p0",
        "Official Claude Code/Codex/Cursor/VS Code installation path for Shopify AI Toolkit and Dev MCP.",
    ),
    CmsCandidate(
        "Shopify Dev MCP",
        "https://shopify.dev/docs/apps/build/ai-toolkit#install-with-the-dev-mcp-server",
        "shopify",
        "mcp",
        "low",
        "p0",
        "Official local MCP via npx @shopify/dev-mcp for public dev context, docs, schemas, and validation.",
    ),
    CmsCandidate(
        "Shopify Theme Check",
        "https://github.com/Shopify/theme-check",
        "shopify",
        "cli",
        "low",
        "p0",
        "Liquid/theme linting baseline for the Shopify layer and generated theme validation.",
    ),
    CmsCandidate(
        "Shopify CLI",
        "https://shopify.dev/docs/api/shopify-cli/theme",
        "shopify",
        "cli",
        "medium",
        "p0",
        "Official theme/app CLI layer for init/dev/check/push/pull/profile; protect remote writes behind confirmations.",
    ),
    CmsCandidate(
        "Sanity MCP",
        "https://www.sanity.io/docs/ai/mcp-server",
        "cms",
        "remote-mcp",
        "medium",
        "p1",
        "Official Sanity MCP for content/schema/GROQ/releases with OAuth/token write access.",
    ),
    CmsCandidate(
        "Contentful MCP Server",
        "https://github.com/contentful/contentful-mcp-server",
        "cms",
        "mcp",
        "medium",
        "p1",
        "Official Contentful Management API MCP for entries, assets, content types, localization, and publishing workflows.",
    ),
    CmsCandidate(
        "Strapi MCP workflow",
        "https://strapi.io/blog/claude-code-strapi-mcp-ai-content-workflows",
        "cms",
        "plugin-mcp",
        "high",
        "p3",
        "Development/local-only community plugin workflow; revisit when native production MCP support matures.",
    ),
)


def build_cms_candidate_report(
    candidates: tuple[CmsCandidate, ...] = CMS_CANDIDATES,
) -> InventoryReport:
    items = [
        InventoryItem(
            id=f"cms-{slugify(candidate.name)}",
            name=candidate.name,
            kind="candidate",
            status="missing",
            domain=candidate.domain,
            risk=candidate.risk,
            source_url=candidate.source_url,
            recommended_action="install_later",
            notes=(
                f"priority={candidate.priority}; integration={candidate.integration}; "
                f"{candidate.notes}"
            ),
        )
        for candidate in candidates
    ]
    return InventoryReport(generated_at=generated_at(), items=items)
