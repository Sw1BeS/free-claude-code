from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json

DEFAULT_HERMES_AGENT_ROOT = Path("/root/.hermes/hermes-agent")
DEFAULT_RUNTIME_BUNDLE_ROOT = DEFAULT_HERMES_AGENT_ROOT / "ops" / "hermes-evolution"
DEFAULT_STAGING_ROOT = Path("/root/nerd-claude-free-staging")
DEFAULT_STACK_ROOT = Path("/root/nerd-agency-stack")
SERVICE_FILTER_TERMS = ("hermes", "ollama", "litellm", "nerd-os")
REQUIRED_HERMES_BUNDLE_PATHS = (
    "README.md",
    "compose",
    "runbooks",
    "scripts",
    "systemd",
)


@dataclass(frozen=True)
class ServiceStatus:
    unit: str
    active: str
    sub: str
    raw: str

    @property
    def needs_attention(self) -> bool:
        return self.active in {"failed", "activating"} or self.sub in {
            "failed",
            "auto-restart",
        }


def _parse_service_rows(service_rows: Iterable[str] | None) -> dict[str, ServiceStatus]:
    services: dict[str, ServiceStatus] = {}
    for row in service_rows or ():
        raw = row.strip()
        if not raw:
            continue
        parts = raw.lstrip("●").split()
        if not parts or not parts[0].endswith(".service"):
            continue
        services[parts[0]] = ServiceStatus(
            unit=parts[0],
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


def _item(
    *,
    id: str,
    component: str,
    kind: str,
    status: str,
    risk: str,
    approval_level: str,
    notes: str,
    path: Path | str | None = None,
    evidence: Iterable[str] = (),
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": id,
        "component": component,
        "name": component,
        "kind": kind,
        "classification": "update_candidate",
        "status": status,
        "risk": risk,
        "approval_level": approval_level,
        "evidence": sorted({value for value in evidence if value}),
        "notes": notes,
        "secrets_policy": "env-names-only-no-values",
    }
    if path is not None:
        item["path"] = str(path)
    if metadata is not None:
        item["metadata"] = metadata
    return item


def _service_evidence(
    services: dict[str, ServiceStatus],
    *units: str,
) -> list[str]:
    return [services[unit].raw for unit in units if unit in services]


def _bundle_missing_paths(runtime_bundle_root: Path) -> list[str]:
    return sorted(
        relative
        for relative in REQUIRED_HERMES_BUNDLE_PATHS
        if not (runtime_bundle_root / relative).exists()
    )


def build_update_candidates_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    hermes_agent_root: Path = DEFAULT_HERMES_AGENT_ROOT,
    runtime_bundle_root: Path = DEFAULT_RUNTIME_BUNDLE_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    stack_root: Path = DEFAULT_STACK_ROOT,
    service_rows: Iterable[str] | None = None,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    hermes_agent_root = Path(hermes_agent_root)
    runtime_bundle_root = Path(runtime_bundle_root)
    staging_root = Path(staging_root)
    stack_root = Path(stack_root)
    services = _parse_service_rows(service_rows)

    missing_bundle_paths = _bundle_missing_paths(runtime_bundle_root)
    fragile_services = [
        status.raw
        for unit, status in sorted(services.items())
        if unit.startswith("hermes-") and status.needs_attention
    ]
    hermes_blocked = bool(missing_bundle_paths or fragile_services)

    ollama = services.get("ollama.service")
    ollama_deferred = ollama.needs_attention if ollama else False

    inventory_script = staging_root / "scripts" / "nerd" / "generate_inventory.py"
    items = [
        _item(
            id="update-hermes-agent-runtime",
            component="Hermes Agent Runtime",
            kind="repo",
            status="blocked" if hermes_blocked else "candidate",
            risk="high" if hermes_blocked else "medium",
            approval_level="L3",
            path=hermes_agent_root,
            evidence=[
                str(hermes_agent_root) if hermes_agent_root.exists() else "",
                str(runtime_bundle_root) if runtime_bundle_root.exists() else "",
                *_service_evidence(
                    services,
                    "hermes-gateway.service",
                    "hermes-webhook.service",
                    "hermes-perpetual-autonomy.service",
                ),
            ],
            metadata={
                "runtime_bundle": str(runtime_bundle_root),
                "missing_bundle_paths": missing_bundle_paths,
                "fragile_services": fragile_services,
                "check_commands": [
                    "git status --short",
                    "git fetch --dry-run origin",
                    "hermes status",
                    "hermes doctor",
                ],
                "apply_command": None,
                "rollback_required": True,
            },
            notes=(
                "Direct Hermes update/restart is blocked until missing runtime bundle paths and fragile services are reconciled."
                if hermes_blocked
                else "Hermes runtime can be considered for an audited update, but still requires approval."
            ),
        ),
        _item(
            id="update-ollama-runtime",
            component="Ollama Runtime",
            kind="service",
            status="deferred" if ollama_deferred else "candidate",
            risk="medium" if ollama_deferred else "low",
            approval_level="L2",
            evidence=_service_evidence(services, "ollama.service"),
            metadata={
                "check_commands": ["ollama list", "systemctl status ollama --no-pager"],
                "apply_command": None,
                "expected_restarts": ["ollama.service"],
            },
            notes="Ollama update is represented as a candidate only; registry generation does not pull models or restart services.",
        ),
        _item(
            id="refresh-nerd-inventory",
            component="NERD Inventory Refresh",
            kind="refresh",
            status="safe_check" if inventory_script.is_file() else "missing",
            risk="low",
            approval_level="L1",
            path=inventory_script,
            evidence=[str(inventory_script)] if inventory_script.is_file() else [],
            metadata={
                "check_command": [
                    "uv",
                    "run",
                    "python",
                    "scripts/nerd/generate_inventory.py",
                ],
                "apply_command": None,
            },
            notes="Safe knowledge refresh candidate for generated inventory files.",
        ),
        _item(
            id="refresh-autonomous-registries",
            component="Autonomous Registries Refresh",
            kind="refresh",
            status="safe_check",
            risk="low",
            approval_level="L1",
            path=staging_root,
            evidence=[str(staging_root)] if staging_root.exists() else [],
            metadata={
                "check_commands": [
                    "python -m scripts.nerd.autonomous.bootstrap",
                    "python -m scripts.nerd.autonomous.existing_work",
                    "python -m scripts.nerd.autonomous.runtime_integrations",
                    "python -m scripts.nerd.autonomous.brain_memory",
                    "python -m scripts.nerd.autonomous.hermes_agents",
                    "python -m scripts.nerd.autonomous.hermes_repair_readiness",
                ],
                "apply_command": None,
            },
            notes="Read-only/status-oriented canonical registry refreshes.",
        ),
    ]

    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_update_candidates_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    hermes_agent_root: Path = DEFAULT_HERMES_AGENT_ROOT,
    runtime_bundle_root: Path = DEFAULT_RUNTIME_BUNDLE_ROOT,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    stack_root: Path = DEFAULT_STACK_ROOT,
    service_rows: Iterable[str] | None = None,
) -> Path:
    output = Path(canonical_root) / "registry" / "update-candidates.json"
    resolved_service_rows = (
        discover_service_rows() if service_rows is None else service_rows
    )
    registry = build_update_candidates_registry(
        canonical_root=canonical_root,
        hermes_agent_root=hermes_agent_root,
        runtime_bundle_root=runtime_bundle_root,
        staging_root=staging_root,
        stack_root=stack_root,
        service_rows=resolved_service_rows,
    )
    return write_json(output, registry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write NERD guarded update candidates registry."
    )
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument(
        "--hermes-agent-root", type=Path, default=DEFAULT_HERMES_AGENT_ROOT
    )
    parser.add_argument(
        "--runtime-bundle-root", type=Path, default=DEFAULT_RUNTIME_BUNDLE_ROOT
    )
    parser.add_argument("--staging-root", type=Path, default=DEFAULT_STAGING_ROOT)
    parser.add_argument("--stack-root", type=Path, default=DEFAULT_STACK_ROOT)
    parser.add_argument(
        "--service-row",
        dest="service_rows",
        action="append",
        help="Injected systemd-style service row. Does not query or restart services.",
    )
    args = parser.parse_args(argv)
    output = write_update_candidates_registry(
        canonical_root=args.canonical_root,
        hermes_agent_root=args.hermes_agent_root,
        runtime_bundle_root=args.runtime_bundle_root,
        staging_root=args.staging_root,
        stack_root=args.stack_root,
        service_rows=args.service_rows,
    )
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
