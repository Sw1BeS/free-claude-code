from __future__ import annotations

from pathlib import Path

from scripts.nerd.inventory.models import InventoryItem, InventoryReport
from scripts.nerd.inventory.workspace import generated_at


def build_autonomous_core_report(
    canonical_root: Path = Path("/root/nerd-method"),
) -> InventoryReport:
    system_dir = canonical_root / "system"
    registry_dir = canonical_root / "registry"
    memory_dir = canonical_root / "memory"
    items = [
        InventoryItem(
            id="autonomous-core-canonical-root",
            name="NERD-METHOD Canonical Root",
            kind="dir",
            status="present" if canonical_root.exists() else "missing",
            domain="autonomous-core",
            risk="low",
            classification="installed",
            path=str(canonical_root),
            evidence=[
                str(canonical_root / "AGENTS.md"),
                str(canonical_root / "memory"),
            ],
            recommended_action="keep",
            notes="Product root for Autonomous Core state; staging workspaces must not replace it.",
        ),
        InventoryItem(
            id="autonomous-core-system-policy",
            name="Autonomous Core System Policy",
            kind="config",
            status="present" if system_dir.exists() else "missing",
            domain="autonomous-core",
            risk="medium",
            classification="runtime-candidate",
            path=str(system_dir),
            evidence=[
                str(system_dir / "autonomy-policy.yaml"),
                str(system_dir / "risk-policy.yaml"),
                str(system_dir / "model-routing.yaml"),
                str(system_dir / "memory-contract.yaml"),
            ],
            recommended_action="normalize",
            notes="Policy files define model routing, autonomy levels, risk gates, and memory writeback.",
        ),
        InventoryItem(
            id="autonomous-core-registry",
            name="Autonomous Core Registry",
            kind="config",
            status="present" if registry_dir.exists() else "missing",
            domain="autonomous-core",
            risk="low",
            classification="installed",
            path=str(registry_dir),
            evidence=[
                str(registry_dir / "existing-work.json"),
                str(registry_dir / "departments.json"),
                str(registry_dir / "models.json"),
                str(registry_dir / "workflows.json"),
            ],
            recommended_action="index",
            notes="Canonical registry for existing work, departments, tools, workflows, and model profiles.",
        ),
        InventoryItem(
            id="autonomous-core-runtime-integrations",
            name="Runtime Integrations Registry",
            kind="config",
            status=(
                "present"
                if (registry_dir / "runtime-integrations.json").is_file()
                else "missing"
            ),
            domain="runtimes",
            risk="medium",
            classification="runtime-candidate",
            path=str(registry_dir / "runtime-integrations.json"),
            evidence=[
                str(registry_dir / "runtime-integrations.json"),
                str(system_dir / "model-routing.yaml"),
                "/root/hermes",
                "/root/nerd-method/tools/git-inspired/awesome-openclaw-skills",
            ],
            recommended_action="index",
            notes="Read-only registry for Hermes, OpenClaw sources, local LLMs, LiteLLM, Ollama, and model routers.",
        ),
        InventoryItem(
            id="autonomous-core-memory",
            name="Autonomous Core Memory",
            kind="dir",
            status="present" if memory_dir.exists() else "missing",
            domain="memory",
            risk="medium",
            classification="installed",
            path=str(memory_dir),
            evidence=[
                str(memory_dir / "inbox"),
                str(memory_dir / "tasks"),
                str(memory_dir / "runs"),
                str(memory_dir / "artifacts"),
            ],
            recommended_action="index",
            notes="JSON-first memory queues for inbox, tasks, runs, traces, reports, and artifacts.",
        ),
        InventoryItem(
            id="autonomous-core-n8n-visibility",
            name="n8n Workflow Visibility",
            kind="service",
            status="present",
            domain="automations",
            risk="medium",
            classification="runtime-candidate",
            path="/root/nerd-agency-stack/n8n/v1-workflows",
            source_url="https://automations.umanoff-analytics.space",
            evidence=[
                "/root/nerd-agency-stack/n8n/v1-workflows",
                "/root/nerd-method/registry/workflows.json",
            ],
            recommended_action="normalize",
            notes="Workflows are visible records with gates; Autonomous Core does not run hidden workflow state.",
        ),
        InventoryItem(
            id="autonomous-core-lab",
            name="High-Risk Lab Gate",
            kind="config",
            status="staged",
            domain="lab",
            risk="high",
            classification="high-risk-disabled",
            path=str(canonical_root / "departments" / "lab"),
            evidence=[
                str(canonical_root / "system" / "risk-policy.yaml"),
                str(canonical_root / "departments" / "lab"),
            ],
            recommended_action="review_later",
            notes="Lab requests are recorded and routed to approval; real-world harmful actions remain blocked.",
        ),
    ]
    return InventoryReport(generated_at=generated_at(), items=items)
