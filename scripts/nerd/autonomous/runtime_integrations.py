from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json

DEFAULT_HERMES_ROOT = Path("/root/hermes")
DEFAULT_GITINSPIRED_ROOT = Path("/root/nerd-method/tools/git-inspired")
LITELLM_LOCAL_BASE_URL = "http://127.0.0.1:44000/v1"
SERVICE_FILTER_TERMS = (
    "hermes",
    "ollama",
    "litellm",
    "router",
    "openclaw",
    "n8n",
    "telegram",
    "langfuse",
    "openwebui",
    "open-webui",
)
REMOVED_SERVICE_TERMS = ("paper" + "clip",)


@dataclass(frozen=True)
class ServiceStatus:
    unit: str
    name: str
    load: str
    active: str
    sub: str
    raw: str

    @property
    def registry_status(self) -> str:
        if self.active in {"failed", "activating"} or self.sub in {
            "failed",
            "auto-restart",
        }:
            return "needs_attention"
        if self.active == "active":
            return "active"
        if self.active == "inactive" or self.sub == "dead":
            return "inactive"
        return "unknown"


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", cleaned)


def _item(
    *,
    id: str,
    name: str,
    kind: str,
    classification: str,
    status: str,
    risk: str,
    notes: str,
    path: Path | str | None = None,
    source_url: str | None = None,
    evidence: Iterable[str] = (),
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": id,
        "name": name,
        "kind": kind,
        "classification": classification,
        "status": status,
        "risk": risk,
        "evidence": sorted({item for item in evidence if item}),
        "notes": notes,
    }
    if path is not None:
        item["path"] = str(path)
    if source_url is not None:
        item["source_url"] = source_url
    if metadata is not None:
        item["metadata"] = metadata
    return item


def _parse_service_rows(service_rows: Iterable[str] | None) -> dict[str, ServiceStatus]:
    services: dict[str, ServiceStatus] = {}
    for row in service_rows or ():
        raw = row.strip()
        if not raw:
            continue
        parts = raw.lstrip("●").split()
        if not parts or not parts[0].endswith(".service"):
            continue
        unit = parts[0]
        name = unit.removesuffix(".service")
        services[name] = ServiceStatus(
            unit=unit,
            name=name,
            load=parts[1] if len(parts) > 1 else "unknown",
            active=parts[2] if len(parts) > 2 else "unknown",
            sub=parts[3] if len(parts) > 3 else "unknown",
            raw=raw,
        )
    return services


def discover_service_rows() -> list[str]:
    completed = subprocess.run(
        ["systemctl", "list-units", "--type=service", "--all", "--no-pager"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    rows = []
    for line in completed.stdout.splitlines():
        lowered = line.lower()
        if any(term in lowered for term in SERVICE_FILTER_TERMS):
            rows.append(line.strip())
    return rows


def _hermes_item(hermes_root: Path) -> dict[str, object]:
    status_file = hermes_root / "core" / "status.json"
    config_file = hermes_root / "infra" / "configs" / "config.yaml"
    evidence = [str(hermes_root)]
    evidence.extend(str(path) for path in (status_file, config_file) if path.is_file())
    exists = hermes_root.exists()
    return _item(
        id="runtime-hermes",
        name="Hermes",
        kind="runtime",
        classification="active_runtime" if exists else "runtime_candidate",
        status="active" if exists else "missing",
        risk="medium",
        path=hermes_root,
        evidence=evidence,
        notes=(
            "Hermes root is present; registry entry is read-only status evidence."
            if exists
            else "Hermes root was expected but not found during registry build."
        ),
    )


def _hermes_service_items(
    services: dict[str, ServiceStatus],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for service in services.values():
        if not service.name.startswith("hermes"):
            continue
        if any(term in service.name.lower() for term in REMOVED_SERVICE_TERMS):
            continue
        status = service.registry_status
        items.append(
            _item(
                id=f"service-{slugify(service.name)}",
                name=service.name.replace("-", " ").title(),
                kind="service",
                classification="runtime_service",
                status=status,
                risk="medium" if status == "needs_attention" else "low",
                evidence=[service.raw],
                notes="Hermes-related systemd service observed from injected service rows.",
            )
        )
    return items


def _service_status(
    services: dict[str, ServiceStatus],
    *names: str,
    default: str = "configured",
) -> str:
    for name in names:
        service = services.get(name)
        if service:
            return service.registry_status
    return default


def _platform_integration_items(
    services: dict[str, ServiceStatus],
) -> list[dict[str, object]]:
    langfuse_status = _service_status(services, "langfuse", default="configured")
    n8n_status = _service_status(services, "n8n", default="configured")
    openwebui_status = _service_status(
        services,
        "openwebui",
        "open-webui",
        default="optional",
    )
    return [
        _item(
            id="integration-n8n",
            name="n8n",
            kind="workflow_runtime",
            classification="workflow_orchestrator",
            status=n8n_status,
            risk="medium",
            evidence=[services["n8n"].raw] if "n8n" in services else [],
            metadata={
                "core_shell": False,
                "dry_run_actions": [
                    "autonomous_brain_intake_n8n_dry_run",
                ],
            },
            notes="n8n is connected through NERD OS dry-run intake and guarded workflow actions.",
        ),
        _item(
            id="integration-telegram",
            name="Telegram Intake",
            kind="message_intake",
            classification="intake_adapter",
            status="configured",
            risk="medium",
            metadata={
                "core_shell": False,
                "dry_run_actions": [
                    "autonomous_brain_intake_telegram_dry_run",
                ],
            },
            notes="Telegram messages feed NERD OS inbox/task/memory candidate flow through dry-run first.",
        ),
        _item(
            id="integration-langfuse",
            name="Langfuse",
            kind="observability",
            classification="trace_observability",
            status=langfuse_status,
            risk="low",
            evidence=[services["langfuse"].raw] if "langfuse" in services else [],
            metadata={"core_shell": False},
            notes="Trace and observability surface for model and agent operations.",
        ),
        _item(
            id="integration-openwebui",
            name="Open WebUI",
            kind="legacy_chat_surface",
            classification="optional_integration",
            status=openwebui_status,
            risk="medium",
            evidence=[
                service.raw
                for key, service in services.items()
                if key in {"openwebui", "open-webui"}
            ],
            metadata={
                "role": "optional_chat_surface",
                "core_shell": False,
                "approval_gated": True,
            },
            notes=(
                "Open WebUI is retained as an optional legacy chat/model surface; "
                "it is not the primary NERD OS interface."
            ),
        ),
        _item(
            id="integration-openhands",
            name="OpenHands",
            kind="agent_tooling",
            classification="optional_integration",
            status="not_configured",
            risk="medium",
            metadata={"core_shell": False},
            notes="Optional coding-agent surface reserved for future NERD OS integration.",
        ),
        _item(
            id="integration-dify",
            name="Dify",
            kind="ai_workflow_tooling",
            classification="optional_integration",
            status="not_configured",
            risk="medium",
            metadata={"core_shell": False},
            notes="Optional AI workflow surface reserved for future NERD OS integration.",
        ),
    ]


def _gitinspired_items(gitinspired_root: Path) -> list[dict[str, object]]:
    if not gitinspired_root.is_dir():
        return []

    items: list[dict[str, object]] = []
    openclaw_root = gitinspired_root / "awesome-openclaw-skills"
    if openclaw_root.is_dir():
        items.append(
            _item(
                id="source-openclaw-skills",
                name="Awesome OpenClaw Skills",
                kind="skillpack",
                classification="source_cache",
                status="present",
                risk="low",
                path=openclaw_root,
                evidence=[str(openclaw_root)],
                notes="OpenClaw skill source cache.",
            )
        )

    ecc_root = gitinspired_root / "ecc"
    if ecc_root.is_dir():
        items.append(
            _item(
                id="migration-ecc-docs",
                name="ECC Hermes/OpenClaw Docs",
                kind="skillpack",
                classification="migration_source",
                status="present",
                risk="low",
                path=ecc_root,
                evidence=[str(ecc_root)],
                notes="ECC documentation source for Hermes/OpenClaw migration planning.",
            )
        )

    router_root = gitinspired_root / "9router"
    if router_root.is_dir():
        items.append(
            _item(
                id="runtime-9router",
                name="9router",
                kind="model_router",
                classification="model_router",
                status="present",
                risk="medium",
                path=router_root,
                evidence=[str(router_root)],
                notes="Model-router candidate source; registry does not start or restart it.",
            )
        )

    graphify_root = gitinspired_root / "graphify"
    if graphify_root.is_dir():
        items.append(
            _item(
                id="source-graphify",
                name="Graphify",
                kind="model_tooling",
                classification="model_source",
                status="present",
                risk="low",
                path=graphify_root,
                evidence=[str(graphify_root)],
                notes="Model/graph tooling source cache for later evaluation.",
            )
        )

    return items


def _local_model_items(
    canonical_root: Path,
    services: dict[str, ServiceStatus],
) -> list[dict[str, object]]:
    routing_file = canonical_root / "system" / "model-routing.yaml"
    litellm = services.get("litellm-local")
    ollama = services.get("ollama")
    return [
        _item(
            id="gateway-litellm-local",
            name="LiteLLM Local Gateway",
            kind="model_gateway",
            classification="model_gateway",
            status=litellm.registry_status if litellm else "configured",
            risk="medium",
            evidence=[litellm.raw if litellm else "", str(routing_file)],
            metadata={"base_url": LITELLM_LOCAL_BASE_URL},
            notes="Local OpenAI-compatible gateway binding. Base URL is internal metadata, not a public link.",
        ),
        _item(
            id="runtime-ollama",
            name="Ollama",
            kind="local_llm_runtime",
            classification="local_llm_runtime",
            status=ollama.registry_status if ollama else "configured",
            risk="low",
            evidence=[ollama.raw if ollama else "", str(routing_file)],
            notes="Local LLM runtime binding; status comes from injected service rows when provided.",
        ),
    ]


def build_runtime_integration_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    hermes_root: Path = DEFAULT_HERMES_ROOT,
    gitinspired_root: Path = DEFAULT_GITINSPIRED_ROOT,
    service_rows: Iterable[str] | None = None,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    hermes_root = Path(hermes_root)
    gitinspired_root = Path(gitinspired_root)
    services = _parse_service_rows(service_rows)

    items: list[dict[str, object]] = [
        _hermes_item(hermes_root),
        *_hermes_service_items(services),
        *_platform_integration_items(services),
        *_gitinspired_items(gitinspired_root),
        *_local_model_items(canonical_root, services),
    ]

    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_runtime_integration_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    hermes_root: Path = DEFAULT_HERMES_ROOT,
    gitinspired_root: Path = DEFAULT_GITINSPIRED_ROOT,
    service_rows: Iterable[str] | None = None,
) -> Path:
    output = Path(canonical_root) / "registry" / "runtime-integrations.json"
    resolved_service_rows = (
        discover_service_rows() if service_rows is None else service_rows
    )
    registry = build_runtime_integration_registry(
        canonical_root=canonical_root,
        hermes_root=hermes_root,
        gitinspired_root=gitinspired_root,
        service_rows=resolved_service_rows,
    )
    return write_json(output, registry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write NERD runtime integrations registry."
    )
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--hermes-root", type=Path, default=DEFAULT_HERMES_ROOT)
    parser.add_argument(
        "--gitinspired-root", type=Path, default=DEFAULT_GITINSPIRED_ROOT
    )
    parser.add_argument(
        "--service-row",
        dest="service_rows",
        action="append",
        help="Injected systemd-style service row. Does not query or restart services.",
    )
    args = parser.parse_args(argv)

    output = write_runtime_integration_registry(
        canonical_root=args.canonical_root,
        hermes_root=args.hermes_root,
        gitinspired_root=args.gitinspired_root,
        service_rows=args.service_rows,
    )
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
