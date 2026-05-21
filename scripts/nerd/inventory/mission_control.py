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
    "open-webui": "http://127.0.0.1:38080",
    "n8n": "http://127.0.0.1:5678",
    "langfuse": "http://127.0.0.1:3300",
    "litellm": "http://127.0.0.1:44000",
    "ollama": "http://127.0.0.1:11434",
    "grafana": "http://127.0.0.1:3002",
    "gitnexus": "http://127.0.0.1:4173",
    "free-claude-admin": "http://127.0.0.1:18082/admin",
}
ACTIVATION_PACKS = {
    "daily": "GitHub, GitNexus, n8n, Open WebUI, Langfuse, Obsidian, NotebookLM",
    "cms-commerce": "WordPress, WooCommerce, Shopify, SEO, analytics",
    "data": "Polars, vector DB, scraping, data analytics",
    "security-safe": "Audit/review only; no offensive active tooling in V1",
}
MEMORY_LAYERS = {
    "system": "Open WebUI knowledge, NERD inventory, manifest, service directory, and operating policies",
    "projects": "Client/project docs, task history, GitHub/GitNexus notes, and implementation reports",
    "clients": "Client context, preferences, constraints, and reusable delivery patterns",
    "prompts": "Prompt library, reusable skills, activation packs, and workflow templates",
    "traces": "Langfuse traces, Grafana links, n8n executions, and incident notes",
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
            notes=f"public_url={PUBLIC_URL}; open_webui_loopback=http://127.0.0.1:38080",
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

    for service, url in INTERNAL_SERVICES.items():
        risk = "medium" if service in {"open-webui", "free-claude-admin"} else "low"
        items.append(
            _item(
                item_id=f"service-{service}",
                name=f"Internal Service: {service}",
                kind="service",
                status="active" if stack_status == "present" else "investigate",
                domain="service-map",
                risk=risk,
                notes=f"internal_url={url}",
                action="keep",
            )
        )

    return InventoryReport(generated_at=generated_at(), items=items, warnings=warnings)
