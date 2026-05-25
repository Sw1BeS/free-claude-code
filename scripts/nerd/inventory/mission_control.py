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


PUBLIC_URL = "https://agency.umanoff-analytics.space"
PUBLIC_DOMAINS = {
    "agency": "Primary Mission Control shell",
    "agents": "Agent task workspaces routed to Mission Control",
    "automations": "Automation workspace routed to Mission Control",
    "memory": "Unified memory and knowledge workspace routed to Mission Control",
    "obs": "Observability workspace routed to Mission Control",
    "cms": "CMS and commerce workspace routed to Mission Control",
}
INTERNAL_SERVICES = {
    "open-webui": "https://agency.umanoff-analytics.space",
    "n8n": "https://automations.umanoff-analytics.space",
    "langfuse": "https://obs.umanoff-analytics.space",
    "litellm": "https://agency.umanoff-analytics.space/nerd-os/",
    "ollama": "https://agency.umanoff-analytics.space/nerd-os/",
    "grafana": "https://obs.umanoff-analytics.space",
    "gitnexus": "https://agency.umanoff-analytics.space/nerd-os/",
    "free-claude-admin": "https://agency.umanoff-analytics.space/nerd-os/",
}
ACTIVATION_PACKS = {
    "daily": "GitHub, GitNexus, n8n, Open WebUI, Langfuse, Obsidian, NotebookLM",
    "cms-commerce": "WordPress, WooCommerce, Shopify, SEO, analytics",
    "data": "Polars, vector DB, scraping, data analytics",
    "github-dev": "Git guard, canonical repo policy, GitHub triage, GitNexus, CodeGraph, Spec Kit",
    "knowledge": "Open WebUI knowledge, Obsidian, NotebookLM, prompt library, provenance, reports",
    "design": "OpenUI, open-design, design systems, graph reports, UI generation",
    "security-safe": "Audit/review only; no offensive active tooling in V1",
    "product-growth": "Client offers, digital products, templates, guides, commercialization",
}
MEMORY_LAYERS = {
    "system": "Open WebUI knowledge, NERD inventory, manifest, service directory, and operating policies",
    "projects": "Client/project docs, task history, GitHub/GitNexus notes, and implementation reports",
    "clients": "Client context, preferences, constraints, and reusable delivery patterns",
    "prompts": "Prompt library, reusable skills, activation packs, and workflow templates",
    "traces": "Langfuse traces, Grafana links, n8n executions, and incident notes",
}
GITHUB_POLICY_ITEMS = {
    "canonical-origin": "origin is the user-owned writable canonical remote; branch tracking must point to origin",
    "protected-upstream": "upstream is the read-only original source remote and must not accept pushes",
    "git-guard": "scripts/git-guard.sh checks branch, remotes, dirty tree, ownership, and token patterns before push work",
    "status-panel": "NERD OS exposes branch, dirty count, unpushed commits, canonical repo, and upstream protection",
}


def _item(
    *,
    item_id: str,
    name: str,
    kind: str,
    status: str,
    domain: str,
    risk: str,
    path: Path | None = None,
    source_url: str | None = None,
    notes: str | None = None,
    action: str = "keep",
) -> InventoryItem:
    return InventoryItem(
        id=item_id,
        name=name,
        kind=cast(Kind, kind),
        status=cast(Status, status),
        domain=domain,
        risk=cast(Risk, risk),
        path=str(path) if path else None,
        source_url=source_url,
        evidence=[str(path)] if path else [],
        recommended_action=cast(Action, action),
        notes=notes,
    )


def build_mission_control_report(
    stack_dir: Path = Path("/root/nerd-agency-stack"),
) -> InventoryReport:
    items: list[InventoryItem] = []
    warnings: list[str] = []
    stack_status = "present" if stack_dir.exists() else "missing"
    if stack_status == "missing":
        warnings.append(f"{stack_dir}: NERD Agency stack directory is missing")

    items.append(
        _item(
            item_id="nerd-agency-stack",
            name="NERD Agency Stack",
            kind="dir",
            status=stack_status,
            domain="mission-control",
            risk="medium",
            path=stack_dir,
            notes=f"public_url={PUBLIC_URL}; route_policy=domain_first_raw_backends_private",
        )
    )

    files = {
        "docker-compose": "docker-compose.yml",
        "domains": "nerd-agency.domains.yaml",
        "env-example": ".env.example",
        "manifest": "nerd-agency.manifest.yaml",
        "nginx-http": "nginx/nerd-agency-mission-control.http.conf",
        "nginx-https": "nginx/nerd-agency-mission-control.https.conf",
    }
    for item_id, relative in files.items():
        path = stack_dir / relative
        items.append(
            _item(
                item_id=f"mission-{item_id}",
                name=f"Mission Control {relative}",
                kind="config"
                if relative.endswith((".yml", ".yaml", ".conf", ".example"))
                else "doc",
                status="present" if path.is_file() else "missing",
                domain="mission-control",
                risk="medium" if item_id in {"docker-compose", "manifest"} else "low",
                path=path,
                action="keep" if path.is_file() else "review_later",
            )
        )

    workflow_dir = stack_dir / "n8n" / "v1-workflows"
    workflows = sorted(path.name for path in workflow_dir.glob("*.workflow.json"))
    items.append(
        _item(
            item_id="n8n-v1-workflows",
            name="n8n V1 Workflows",
            kind="config",
            status="present" if workflows else "missing",
            domain="automation",
            risk="medium",
            path=workflow_dir,
            notes=f"count={len(workflows)}; workflows={', '.join(workflows)}",
            action="normalize",
        )
    )

    for pack, description in ACTIVATION_PACKS.items():
        items.append(
            _item(
                item_id=f"activation-pack-{pack}",
                name=f"Activation Pack: {pack}",
                kind="config",
                status="present",
                domain="skills",
                risk="low" if pack != "security-safe" else "medium",
                path=stack_dir / "nerd-agency.manifest.yaml",
                notes=description,
                action="normalize",
            )
        )

    for subdomain, description in PUBLIC_DOMAINS.items():
        host = (
            "agency.umanoff-analytics.space"
            if subdomain == "agency"
            else f"{subdomain}.umanoff-analytics.space"
        )
        items.append(
            _item(
                item_id=f"public-domain-{subdomain}",
                name=f"Public Domain: {host}",
                kind="service",
                status="investigate",
                domain="public-routing",
                risk="medium",
                path=stack_dir / "nerd-agency.manifest.yaml",
                notes=(
                    f"{description}; target=agency.umanoff-analytics.space; "
                    "backend=Open WebUI; expose_raw_backend=false"
                ),
                action="normalize",
            )
        )

    for layer, description in MEMORY_LAYERS.items():
        items.append(
            _item(
                item_id=f"memory-layer-{layer}",
                name=f"Unified Memory: {layer}",
                kind="config",
                status="present",
                domain="unified-memory",
                risk="medium" if layer in {"clients", "traces"} else "low",
                path=stack_dir / "nerd-agency.manifest.yaml",
                notes=description,
                action="normalize",
            )
        )

    for service, public_route in INTERNAL_SERVICES.items():
        risk = "medium" if service in {"open-webui", "free-claude-admin"} else "low"
        items.append(
            _item(
                item_id=f"service-{service}",
                name=f"Internal Service: {service}",
                kind="service",
                status="active" if stack_status == "present" else "investigate",
                domain="service-map",
                risk=risk,
                source_url=public_route,
                notes=f"public_route={public_route}; backend_scope=private",
                action="keep",
            )
        )

    for slug, description in GITHUB_POLICY_ITEMS.items():
        items.append(
            _item(
                item_id=f"github-policy-{slug}",
                name=f"GitHub Policy: {slug.replace('-', ' ').title()}",
                kind="config",
                status="present",
                domain="github-hardening",
                risk="low" if slug != "protected-upstream" else "medium",
                path=Path("/root/nerd-claude-free-staging/scripts/git-guard.sh")
                if slug == "git-guard"
                else stack_dir / "nerd-agency.manifest.yaml",
                notes=description,
                action="keep" if slug == "git-guard" else "normalize",
            )
        )

    return InventoryReport(generated_at=generated_at(), items=items, warnings=warnings)
