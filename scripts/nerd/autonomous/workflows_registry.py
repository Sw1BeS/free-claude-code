from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json


def _workflow(
    *,
    id: str,
    name: str,
    source: str,
    status: str,
    trigger: str,
    last_run: str | None,
    dry_run_available: bool,
    approval_required: bool,
    notes: str,
) -> dict[str, object]:
    return {
        "id": id,
        "name": name,
        "source": source,
        "status": status,
        "trigger": trigger,
        "last_run": last_run,
        "dry_run_available": dry_run_available,
        "approval_required": approval_required,
        "notes": notes,
    }


def build_workflows_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    items = [
        _workflow(
            id="workflow-brain-intake-n8n",
            name="Brain Intake n8n",
            source="n8n",
            status="dry_run_ready",
            trigger="manual_or_webhook",
            last_run=None,
            dry_run_available=True,
            approval_required=False,
            notes="Classifies links/repos/text/files into inbox, task, and memory candidate without direct execution.",
        ),
        _workflow(
            id="workflow-brain-intake-telegram",
            name="Brain Intake Telegram",
            source="webhook",
            status="dry_run_ready",
            trigger="telegram_message",
            last_run=None,
            dry_run_available=True,
            approval_required=False,
            notes="Telegram intake is routed through NERD OS memory candidate flow.",
        ),
        _workflow(
            id="workflow-hermes-gateway-events",
            name="Hermes Gateway Events",
            source="webhook",
            status="active",
            trigger="telegram_discord_gateway",
            last_run=None,
            dry_run_available=False,
            approval_required=False,
            notes="Gateway-driven Hermes runtime events remain active through the generic NERD OS event bridge.",
        ),
        _workflow(
            id="workflow-agency-request-to-delivery",
            name="Agency Request to Delivery",
            source="internal",
            status="active",
            trigger="manual_cli_or_runner_action",
            last_run=None,
            dry_run_available=True,
            approval_required=False,
            notes="Turns an operator request into inbox/task memory, brief, design, implementation, static landing artifact when applicable, deployment handoff, and run evidence.",
        ),
        _workflow(
            id="workflow-openwebui-seed-legacy",
            name="Open WebUI Seed Legacy",
            source="internal",
            status="legacy_optional",
            trigger="manual_action",
            last_run=None,
            dry_run_available=True,
            approval_required=True,
            notes="Open WebUI is optional chat/model surface only, not the NERD OS shell.",
        ),
    ]
    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_workflows_registry(canonical_root: Path = DEFAULT_CANONICAL_ROOT) -> Path:
    output = Path(canonical_root) / "registry" / "workflows-registry.json"
    return write_json(output, build_workflows_registry(canonical_root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write NERD OS workflows registry.")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    args = parser.parse_args(argv)
    output = write_workflows_registry(args.canonical_root)
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
