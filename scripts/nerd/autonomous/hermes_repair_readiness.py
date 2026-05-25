from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json

DEFAULT_HERMES_AGENT_ROOT = Path("/root/.hermes/hermes-agent")
DEFAULT_RUNTIME_BUNDLE_ROOT = DEFAULT_HERMES_AGENT_ROOT / "ops" / "hermes-evolution"
DEFAULT_ARCHIVE_BUNDLE_ROOT = Path(
    "/root/hermes/archive/legacy_root/hermes-evolution-rollback-repo"
)
DEFAULT_SOURCE_BUNDLE_ROOT = (
    Path("/root/.config/superpowers/worktrees/hermes/autonomy-proof-20260429")
    / "ops"
    / "hermes-evolution"
)
SERVICE_FILTER_TERMS = ("hermes",)
REQUIRED_RUNTIME_PATHS = (
    "README.md",
    "compose",
    "runbooks",
    "scripts/bootstrap_layout.sh",
    "scripts/validate_bundle.py",
    "systemd",
)
REQUIRED_RUNTIME_SCRIPTS = (
    "scripts/hermes_webhook_bridge.py",
    "scripts/moneygen_bounded.py",
    "scripts/nerdm_knowledge_sync_report.py",
    "scripts/postgres_readonly_mcp.py",
)
REQUIRED_AGENT_SCRIPTS = ("scripts/hermes-perpetual-conductor.py",)


def _item(
    *,
    id: str,
    name: str,
    kind: str,
    classification: str,
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
        "name": name,
        "kind": kind,
        "classification": classification,
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


def _parse_service_rows(service_rows: Iterable[str] | None) -> list[str]:
    return sorted({row.strip() for row in service_rows or () if row.strip()})


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


def discover_systemd_link_rows() -> list[str]:
    rows: list[str] = []
    for root in (Path("/etc/systemd/system"), Path("/lib/systemd/system")):
        if not root.is_dir():
            continue
        for path in sorted(root.glob("hermes-*")):
            target = path.resolve(strict=False) if path.is_symlink() else Path("")
            rows.append(f"{path} -> {target if target else ''}")
    return rows


def discover_docker_rows() -> list[str]:
    completed = subprocess.run(
        [
            "docker",
            "ps",
            "--format",
            "{{.Names}} {{.Image}} {{.Status}}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [
        line.strip()
        for line in completed.stdout.splitlines()
        if "hermes-evolution" in line.lower()
    ]


def _missing_relative_paths(root: Path, relative_paths: Iterable[str]) -> list[str]:
    return sorted(
        relative for relative in relative_paths if not (root / relative).exists()
    )


def _bundle_files(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    )


def _available_bundle_scripts(
    bundle_root: Path,
    required_scripts: Iterable[str],
) -> list[str]:
    return sorted(
        relative for relative in required_scripts if (bundle_root / relative).is_file()
    )


def _bad_systemd_links(systemd_link_rows: Iterable[str] | None) -> list[dict[str, str]]:
    bad_links: list[dict[str, str]] = []
    for row in systemd_link_rows or ():
        if "->" not in row:
            continue
        source, target = [part.strip() for part in row.split("->", 1)]
        if not target:
            continue
        if "hermes-evolution" not in target:
            continue
        if not Path(target).exists():
            bad_links.append({"source": source, "target": target})
    return sorted(bad_links, key=lambda item: (item["source"], item["target"]))


def _fragile_services(service_rows: Iterable[str] | None) -> list[str]:
    rows = _parse_service_rows(service_rows)
    fragile = []
    for row in rows:
        normalized = row.lstrip("●").strip()
        parts = normalized.split()
        if len(parts) < 4:
            continue
        active = parts[2]
        sub = parts[3]
        if active in {"failed", "activating"} or sub in {"failed", "auto-restart"}:
            fragile.append(normalized)
    return sorted(fragile)


def _restore_plan(
    runtime_bundle_root: Path,
    restore_bundle_root: Path,
) -> dict[str, object]:
    include_args = (
        "--include='/README.md' "
        "--include='/SYSTEM_MAP.md' "
        "--include='/caddy/***' "
        "--include='/compose/***' "
        "--include='/config/***' "
        "--include='/docs/***' "
        "--include='/env/' "
        "--include='/env/*.example' "
        "--include='/litellm/***' "
        "--include='/postgres/***' "
        "--include='/runbooks/***' "
        "--include='/scripts/***' "
        "--include='/systemd/***' "
        "--exclude='*'"
    )
    return {
        "dry_run_command": (
            "rsync --dry-run --itemize-changes -a "
            f"{include_args} "
            f"{restore_bundle_root}/ "
            f"{runtime_bundle_root}/"
        ),
        "apply_command": (
            f"rsync -a {include_args} {restore_bundle_root}/ {runtime_bundle_root}/"
        ),
        "apply_requires_approval": True,
        "restart_allowed": False,
    }


def build_hermes_repair_readiness_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    hermes_agent_root: Path = DEFAULT_HERMES_AGENT_ROOT,
    runtime_bundle_root: Path = DEFAULT_RUNTIME_BUNDLE_ROOT,
    archive_bundle_root: Path = DEFAULT_ARCHIVE_BUNDLE_ROOT,
    source_bundle_root: Path | None = None,
    service_rows: Iterable[str] | None = None,
    systemd_link_rows: Iterable[str] | None = None,
    docker_rows: Iterable[str] | None = None,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    hermes_agent_root = Path(hermes_agent_root)
    runtime_bundle_root = Path(runtime_bundle_root)
    archive_bundle_root = Path(archive_bundle_root)
    source_bundle_root = (
        Path(source_bundle_root)
        if source_bundle_root is not None
        else archive_bundle_root
    )
    restore_bundle_root = (
        source_bundle_root if source_bundle_root.is_dir() else archive_bundle_root
    )

    archive_files = _bundle_files(archive_bundle_root)
    source_files = _bundle_files(source_bundle_root)
    missing_runtime_paths = _missing_relative_paths(
        runtime_bundle_root,
        REQUIRED_RUNTIME_PATHS,
    )
    missing_runtime_scripts = _missing_relative_paths(
        runtime_bundle_root,
        REQUIRED_RUNTIME_SCRIPTS,
    )
    missing_agent_scripts = _missing_relative_paths(
        hermes_agent_root,
        REQUIRED_AGENT_SCRIPTS,
    )
    bad_unit_links = _bad_systemd_links(systemd_link_rows)
    fragile_services = _fragile_services(service_rows)
    observed_containers = sorted(
        {row.strip() for row in docker_rows or () if row.strip()}
    )

    layout_blocked = bool(missing_runtime_paths)
    script_blocked = bool(missing_runtime_scripts or missing_agent_scripts)
    systemd_blocked = bool(bad_unit_links or fragile_services)
    items = [
        _item(
            id="hermes-detached-checkout-restore-source",
            name="Hermes Detached Checkout Restore Source",
            kind="restore_source",
            classification="hermes_repair_readiness",
            status="present" if source_bundle_root.is_dir() else "missing",
            risk="medium" if source_bundle_root.is_dir() else "high",
            approval_level="L1",
            path=source_bundle_root,
            evidence=[str(source_bundle_root)] if source_bundle_root.exists() else [],
            metadata={
                "source_file_count": len(source_files),
                "required_runtime_paths_available": [
                    relative
                    for relative in REQUIRED_RUNTIME_PATHS
                    if (source_bundle_root / relative).exists()
                ],
            },
            notes="Detached Hermes checkout source for runtime bundle/source consistency repair planning.",
        ),
        _item(
            id="hermes-archive-restore-source",
            name="Hermes Archive Restore Source",
            kind="restore_source",
            classification="hermes_repair_readiness",
            status="present" if archive_bundle_root.is_dir() else "missing",
            risk="medium" if archive_bundle_root.is_dir() else "high",
            approval_level="L1",
            path=archive_bundle_root,
            evidence=[str(archive_bundle_root)] if archive_bundle_root.exists() else [],
            metadata={
                "source_file_count": len(archive_files),
                "required_runtime_paths_available": [
                    relative
                    for relative in REQUIRED_RUNTIME_PATHS
                    if (archive_bundle_root / relative).exists()
                ],
            },
            notes="Local archive source for guarded dry-run restore planning. Registry generation does not copy files.",
        ),
        _item(
            id="hermes-runtime-bundle-layout",
            name="Hermes Runtime Bundle Layout",
            kind="runtime_bundle",
            classification="hermes_repair_readiness",
            status="blocked" if layout_blocked else "ready",
            risk="high" if layout_blocked else "medium",
            approval_level="L3",
            path=runtime_bundle_root,
            evidence=[
                str(runtime_bundle_root) if runtime_bundle_root.exists() else "",
                str(archive_bundle_root) if archive_bundle_root.exists() else "",
                str(source_bundle_root) if source_bundle_root.exists() else "",
            ],
            metadata={
                "missing_runtime_paths": missing_runtime_paths,
                "selected_restore_source": str(restore_bundle_root),
                "restart_allowed": False,
                "dry_run_commands": [
                    "python -m scripts.nerd.autonomous.hermes_repair_readiness --check"
                ],
                "restore_plan": _restore_plan(runtime_bundle_root, restore_bundle_root),
            },
            notes="Runtime bundle restore is blocked until the operator approves a dry-run reviewed copy plan.",
        ),
        _item(
            id="hermes-runtime-script-sources",
            name="Hermes Runtime Script Sources",
            kind="script_sources",
            classification="hermes_repair_readiness",
            status="blocked" if script_blocked else "ready",
            risk="high" if script_blocked else "medium",
            approval_level="L3",
            path=runtime_bundle_root / "scripts",
            evidence=[str(runtime_bundle_root / "scripts")]
            if (runtime_bundle_root / "scripts").exists()
            else [],
            metadata={
                "missing_script_paths": missing_runtime_scripts,
                "missing_agent_script_paths": missing_agent_scripts,
                "available_archive_scripts": _available_bundle_scripts(
                    archive_bundle_root,
                    REQUIRED_RUNTIME_SCRIPTS,
                ),
                "available_source_scripts": _available_bundle_scripts(
                    source_bundle_root,
                    REQUIRED_RUNTIME_SCRIPTS,
                ),
                "restart_allowed": False,
            },
            notes="Systemd-referenced Hermes scripts must exist before any service restart is considered.",
        ),
        _item(
            id="hermes-systemd-consistency",
            name="Hermes Systemd Consistency",
            kind="systemd_units",
            classification="hermes_repair_readiness",
            status="blocked" if systemd_blocked else "ready",
            risk="high" if systemd_blocked else "medium",
            approval_level="L3",
            evidence=[bad_unit_link["source"] for bad_unit_link in bad_unit_links]
            + fragile_services,
            metadata={
                "bad_unit_links": bad_unit_links,
                "fragile_services": fragile_services,
                "restart_allowed": False,
            },
            notes="Hermes systemd units are readiness evidence only. Registry generation does not reload or restart systemd.",
        ),
        _item(
            id="hermes-runtime-containers",
            name="Hermes Runtime Containers",
            kind="containers",
            classification="hermes_repair_readiness",
            status="observed" if observed_containers else "not_observed",
            risk="medium" if observed_containers else "unknown",
            approval_level="L1",
            evidence=observed_containers,
            metadata={"container_count": len(observed_containers)},
            notes="Read-only docker ps evidence for existing Hermes runtime containers.",
        ),
    ]

    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_hermes_repair_readiness_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    hermes_agent_root: Path = DEFAULT_HERMES_AGENT_ROOT,
    runtime_bundle_root: Path = DEFAULT_RUNTIME_BUNDLE_ROOT,
    archive_bundle_root: Path = DEFAULT_ARCHIVE_BUNDLE_ROOT,
    source_bundle_root: Path | None = DEFAULT_SOURCE_BUNDLE_ROOT,
    service_rows: Iterable[str] | None = None,
    systemd_link_rows: Iterable[str] | None = None,
    docker_rows: Iterable[str] | None = None,
) -> Path:
    output = Path(canonical_root) / "registry" / "hermes-repair-readiness.json"
    registry = build_hermes_repair_readiness_registry(
        canonical_root=canonical_root,
        hermes_agent_root=hermes_agent_root,
        runtime_bundle_root=runtime_bundle_root,
        archive_bundle_root=archive_bundle_root,
        source_bundle_root=source_bundle_root,
        service_rows=discover_service_rows() if service_rows is None else service_rows,
        systemd_link_rows=(
            discover_systemd_link_rows()
            if systemd_link_rows is None
            else systemd_link_rows
        ),
        docker_rows=discover_docker_rows() if docker_rows is None else docker_rows,
    )
    return write_json(output, registry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write or check NERD Hermes repair readiness registry."
    )
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument(
        "--hermes-agent-root", type=Path, default=DEFAULT_HERMES_AGENT_ROOT
    )
    parser.add_argument(
        "--runtime-bundle-root", type=Path, default=DEFAULT_RUNTIME_BUNDLE_ROOT
    )
    parser.add_argument(
        "--archive-bundle-root", type=Path, default=DEFAULT_ARCHIVE_BUNDLE_ROOT
    )
    parser.add_argument(
        "--source-bundle-root", type=Path, default=DEFAULT_SOURCE_BUNDLE_ROOT
    )
    parser.add_argument(
        "--check", action="store_true", help="Print registry JSON without writing."
    )
    parser.add_argument(
        "--service-row",
        dest="service_rows",
        action="append",
        help="Injected systemd-style service row. Does not query or restart services.",
    )
    parser.add_argument(
        "--systemd-link-row",
        dest="systemd_link_rows",
        action="append",
        help="Injected systemd link row in 'source -> target' form.",
    )
    parser.add_argument(
        "--docker-row",
        dest="docker_rows",
        action="append",
        help="Injected docker ps-style row. Does not query or start containers.",
    )
    args = parser.parse_args(argv)

    service_rows = (
        discover_service_rows() if args.service_rows is None else args.service_rows
    )
    systemd_link_rows = (
        discover_systemd_link_rows()
        if args.systemd_link_rows is None
        else args.systemd_link_rows
    )
    docker_rows = (
        discover_docker_rows() if args.docker_rows is None else args.docker_rows
    )
    if args.check:
        registry = build_hermes_repair_readiness_registry(
            canonical_root=args.canonical_root,
            hermes_agent_root=args.hermes_agent_root,
            runtime_bundle_root=args.runtime_bundle_root,
            archive_bundle_root=args.archive_bundle_root,
            source_bundle_root=args.source_bundle_root,
            service_rows=service_rows,
            systemd_link_rows=systemd_link_rows,
            docker_rows=docker_rows,
        )
        sys.stdout.write(
            json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        return 0

    output = write_hermes_repair_readiness_registry(
        canonical_root=args.canonical_root,
        hermes_agent_root=args.hermes_agent_root,
        runtime_bundle_root=args.runtime_bundle_root,
        archive_bundle_root=args.archive_bundle_root,
        source_bundle_root=args.source_bundle_root,
        service_rows=service_rows,
        systemd_link_rows=systemd_link_rows,
        docker_rows=docker_rows,
    )
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
