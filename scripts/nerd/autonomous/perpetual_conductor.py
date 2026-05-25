from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT

DEFAULT_REPORT_DIR = (
    Path("/root/.hermes/hermes-agent")
    / "ops"
    / "hermes-evolution"
    / "reports"
    / "autonomy-supervisor"
)
ATTENTION_STATUSES = {"blocked", "failed", "missing", "needs_attention"}


@dataclass(frozen=True)
class ConductorConfig:
    canonical_root: Path = DEFAULT_CANONICAL_ROOT
    report_dir: Path = DEFAULT_REPORT_DIR
    poll_sec: int = 300
    dry_run: bool = False
    max_cycles: int | None = None


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_read_json(path: Path, default: object) -> object:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return default


def _items(canonical_root: Path, name: str) -> list[dict[str, object]]:
    payload = _safe_read_json(canonical_root / "registry" / name, {"items": []})
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    return []


def _attention_items(
    groups: Iterable[list[dict[str, object]]],
) -> list[dict[str, object]]:
    attention = []
    for records in groups:
        for record in records:
            status = str(record.get("status") or "")
            if status in ATTENTION_STATUSES:
                attention.append(
                    {
                        "id": record.get("id"),
                        "name": record.get("name"),
                        "status": status,
                        "risk": record.get("risk") or record.get("risk_level"),
                    }
                )
    return attention


def _openwebui_core_shell(integrations: list[dict[str, object]]) -> bool:
    for item in integrations:
        if item.get("id") != "integration-openwebui":
            continue
        metadata = item.get("metadata")
        return bool(isinstance(metadata, dict) and metadata.get("core_shell") is True)
    return False


def run_cycle(config: ConductorConfig) -> dict[str, Any]:
    canonical_root = Path(config.canonical_root)
    agents = _items(canonical_root, "hermes-agents.json")
    brain = _items(canonical_root, "brain-memory.json")
    workflows = _items(canonical_root, "workflows-registry.json")
    integrations = _items(canonical_root, "runtime-integrations.json")
    updates = _items(canonical_root, "update-candidates.json")
    attention = _attention_items([agents, brain, workflows, integrations, updates])
    return {
        "generated_at": now_iso(),
        "action": "nerd_os_registry_supervision",
        "dry_run": config.dry_run,
        "canonical_root": str(canonical_root),
        "counts": {
            "hermes_agents": len(agents),
            "brain_items": len(brain),
            "workflows": len(workflows),
            "integrations": len(integrations),
            "updates": len(updates),
            "attention": len(attention),
        },
        "attention_items": attention[:20],
        "openwebui_core_shell": _openwebui_core_shell(integrations),
        "next_action": (
            "review_attention_items" if attention else "continue_registry_supervision"
        ),
    }


def write_evidence(report_dir: Path, record: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"autonomy-supervisor-{stamp}.json"
    payload = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    (report_dir / "autonomy-supervisor-latest.json").write_text(
        payload,
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run generic NERD OS registry supervision loop."
    )
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--poll-sec", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-cycles", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    max_cycles = 1 if args.once else args.max_cycles
    config = ConductorConfig(
        canonical_root=args.canonical_root,
        report_dir=args.report_dir,
        poll_sec=args.poll_sec,
        dry_run=args.dry_run,
        max_cycles=max_cycles,
    )
    cycles = 0
    while True:
        record = run_cycle(config)
        path = write_evidence(config.report_dir, record)
        print(
            json.dumps(
                {
                    "evidence": str(path),
                    "action": record["action"],
                    "dry_run": record["dry_run"],
                    "attention": record["counts"]["attention"],
                },
                ensure_ascii=False,
            )
        )
        cycles += 1
        if config.max_cycles is not None and cycles >= config.max_cycles:
            return 0
        time.sleep(max(1, config.poll_sec))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    except Exception as exc:
        print(f"NERD OS conductor failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
