from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

DEFAULT_CANONICAL_ROOT = Path("/root/nerd-method")

Risk = Literal["low", "medium", "high", "unknown"]
Privacy = Literal["public", "project", "personal", "client", "sensitive"]
AutonomyLevel = Literal["L0", "L1", "L2", "L3", "L4", "L5"]


def to_pretty_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_pretty_json(data), encoding="utf-8")
    return path


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _without_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _sorted_unique(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


@dataclass(frozen=True)
class InboxItem:
    id: str
    created_at: str
    source: str
    raw_text: str
    detected_type: str
    tags: list[str] = field(default_factory=list)
    risk: Risk = "unknown"
    privacy: Privacy = "project"
    status: str = "new"
    source_url: str | None = None
    raw_path: str | None = None
    project: str = "NERD-METHOD"
    client: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _without_none(
            {
                "id": self.id,
                "created_at": self.created_at,
                "source": self.source,
                "source_url": self.source_url,
                "raw_text": self.raw_text,
                "raw_path": self.raw_path,
                "detected_type": self.detected_type,
                "project": self.project,
                "client": self.client,
                "tags": _sorted_unique(self.tags),
                "risk": self.risk,
                "privacy": self.privacy,
                "status": self.status,
            }
        )


@dataclass(frozen=True)
class Task:
    id: str
    inbox_id: str
    title: str
    department: str
    risk: Risk
    autonomy_level: AutonomyLevel
    assigned_agent_role: str
    model_profile: str
    required_approval: bool
    status: str
    priority: str = "medium"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "inbox_id": self.inbox_id,
            "title": self.title,
            "department": self.department,
            "priority": self.priority,
            "risk": self.risk,
            "autonomy_level": self.autonomy_level,
            "assigned_agent_role": self.assigned_agent_role,
            "model_profile": self.model_profile,
            "required_approval": self.required_approval,
            "status": self.status,
            "tags": _sorted_unique(self.tags),
        }


@dataclass(frozen=True)
class RunRecord:
    id: str
    task_id: str
    action_id: str | None
    workflow_id: str | None
    started_at: str
    risk: Risk
    finished_at: str | None = None
    exit_code: int | None = None
    trace_url: str | None = None
    logs_url: str | None = None
    artifact_paths: list[str] = field(default_factory=list)
    writeback_status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return _without_none(
            {
                "id": self.id,
                "task_id": self.task_id,
                "action_id": self.action_id,
                "workflow_id": self.workflow_id,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "exit_code": self.exit_code,
                "risk": self.risk,
                "trace_url": self.trace_url,
                "logs_url": self.logs_url,
                "artifact_paths": sorted(self.artifact_paths),
                "writeback_status": self.writeback_status,
            }
        )


@dataclass(frozen=True)
class MemoryArtifact:
    id: str
    task_id: str
    run_id: str | None
    artifact_type: str
    path: str
    summary: str
    provenance: list[str] = field(default_factory=list)
    promotion_status: str = "candidate"

    def to_dict(self) -> dict[str, Any]:
        return _without_none(
            {
                "id": self.id,
                "task_id": self.task_id,
                "run_id": self.run_id,
                "artifact_type": self.artifact_type,
                "path": self.path,
                "summary": self.summary,
                "provenance": _sorted_unique(self.provenance),
                "promotion_status": self.promotion_status,
            }
        )


@dataclass(frozen=True)
class ApprovalRecord:
    id: str
    task_id: str
    decision: str
    reviewer: str
    decided_at: str
    reason: str | None
    execution_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return _without_none(
            {
                "id": self.id,
                "task_id": self.task_id,
                "decision": self.decision,
                "reviewer": self.reviewer,
                "decided_at": self.decided_at,
                "reason": self.reason,
                "execution_allowed": self.execution_allowed,
            }
        )


@dataclass(frozen=True)
class Department:
    id: str
    name: str
    domain: str
    responsibilities: list[str]
    default_model_profile: str
    default_autonomy_level: AutonomyLevel
    risk_gate: str = "standard"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "responsibilities": sorted(self.responsibilities),
            "default_model_profile": self.default_model_profile,
            "default_autonomy_level": self.default_autonomy_level,
            "risk_gate": self.risk_gate,
        }


@dataclass(frozen=True)
class ModelProfile:
    id: str
    use: str
    privacy: str
    preferred_runtime: str
    fallback_profile: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _without_none(
            {
                "id": self.id,
                "use": self.use,
                "privacy": self.privacy,
                "preferred_runtime": self.preferred_runtime,
                "fallback_profile": self.fallback_profile,
            }
        )


@dataclass(frozen=True)
class WorkflowRecord:
    id: str
    name: str
    provider: str
    path: str | None
    risk: Risk
    autonomy_level: AutonomyLevel
    auto_mode: str
    writes_run_record: bool
    provenance: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _without_none(
            {
                "id": self.id,
                "name": self.name,
                "provider": self.provider,
                "path": self.path,
                "risk": self.risk,
                "autonomy_level": self.autonomy_level,
                "auto_mode": self.auto_mode,
                "writes_run_record": self.writes_run_record,
                "provenance": _sorted_unique(self.provenance),
                "notes": self.notes,
            }
        )


@dataclass(frozen=True)
class ExistingWorkItem:
    id: str
    name: str
    kind: str
    classification: str
    status: str
    path: str
    domain: str
    risk: Risk = "unknown"
    source_url: str | None = None
    evidence: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _without_none(
            {
                "id": self.id,
                "name": self.name,
                "kind": self.kind,
                "classification": self.classification,
                "status": self.status,
                "path": self.path,
                "domain": self.domain,
                "risk": self.risk,
                "source_url": self.source_url,
                "evidence": _sorted_unique(self.evidence),
                "notes": self.notes,
            }
        )
