from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from scripts.nerd.autonomous.models import (
    DEFAULT_CANONICAL_ROOT,
    Department,
    ModelProfile,
    WorkflowRecord,
    write_json,
)

CORE_DIRECTORIES = (
    "system",
    "registry",
    "memory/inbox",
    "memory/tasks",
    "memory/brain",
    "memory/brain/candidates",
    "memory/agents",
    "memory/projects",
    "memory/clients",
    "memory/knowledge",
    "memory/prompts",
    "memory/reports",
    "memory/runs",
    "memory/traces",
    "memory/artifacts",
    "memory/approvals",
    "departments/ops",
    "departments/engineering",
    "departments/research",
    "departments/data-studio",
    "departments/cms-commerce",
    "departments/product-growth",
    "departments/memory",
    "departments/lab",
    "automation/n8n-workflows",
    "automation/schedulers",
    "automation/scripts",
    "operations/hermes",
    "operations/updates",
    "operations/ruflo-workspace",
    "operations/openclaw",
    "operations/free-claude",
    "operations/model-routing",
    "tools/git-inspired",
    "tools/node-global",
    "tools/python",
    "artifacts/specs",
    "artifacts/plans",
    "artifacts/audits",
    "artifacts/exports",
    "artifacts/reports",
    "backups/manifests",
    "backups/snapshots",
    "bin",
)


def generated_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_departments() -> list[Department]:
    return [
        Department(
            id="ops",
            name="Ops",
            domain="operations",
            responsibilities=[
                "backups",
                "domains",
                "health",
                "incidents",
                "updates",
            ],
            default_model_profile="ops_fast",
            default_autonomy_level="L2",
        ),
        Department(
            id="engineering",
            name="Engineering",
            domain="development",
            responsibilities=[
                "apps",
                "code",
                "github",
                "gitnexus",
                "sites",
            ],
            default_model_profile="coding_deep",
            default_autonomy_level="L1",
        ),
        Department(
            id="research",
            name="Research",
            domain="research",
            responsibilities=[
                "github-trends",
                "notebooklm",
                "repo-intake",
                "rss",
                "web-research",
            ],
            default_model_profile="research_deep",
            default_autonomy_level="L1",
        ),
        Department(
            id="data-studio",
            name="Data Studio",
            domain="data",
            responsibilities=[
                "archives",
                "classification",
                "datasets",
                "exports",
                "saved-items",
            ],
            default_model_profile="data_extract",
            default_autonomy_level="L1",
        ),
        Department(
            id="cms-commerce",
            name="CMS/Commerce",
            domain="commerce",
            responsibilities=[
                "analytics",
                "migrations",
                "shopify",
                "themes",
                "wordpress",
            ],
            default_model_profile="coding_deep",
            default_autonomy_level="L1",
        ),
        Department(
            id="product-growth",
            name="Product/Growth",
            domain="growth",
            responsibilities=[
                "commercialization",
                "digital-products",
                "github-publishing",
                "moneygen",
                "simpler-alternatives",
            ],
            default_model_profile="research_deep",
            default_autonomy_level="L1",
        ),
        Department(
            id="memory",
            name="Memory",
            domain="knowledge",
            responsibilities=[
                "knowledge",
                "notebooklm",
                "obsidian",
                "prompts",
                "skills",
            ],
            default_model_profile="private_local",
            default_autonomy_level="L1",
        ),
        Department(
            id="lab",
            name="Lab",
            domain="lab",
            responsibilities=[
                "betting-research",
                "dark-ai",
                "high-risk-simulation",
                "security-research",
                "uncensored-local-research",
            ],
            default_model_profile="lab_research",
            default_autonomy_level="L4",
            risk_gate="approval_required",
        ),
    ]


def default_model_profiles() -> list[ModelProfile]:
    return [
        ModelProfile(
            id="coding_deep",
            use="complex implementation, architecture, refactor",
            privacy="project",
            preferred_runtime="litellm",
            fallback_profile="coding_fast",
        ),
        ModelProfile(
            id="coding_fast",
            use="small edits, tests, scripts",
            privacy="project",
            preferred_runtime="9router",
            fallback_profile="ops_fast",
        ),
        ModelProfile(
            id="research_deep",
            use="repository analysis, market research, long documents",
            privacy="mixed",
            preferred_runtime="litellm",
            fallback_profile="data_extract",
        ),
        ModelProfile(
            id="data_extract",
            use="exports, tables, classification, entity extraction",
            privacy="personal_or_client",
            preferred_runtime="local_or_litellm",
            fallback_profile="private_local",
        ),
        ModelProfile(
            id="ops_fast",
            use="status checks, summaries, routing",
            privacy="system",
            preferred_runtime="litellm",
        ),
        ModelProfile(
            id="design_ui",
            use="UI, UX, generated interfaces, product mockups",
            privacy="project",
            preferred_runtime="litellm",
            fallback_profile="coding_deep",
        ),
        ModelProfile(
            id="private_local",
            use="private personal or client data",
            privacy="sensitive",
            preferred_runtime="ollama",
        ),
        ModelProfile(
            id="lab_research",
            use="high-risk research and simulation only",
            privacy="isolated",
            preferred_runtime="local_isolated",
            fallback_profile="private_local",
        ),
    ]


def default_workflows() -> list[WorkflowRecord]:
    return [
        WorkflowRecord(
            id="health_status",
            name="Health Status",
            provider="n8n",
            path="/root/nerd-agency-stack/n8n/v1-workflows/health-status.workflow.json",
            risk="low",
            autonomy_level="L2",
            auto_mode="allowed",
            writes_run_record=False,
            provenance=["/root/nerd-agency-stack/n8n/v1-workflows"],
        ),
        WorkflowRecord(
            id="regenerate_inventory",
            name="Regenerate Inventory",
            provider="n8n",
            path="/root/nerd-agency-stack/n8n/v1-workflows/regenerate-inventory.workflow.json",
            risk="low",
            autonomy_level="L2",
            auto_mode="allowed",
            writes_run_record=False,
            provenance=["/root/nerd-agency-stack/n8n/v1-workflows"],
        ),
        WorkflowRecord(
            id="github_repo_triage",
            name="GitHub Repo Triage",
            provider="n8n",
            path="/root/nerd-agency-stack/n8n/v1-workflows/github-repo-triage.workflow.json",
            risk="medium",
            autonomy_level="L3",
            auto_mode="approval_required",
            writes_run_record=False,
            provenance=["/root/nerd-agency-stack/n8n/v1-workflows"],
        ),
        WorkflowRecord(
            id="cms_commerce_planning",
            name="CMS Commerce Planning",
            provider="n8n",
            path="/root/nerd-agency-stack/n8n/v1-workflows/cms-commerce-planning.workflow.json",
            risk="medium",
            autonomy_level="L3",
            auto_mode="approval_required",
            writes_run_record=False,
            provenance=["/root/nerd-agency-stack/n8n/v1-workflows"],
        ),
        WorkflowRecord(
            id="langfuse_trace_lookup",
            name="Langfuse Trace Lookup",
            provider="n8n",
            path="/root/nerd-agency-stack/n8n/v1-workflows/langfuse-trace-lookup.workflow.json",
            risk="low",
            autonomy_level="L2",
            auto_mode="allowed",
            writes_run_record=False,
            provenance=["/root/nerd-agency-stack/n8n/v1-workflows"],
        ),
    ]


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _record_bundle(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"generated_at": generated_at(), "items": items}


def bootstrap_autonomous_core(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    for relative in CORE_DIRECTORIES:
        (canonical_root / relative).mkdir(parents=True, exist_ok=True)

    generated_files: list[str] = []
    generated_files.append(
        str(
            _write_yaml(
                canonical_root / "system" / "autonomy-policy.yaml",
                {
                    "levels": {
                        "L0": {"approval": "not_required", "meaning": "read-only"},
                        "L1": {
                            "approval": "not_required",
                            "meaning": "drafts, reports, tasks, memory candidates",
                        },
                        "L2": {
                            "approval": "not_required_if_allowlisted",
                            "meaning": "allowlisted low-risk workflows",
                        },
                        "L3": {
                            "approval": "required",
                            "meaning": "medium-risk workflow or write action",
                        },
                        "L4": {
                            "approval": "required_and_isolated",
                            "meaning": "high-risk lab simulation",
                        },
                        "L5": {
                            "approval": "blocked",
                            "meaning": "unsafe real-world action",
                        },
                    }
                },
            )
        )
    )
    generated_files.append(
        str(
            _write_yaml(
                canonical_root / "system" / "risk-policy.yaml",
                {
                    "default": "medium",
                    "high_risk_requires": ["approval", "isolation", "provenance"],
                    "blocked_real_world_actions": [
                        "credential_theft",
                        "destructive_access",
                        "financial_execution",
                        "offensive_operations",
                        "social_farming",
                        "stealth_automation",
                    ],
                },
            )
        )
    )
    generated_files.append(
        str(
            _write_yaml(
                canonical_root / "system" / "model-routing.yaml",
                {
                    "policy": {
                        "external_metered_spend": "approval_required",
                        "private_data_default": "private_local",
                        "high_risk_default": "lab_research",
                        "trace_required": True,
                    },
                    "runtimes": {
                        "litellm-local": {
                            "kind": "model_gateway",
                            "base_url": "http://127.0.0.1:44000/v1",
                            "public": False,
                            "status_source": "hermes_config",
                        },
                        "ollama": {
                            "kind": "local_llm_runtime",
                            "status_command": ["ollama", "list"],
                            "public": False,
                        },
                        "9router": {
                            "kind": "coding_agent_router",
                            "path": "/root/nerd-method/tools/git-inspired/9router",
                            "public": False,
                        },
                        "hermes": {
                            "kind": "operator_shell",
                            "status_command": ["/root/.local/bin/hermes", "status"],
                            "public": False,
                        },
                    },
                    "profiles": {
                        profile.id: {
                            "use": profile.use,
                            "privacy": profile.privacy,
                            "preferred_runtime": profile.preferred_runtime,
                            "fallback_profile": profile.fallback_profile,
                        }
                        for profile in default_model_profiles()
                    },
                    "profile_bindings": {
                        "coding_deep": {"runtime": "litellm-local", "model": "dev-coder"},
                        "coding_fast": {"runtime": "9router", "model": "dev-coder-fast"},
                        "research_deep": {"runtime": "litellm-local", "model": "research-deep"},
                        "data_extract": {"runtime": "litellm-local", "model": "local-utility"},
                        "ops_fast": {"runtime": "litellm-local", "model": "ops-fast"},
                        "design_ui": {"runtime": "litellm-local", "model": "browser-ui"},
                        "private_local": {"runtime": "ollama", "model": "local-private"},
                        "lab_research": {"runtime": "ollama", "model": "redteam-sandbox"},
                    },
                    "hermes_aliases": {
                        "dev-coder": "coding_deep",
                        "dev-coder-fast": "coding_fast",
                        "research-deep": "research_deep",
                        "ops-fast": "ops_fast",
                        "browser-ui": "design_ui",
                        "local-utility": "data_extract",
                        "redteam-sandbox": "lab_research",
                    },
                },
            )
        )
    )
    generated_files.append(
        str(
            _write_yaml(
                canonical_root / "system" / "memory-contract.yaml",
                {
                    "records": [
                        "InboxItem",
                        "Task",
                        "RunRecord",
                        "MemoryArtifact",
                        "ApprovalRecord",
                        "BrainMemoryRecord",
                        "HermesAgentRecord",
                        "UpdateCandidateRecord",
                    ],
                    "writeback": {
                        "raw_input": "memory/inbox",
                        "tasks": "memory/tasks",
                        "brain": "memory/brain",
                        "agents": "memory/agents",
                        "runs": "memory/runs",
                        "artifacts": "memory/artifacts",
                        "approvals": "memory/approvals",
                    },
                    "provenance_required": True,
                },
            )
        )
    )
    generated_files.append(
        str(
            _write_yaml(
                canonical_root / "system" / "domain-routes.yaml",
                {
                    "base": "https://agency.umanoff-analytics.space/nerd-os/",
                    "routes": [
                        "/nerd-os/",
                        "/nerd-os/inbox",
                        "/nerd-os/tasks",
                        "/nerd-os/brain",
                        "/nerd-os/hermes",
                        "/nerd-os/updates",
                        "/nerd-os/runs",
                        "/nerd-os/registry",
                    ],
                },
            )
        )
    )
    generated_files.append(
        str(
            _write_yaml(
                canonical_root / "system" / "autonomous-core.yaml",
                {
                    "canonical_root": str(canonical_root),
                    "state": "active_foundation",
                    "adapter_workspace": "/root/nerd-claude-free-staging",
                    "runtime_stack": "/root/nerd-agency-stack",
                },
            )
        )
    )

    generated_files.append(
        str(
            write_json(
                canonical_root / "registry" / "departments.json",
                _record_bundle([item.to_dict() for item in default_departments()]),
            )
        )
    )
    generated_files.append(
        str(
            write_json(
                canonical_root / "registry" / "models.json",
                _record_bundle([item.to_dict() for item in default_model_profiles()]),
            )
        )
    )
    generated_files.append(
        str(
            write_json(
                canonical_root / "registry" / "workflows.json",
                _record_bundle([item.to_dict() for item in default_workflows()]),
            )
        )
    )
    generated_files.append(
        str(
            write_json(
                canonical_root / "registry" / "services.json",
                _record_bundle(
                    [
                        {
                            "id": "nerd-os",
                            "name": "NERD OS",
                            "url": "https://agency.umanoff-analytics.space/nerd-os/",
                            "kind": "domain-ui",
                            "status": "active",
                        },
                        {
                            "id": "n8n",
                            "name": "n8n Automations",
                            "url": "https://automations.umanoff-analytics.space",
                            "kind": "workflow-layer",
                            "status": "active",
                        },
                        {
                            "id": "memory",
                            "name": "Shared Memory",
                            "url": "https://memory.umanoff-analytics.space",
                            "kind": "knowledge-layer",
                            "status": "active",
                        },
                    ]
                ),
            )
        )
    )
    generated_files.append(
        str(
            write_json(
                canonical_root / "registry" / "tools.json",
                _record_bundle(
                    [
                        {
                            "id": "free-claude",
                            "name": "Free Claude Adapter",
                            "path": "/root/nerd-claude-free-staging",
                            "classification": "active_runtime",
                        },
                        {
                            "id": "gitnexus",
                            "name": "GitNexus",
                            "path": "/root/nerd-method/.gitnexus",
                            "classification": "installed",
                        },
                        {
                            "id": "codegraph",
                            "name": "CodeGraph",
                            "path": "/root/nerd-claude-free-staging/.codegraph",
                            "classification": "installed",
                        },
                    ]
                ),
            )
        )
    )
    generated_files.append(
        str(
            write_json(
                canonical_root / "registry" / "mcp-servers.json",
                _record_bundle(
                    [
                        {
                            "id": "ruflo-workspace",
                            "name": "Ruflo Workspace MCP",
                            "path": "/root/nerd-method/operations/ruflo-workspace/.mcp.json",
                            "classification": "candidate_runtime",
                        }
                    ]
                ),
            )
        )
    )
    generated_files.append(
        str(
            write_json(
                canonical_root / "registry" / "agents.json",
                _record_bundle(
                    [
                        {
                            "id": "repo_researcher",
                            "department": "research",
                            "model_profile": "research_deep",
                            "autonomy_level": "L1",
                        },
                        {
                            "id": "engineering_operator",
                            "department": "engineering",
                            "model_profile": "coding_deep",
                            "autonomy_level": "L1",
                        },
                        {
                            "id": "lab_researcher",
                            "department": "lab",
                            "model_profile": "lab_research",
                            "autonomy_level": "L4",
                        },
                    ]
                ),
            )
        )
    )

    return {
        "canonical_root": str(canonical_root),
        "generated_files": sorted(generated_files),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap NERD Autonomous Core.")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    args = parser.parse_args(argv)

    result = bootstrap_autonomous_core(args.canonical_root)
    sys.stdout.write(str(result["canonical_root"]) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
