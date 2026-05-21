from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

Kind = Literal[
    "repo", "dir", "skill", "service", "config", "doc", "archive", "candidate"
]
Status = Literal[
    "active",
    "staged",
    "legacy",
    "present",
    "missing",
    "investigate",
    "skip_candidate",
    "archived",
]
Risk = Literal["low", "medium", "high", "unknown"]
Action = Literal[
    "keep",
    "index",
    "normalize",
    "install_later",
    "review_later",
    "skip",
    "archive_later",
]


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", cleaned)


@dataclass(frozen=True)
class InventoryItem:
    id: str
    name: str
    kind: Kind
    status: Status
    domain: str = "general"
    risk: Risk = "unknown"
    path: str | None = None
    source_url: str | None = None
    evidence: list[str] = field(default_factory=list)
    recommended_action: Action = "review_later"
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "domain": self.domain,
            "risk": self.risk,
            "recommended_action": self.recommended_action,
            "evidence": sorted(self.evidence),
        }
        if self.path is not None:
            data["path"] = self.path
        if self.source_url is not None:
            data["source_url"] = self.source_url
        if self.notes is not None:
            data["notes"] = self.notes
        return data


@dataclass(frozen=True)
class InventoryReport:
    generated_at: str
    items: list[InventoryItem]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "items": [
                item.to_dict() for item in sorted(self.items, key=lambda item: item.id)
            ],
            "warnings": sorted(self.warnings),
        }


def to_pretty_json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
