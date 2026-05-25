from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json

DEFAULT_RUN_LOG_PATH = Path("/root/nerd-method/memory/reports/nerd-os-runs.jsonl")
ATTENTION_STATUSES = {"blocked", "failed", "missing", "needs_attention"}


def _safe_read_json(path: Path, default: object) -> object:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return default


def _items_from_file(path: Path) -> list[dict[str, object]]:
    payload = _safe_read_json(path, {"items": []})
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    return []


def _read_runs(run_log_path: Path, *, limit: int = 50) -> list[dict[str, object]]:
    if not run_log_path.is_file():
        return []
    runs = []
    for line in run_log_path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            runs.append(payload)
    return runs


def _run_log_item(run_log_path: Path) -> dict[str, object]:
    runs = _read_runs(run_log_path)
    failed_runs = [
        run
        for run in runs
        if int(run.get("exit_code", 0)) != 0 or run.get("timed_out") is True
    ]
    return {
        "id": "observability-run-log",
        "name": "NERD OS Run Log",
        "kind": "run_timeline",
        "status": "needs_attention" if failed_runs else "active",
        "risk": "medium" if failed_runs else "low",
        "path": str(run_log_path),
        "metadata": {
            "run_count": len(runs),
            "failed_runs": len(failed_runs),
            "recent_actions": [run.get("action_id") for run in runs[-8:]],
        },
        "notes": "Recent action runner timeline summarized from JSONL records.",
    }


def _runtime_attention_item(canonical_root: Path) -> dict[str, object]:
    runtimes = _items_from_file(
        canonical_root / "registry" / "runtime-integrations.json"
    )
    attention = [
        item for item in runtimes if str(item.get("status") or "") in ATTENTION_STATUSES
    ]
    return {
        "id": "observability-runtime-attention",
        "name": "Runtime Attention",
        "kind": "runtime_health",
        "status": "needs_attention" if attention else "active",
        "risk": "medium" if attention else "low",
        "metadata": {
            "runtime_count": len(runtimes),
            "attention_count": len(attention),
            "attention_ids": [item.get("id") for item in attention[:10]],
        },
        "notes": "Runtime registry records requiring operator attention.",
    }


def build_observability_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    run_log_path: Path | None = None,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    resolved_run_log = (
        Path(run_log_path)
        if run_log_path is not None
        else canonical_root / "memory" / "reports" / "nerd-os-runs.jsonl"
    )
    items = [
        _run_log_item(resolved_run_log),
        _runtime_attention_item(canonical_root),
    ]
    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_observability_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    run_log_path: Path | None = None,
) -> Path:
    output = Path(canonical_root) / "registry" / "observability-events.json"
    return write_json(
        output,
        build_observability_registry(
            canonical_root=canonical_root,
            run_log_path=run_log_path,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write NERD OS observability registry."
    )
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--run-log-path", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args(argv)
    output = write_observability_registry(
        canonical_root=args.canonical_root,
        run_log_path=args.run_log_path,
    )
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
