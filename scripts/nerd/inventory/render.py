from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, cast

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.models import InventoryReport, to_pretty_json
else:
    from .models import InventoryReport, to_pretty_json

SECRET_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])("
    r"sk-or-v1-[A-Za-z0-9]{32,}|"
    r"sk-[A-Za-z0-9]{32,}|"
    r"nvapi-[A-Za-z0-9_-]{20,}|"
    r"wfr_[A-Fa-f0-9]{20,}"
    r")(?![A-Za-z0-9_-])"
)


def redact(value: str | None) -> str:
    if not value:
        return ""
    return SECRET_PATTERN.sub("[REDACTED]", value)


def redact_object(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_object(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_object(item) for key, item in value.items()}
    return value


def render_report_markdown(title: str, report: InventoryReport) -> str:
    lines = [
        f"# {title}",
        "",
        f"Generated: `{report.generated_at}`",
        "",
        "| ID | Name | Kind | Status | Domain | Risk | Action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(report.items, key=lambda entry: entry.id):
        lines.append(
            " | ".join(
                [
                    f"| `{item.id}`",
                    redact(item.name),
                    item.kind,
                    item.status,
                    item.domain,
                    item.risk,
                    f"{item.recommended_action} |",
                ]
            )
        )
        if item.path or item.source_url or item.notes or item.evidence:
            detail = "; ".join(
                part
                for part in [
                    f"path={item.path}" if item.path else "",
                    f"source={item.source_url}" if item.source_url else "",
                    f"notes={redact(item.notes)}" if item.notes else "",
                    f"evidence={', '.join(item.evidence[:5])}" if item.evidence else "",
                ]
                if part
            )
            lines.append(f"|  | {redact(detail)} |  |  |  |  |  |")
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {redact(warning)}" for warning in report.warnings)
    return "\n".join(lines) + "\n"


def write_report_pair(
    output_dir: Path,
    stem: str,
    title: str,
    report: InventoryReport,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{stem}.json").write_text(
        to_pretty_json(cast(dict[str, object], redact_object(report.to_dict()))),
        encoding="utf-8",
    )
    (output_dir / f"{stem}.md").write_text(
        render_report_markdown(title, report),
        encoding="utf-8",
    )
