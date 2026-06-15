from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from scripts.nerd.autonomous.intake import (
    iso_now,
    promote_memory_candidate,
    record_stamp,
    write_brain_intake,
)
from scripts.nerd.autonomous.agency_delivery import (
    DEFAULT_LITELLM_BASE_URL as AGENCY_DEFAULT_LITELLM_BASE_URL,
    DEFAULT_MODEL as AGENCY_DEFAULT_MODEL,
    run_delivery as run_agency_delivery,
)
from scripts.nerd.autonomous.models import ApprovalRecord, write_json
from scripts.nerd.brain.store import (
    brain_candidate_detail,
    build_brain_context_pack,
    build_brain_graph_snapshot,
    build_brain_store_snapshot,
    search_brain_store,
)

DEFAULT_ACTIONS_PATH = Path("/root/nerd-agency-stack/nerd-os.actions.yaml")
DEFAULT_RUN_LOG_PATH = Path("/root/nerd-method/memory/reports/nerd-os-runs.jsonl")
DEFAULT_GIT_REPO_PATH = Path("/root/nerd-claude-free-staging")
DEFAULT_CANONICAL_ROOT = Path("/root/nerd-method")
PUBLIC_BASE_URL = "https://agency.umanoff-analytics.space"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 38181
MAX_JSON_BODY_BYTES = 1_048_576
OS_NAV_ITEMS = (
    ("Mission Control", "mission_control"),
    ("Command Center", "command_center"),
    ("Inbox", "inbox"),
    ("Virtual Office", "office"),
    ("Agents", "agents"),
    ("Tasks / Runs", "tasks"),
    ("Approvals", "approvals"),
    ("Brain", "brain"),
    ("Hermes", "hermes"),
    ("Hermes Repair", "hermes_repair"),
    ("Runtimes", "runtimes"),
    ("Models", "models"),
    ("Updates", "updates"),
    ("Automations", "automations"),
    ("Skills", "skills"),
    ("Workflows", "workflows_registry"),
    ("Integrations", "integrations"),
    ("Memory", "memory"),
    ("Knowledge", "knowledge"),
    ("GitHub", "github"),
    ("Build Studio", "build"),
    ("CMS/Commerce", "cms_commerce"),
    ("Data Studio", "data_studio"),
    ("Product/Growth", "product_growth"),
    ("Observability", "observability"),
    ("Lab", "lab"),
    ("Settings", "settings"),
)
PUBLIC_SERVICE_ROUTES = (
    ("NERD OS", f"{PUBLIC_BASE_URL}/nerd-os/", "Primary mission-control shell"),
    (
        "Mission Control",
        f"{PUBLIC_BASE_URL}/nerd-os/mission-control",
        "Agent fleet, tasks, memory, workflows, and operations",
    ),
    ("Blueprint", f"{PUBLIC_BASE_URL}/nerd-os/blueprint", "Architecture map"),
    ("Virtual Office", f"{PUBLIC_BASE_URL}/nerd-os/office", "Agent rooms"),
    ("Inbox", f"{PUBLIC_BASE_URL}/nerd-os/inbox", "Autonomous intake queue"),
    ("Tasks", f"{PUBLIC_BASE_URL}/nerd-os/tasks", "Draft and routed work"),
    ("Approvals", f"{PUBLIC_BASE_URL}/nerd-os/approvals", "Gated decisions"),
    ("Brain", f"{PUBLIC_BASE_URL}/nerd-os/brain", "Memory, knowledge, and seed state"),
    ("Hermes", f"{PUBLIC_BASE_URL}/nerd-os/hermes", "Hermes agents and objectives"),
    (
        "Hermes Repair",
        f"{PUBLIC_BASE_URL}/nerd-os/hermes-repair",
        "Repair readiness gates",
    ),
    ("Registry", f"{PUBLIC_BASE_URL}/nerd-os/registry", "Canonical state records"),
    ("Runtimes", f"{PUBLIC_BASE_URL}/nerd-os/runtimes", "Hermes, OpenClaw, local LLMs"),
    ("Models", f"{PUBLIC_BASE_URL}/nerd-os/models", "Model routing policy"),
    ("Updates", f"{PUBLIC_BASE_URL}/nerd-os/updates", "Guarded update candidates"),
    ("Runs", f"{PUBLIC_BASE_URL}/nerd-os/runs", "Run records and traces"),
    ("Agents", "https://agents.umanoff-analytics.space", "Agent workspace"),
    (
        "Automations",
        "https://automations.umanoff-analytics.space",
        "n8n and guarded runs",
    ),
    ("Memory", "https://memory.umanoff-analytics.space", "Shared brain"),
    ("Observability", "https://obs.umanoff-analytics.space", "Traces and health"),
    ("CMS/Commerce", "https://cms.umanoff-analytics.space", "Client delivery"),
)
LOCAL_ADDRESS_PATTERN = re.compile(
    r"http://(?:127\.0\.0\.1|localhost|172\.20\.\d+\.\d+)"
    r"(?::\d+)?(?:/[^\s\"'<>]*)?"
)
LOCAL_PATH_PATTERN = re.compile(
    r"(?:/root|/tmp|/home/[^/\s\"'<>]+|/var/(?:tmp|lib|log)|/etc)"
    r"(?:/[^\s\"'<>]*)?"
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?P<key>token|api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|"
    r"secret|password|passwd|authorization|client[_-]?secret|private[_-]?key|"
    r"credentials?|cookie|session[_-]?id)\s*[:=]\s*(?:Bearer\s+)?[^\s,;\"'<>]+",
    re.IGNORECASE,
)
SENSITIVE_BEARER_PATTERN = re.compile(
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)
SENSITIVE_TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9._-]+")
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "access_key",
    "secret",
    "password",
    "passwd",
    "token",
    "credential",
    "credentials",
    "authorization",
    "auth_header",
    "bearer",
    "cookie",
    "session_id",
    "private_key",
    "client_secret",
    "refresh_token",
)
REMOVED_PRODUCT_TERMS = ("paper" + "clip",)
HIDDEN_CORE_UI_STATUSES = {
    "deprecated",
    "legacy_optional",
    "not_configured",
    "optional",
}
HIDDEN_CORE_UI_CLASSIFICATIONS = {
    "optional_legacy_adapter",
    "optional_integration",
}
DEFAULT_OS_CYCLE_ACTIONS = (
    "stack_status",
    "free_claude_status",
    "local_ai_status",
    "litellm_model_list",
    "hermes_status",
    "moneygen_latest_report",
    "codegraph_status",
)


def _surface_route(surface: str) -> str:
    routes = {
        "command_center": ".",
        "mission_control": "mission-control",
        "office": "office",
        "cms_commerce": "cms-commerce",
        "data_studio": "data-studio",
        "product_growth": "product-growth",
        "workflows_registry": "workflows",
    }
    return routes.get(surface, surface.replace("_", "-"))


def _route_to_surface(path: str) -> str | None:
    slug = path.strip("/")
    for _, surface in OS_NAV_ITEMS:
        route = _surface_route(surface).strip("./")
        if route and slug == route:
            return surface
    if slug == "command-center":
        return "command_center"
    return None


class ActionRegistryError(ValueError):
    pass


class DisabledActionError(PermissionError):
    pass


@dataclass(frozen=True)
class Action:
    id: str
    display_name: str
    group: str
    surface: str
    risk: str
    auto_mode: str
    command: tuple[str, ...]
    cwd: Path
    timeout_seconds: int

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Action:
        required = {
            "id",
            "display_name",
            "group",
            "surface",
            "risk",
            "auto_mode",
            "command",
        }
        missing = sorted(key for key in required if key not in raw)
        if missing:
            raise ActionRegistryError(f"Action is missing fields: {', '.join(missing)}")
        command = raw["command"]
        if not isinstance(command, list) or not all(
            isinstance(part, str) and part for part in command
        ):
            raise ActionRegistryError(f"Action {raw.get('id')} has invalid command")
        return cls(
            id=str(raw["id"]),
            display_name=str(raw["display_name"]),
            group=str(raw["group"]),
            surface=str(raw["surface"]),
            risk=str(raw["risk"]),
            auto_mode=str(raw["auto_mode"]),
            command=tuple(command),
            cwd=Path(str(raw.get("cwd", "/root"))),
            timeout_seconds=int(raw.get("timeout_seconds", 30)),
        )


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
        }


class ActionRegistry:
    def __init__(self, actions: list[Action]) -> None:
        self._actions = {action.id: action for action in actions}
        if len(self._actions) != len(actions):
            raise ActionRegistryError("Action ids must be unique")

    @classmethod
    def load(cls, path: Path = DEFAULT_ACTIONS_PATH) -> ActionRegistry:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ActionRegistryError(f"{path} must contain version: 1")
        raw_actions = data.get("actions")
        if not isinstance(raw_actions, list):
            raise ActionRegistryError(f"{path} must contain an actions list")
        return cls([Action.from_mapping(raw) for raw in raw_actions])

    def get(self, action_id: str) -> Action:
        try:
            return self._actions[action_id]
        except KeyError as exc:
            raise ActionRegistryError(f"Unknown action: {action_id}") from exc

    def actions(self) -> list[Action]:
        return sorted(self._actions.values(), key=lambda action: action.id)

    def groups(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for action in self.actions():
            grouped[action.group].append(action.id)
        return dict(grouped)

    def surfaces(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for action in self.actions():
            grouped[action.surface].append(action.id)
        return dict(grouped)


class ActionRunner:
    def __init__(
        self,
        registry: ActionRegistry,
        *,
        log_path: Path = DEFAULT_RUN_LOG_PATH,
    ) -> None:
        self.registry = registry
        self.log_path = log_path

    def run(self, action_id: str, *, allow_disabled: bool = False) -> ActionResult:
        action = self.registry.get(action_id)
        if action.auto_mode != "allowed" and not allow_disabled:
            raise DisabledActionError(f"Action {action.id} is disabled")

        started = time.monotonic()
        try:
            completed = subprocess.run(
                action.command,
                cwd=action.cwd,
                text=True,
                capture_output=True,
                timeout=action.timeout_seconds,
                check=False,
            )
            result = ActionResult(
                action_id=action.id,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=_elapsed_ms(started),
            )
            append_run_log(self.log_path, action, result)
            return result
        except subprocess.TimeoutExpired as exc:
            result = ActionResult(
                action_id=action.id,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or f"Timed out after {action.timeout_seconds}s",
                duration_ms=_elapsed_ms(started),
                timed_out=True,
            )
            append_run_log(self.log_path, action, result)
            return result


def action_summary(registry: ActionRegistry) -> dict[str, object]:
    return {
        "count": len(registry.actions()),
        "groups": registry.groups(),
        "surfaces": registry.surfaces(),
        "actions": [
            {
                "id": action.id,
                "display_name": action.display_name,
                "group": action.group,
                "surface": action.surface,
                "risk": action.risk,
                "auto_mode": action.auto_mode,
                "timeout_seconds": action.timeout_seconds,
                "command": ["<redacted>"],
            }
            for action in registry.actions()
        ],
    }


def public_service_links() -> list[dict[str, str]]:
    return [
        {"label": label, "url": url, "description": description}
        for label, url, description in PUBLIC_SERVICE_ROUTES
    ]


def _redact_local_addresses(value: object) -> object:
    if isinstance(value, str):
        redacted = LOCAL_ADDRESS_PATTERN.sub("[internal backend]", value)
        redacted = LOCAL_PATH_PATTERN.sub("[local path]", redacted)
        redacted = SENSITIVE_ASSIGNMENT_PATTERN.sub(
            lambda match: f"{match.group('key')}=<redacted>",
            redacted,
        )
        redacted = SENSITIVE_BEARER_PATTERN.sub("<redacted>", redacted)
        return SENSITIVE_TOKEN_PATTERN.sub("<redacted>", redacted)
    if isinstance(value, list):
        return [_redact_local_addresses(item) for item in value]
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if _is_sensitive_key(key)
                else _redact_local_addresses(item)
            )
            for key, item in value.items()
        }
    return value


def _is_sensitive_key(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
    if normalized in {"auth_state", "secret_status", "sensitive_key_redaction"}:
        return False
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _record_json_blob(record: dict[str, object]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True).lower()


def _is_hidden_core_ui_record(record: dict[str, object]) -> bool:
    blob = _record_json_blob(record)
    if any(term in blob for term in REMOVED_PRODUCT_TERMS):
        return True
    status = str(record.get("status") or "").strip().lower()
    if status in HIDDEN_CORE_UI_STATUSES:
        return True
    classification = str(record.get("classification") or "").strip().lower()
    return classification in HIDDEN_CORE_UI_CLASSIFICATIONS


def _active_product_records(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [record for record in records if not _is_hidden_core_ui_record(record)]


def _surface_summary(summary: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in summary.items()
        if key in {"canonical_root", "registry", "queues"}
    }


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def append_run_log(log_path: Path, action: Action, result: ActionResult) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action_id": action.id,
        "display_name": action.display_name,
        "group": action.group,
        "surface": action.surface,
        "risk": action.risk,
        "auto_mode": action.auto_mode,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "timed_out": result.timed_out,
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_recent_runs(
    log_path: Path = DEFAULT_RUN_LOG_PATH,
    *,
    limit: int = 25,
) -> list[dict[str, object]]:
    if not log_path.is_file():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    recent = []
    for line in reversed(lines[-limit:]):
        if not line.strip():
            continue
        recent.append(json.loads(line))
    return recent


def _safe_read_json(path: Path, default: object) -> object:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _items_from_record_file(path: Path) -> list[dict[str, object]]:
    payload = _safe_read_json(path, {"items": []})
    if not isinstance(payload, dict):
        return []
    return _safe_record_array(cast("dict[str, object]", payload).get("items"))


def _records_from_dir(path: Path) -> list[dict[str, object]]:
    if not path.is_dir():
        return []
    records = []
    for record_path in sorted(path.glob("*.json")):
        payload = _safe_read_json(record_path, {})
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _action_requests_dir(canonical_root: Path) -> Path:
    return canonical_root / "memory" / "action-requests"


def _action_request_path(request_id: str, canonical_root: Path) -> Path | None:
    normalized = _safe_identifier_part(request_id, fallback="")
    if not normalized:
        return None
    for path in sorted(_action_requests_dir(canonical_root).glob("*.json")):
        payload = _safe_read_json(path, {})
        if isinstance(payload, dict) and payload.get("id") == normalized:
            return path
    return None


def _safe_identifier_part(value: object, *, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return cleaned or fallback


def _run_record_id(run: dict[str, object]) -> str:
    timestamp = str(run.get("timestamp") or "unknown")
    compact_timestamp = re.sub(r"[^0-9A-Za-z]+", "", timestamp) or "unknown"
    action_id = _safe_identifier_part(run.get("action_id"), fallback="action")
    return f"run_{compact_timestamp}_{action_id}"


def _run_record_status(run: dict[str, object]) -> str:
    if run.get("timed_out") is True:
        return "timed_out"
    try:
        exit_code = int(run.get("exit_code", 1))
    except (TypeError, ValueError):
        exit_code = 1
    return "success" if exit_code == 0 else "failed"


def _enrich_run_record(run: dict[str, object]) -> dict[str, object]:
    enriched = dict(run)
    enriched["id"] = _run_record_id(run)
    enriched["status"] = _run_record_status(run)
    enriched.setdefault("name", run.get("display_name") or run.get("action_id"))
    enriched.setdefault("risk", run.get("risk") or "unknown")
    enriched.setdefault("surface", run.get("surface") or "unknown")
    return enriched


def _safe_record_array(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [cast("dict[str, object]", item) for item in value if isinstance(item, dict)]


def _brainstorming_trackio_path(canonical_root: Path) -> Path:
    return canonical_root / "registry" / "brainstorming-trackio.json"


def _write_brainstorming_trackio_items(
    items: list[dict[str, object]],
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> Path:
    return write_json(_brainstorming_trackio_path(canonical_root), {"items": items})


def brainstorming_trackio_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    items = _items_from_record_file(_brainstorming_trackio_path(canonical_root))
    return {
        "summary": {
            "count": len(items),
            "path": str(_brainstorming_trackio_path(canonical_root)),
        },
        "items": items,
    }


BRAINSTORMING_STATUSES = {
    "idea",
    "evaluated",
    "planned",
    "running",
    "shipped",
    "rejected",
}
BRAINSTORMING_PRIORITIES = {"low", "medium", "high", "critical"}


def _trackio_text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _trackio_slug(value: object, fallback: str = "idea") -> str:
    return _safe_identifier_part(value, fallback=fallback).lower()


def create_brainstorming_trackio_idea(
    payload: dict[str, object],
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    title = _trackio_text(payload.get("title"))
    if not title:
        raise ValueError("title is required")
    status = _trackio_text(payload.get("status"), "idea").lower()
    if status not in BRAINSTORMING_STATUSES:
        status = "idea"
    priority = _trackio_text(payload.get("priority"), "medium").lower()
    if priority not in BRAINSTORMING_PRIORITIES:
        priority = "medium"
    now = iso_now()
    idea: dict[str, object] = {
        "id": f"idea_{record_stamp()}_{_trackio_slug(title)}",
        "title": title,
        "description": _trackio_text(
            payload.get("description"), "No description captured yet."
        ),
        "source": _trackio_text(payload.get("source"), "manual"),
        "status": status,
        "priority": priority,
        "related_agent": _trackio_text(payload.get("related_agent"), "unassigned"),
        "related_skill": _trackio_text(payload.get("related_skill"), "unassigned"),
        "related_repo": _trackio_text(payload.get("related_repo"), "unassigned"),
        "next_action": _trackio_text(payload.get("next_action"), "Evaluate and route."),
        "created_at": now,
        "updated_at": now,
    }
    existing_items = _safe_record_array(
        brainstorming_trackio_payload(canonical_root).get("items")
    )
    items = [idea, *existing_items]
    _write_brainstorming_trackio_items(items, canonical_root)
    return {
        "idea": idea,
        "summary": {
            "count": len(items),
            "path": str(_brainstorming_trackio_path(canonical_root)),
        },
    }


def promote_brainstorming_trackio_idea(
    idea_id: str,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    normalized_idea_id = _safe_identifier_part(idea_id, fallback="")
    if not normalized_idea_id:
        raise ValueError("idea_id is required")
    items = _safe_record_array(
        brainstorming_trackio_payload(canonical_root).get("items")
    )
    for index, idea in enumerate(items):
        if idea.get("id") != normalized_idea_id:
            continue
        now = iso_now()
        task: dict[str, object] = {
            "id": f"task_candidate_{record_stamp()}_{_trackio_slug(normalized_idea_id)}",
            "source_idea_id": normalized_idea_id,
            "title": f"Task candidate: {_trackio_text(idea.get('title'), normalized_idea_id)}",
            "description": _trackio_text(
                idea.get("description"), "No description captured yet."
            ),
            "status": "approval_required",
            "required_approval": True,
            "execution_allowed": False,
            "related_agent": _trackio_text(idea.get("related_agent"), "unassigned"),
            "related_skill": _trackio_text(idea.get("related_skill"), "unassigned"),
            "related_repo": _trackio_text(idea.get("related_repo"), "unassigned"),
            "priority": _trackio_text(idea.get("priority"), "medium"),
            "created_at": now,
        }
        updated_idea: dict[str, object] = dict(idea)
        updated_idea["status"] = "planned"
        updated_idea["next_action"] = f"Promoted to {task['id']}"
        updated_idea["updated_at"] = now
        items[index] = updated_idea
        _write_brainstorming_trackio_items(items, canonical_root)
        task_path = canonical_root / "memory" / "tasks" / f"{task['id']}.json"
        write_json(task_path, task)
        return {
            "idea": updated_idea,
            "task": task,
            "paths": {
                "trackio": str(_brainstorming_trackio_path(canonical_root)),
                "task": str(task_path),
            },
            "summary": autonomous_summary(canonical_root),
        }
    raise ValueError(f"unknown idea: {idea_id}")


def _status_needs_attention(status: object) -> bool:
    return str(status or "").strip().lower() in {
        "blocked",
        "needs_attention",
        "failed",
        "missing",
        "timed_out",
        "degraded",
        "approval_required",
        "approval_requested",
        "dirty",
    }


def system_health_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    summary = autonomous_summary(canonical_root)
    observability = _items_from_record_file(
        canonical_root / "registry" / "observability-events.json"
    )
    runtimes = _items_from_record_file(
        canonical_root / "registry" / "runtime-integrations.json"
    )
    runs = autonomous_run_timeline_payload(canonical_root, limit=50)["items"]
    queue_summary = summary["queues"] if isinstance(summary.get("queues"), dict) else {}
    failed_runs = [
        run
        for run in _safe_record_array(runs)
        if _status_needs_attention(run.get("status"))
    ]
    attention_records = [
        record
        for record in _safe_record_array(observability) + _safe_record_array(runtimes)
        if _status_needs_attention(record.get("status"))
    ]
    items: list[dict[str, object]] = []
    if failed_runs:
        items.append(
            {
                "id": "run-failures",
                "name": "Run failures",
                "status": "needs_attention",
                "risk": "medium",
                "notes": f"{len(failed_runs)} recent run(s) need review.",
            }
        )
    items.extend(attention_records)
    if int(queue_summary.get("action_request_count", 0) or 0) > 0:
        items.append(
            {
                "id": "pending-action-requests",
                "name": "Pending action requests",
                "status": "approval_requested",
                "risk": "high",
                "notes": "Operator decisions are waiting.",
            }
        )
    return {
        "summary": {
            "attention_count": len(items),
            "source": "registries_and_run_log",
        },
        "items": items,
    }


def autonomous_summary(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    memory_dir = canonical_root / "memory"
    existing_work = _items_from_record_file(registry_dir / "existing-work.json")
    workflows = _items_from_record_file(registry_dir / "workflows.json")
    runtimes = _items_from_record_file(registry_dir / "runtime-integrations.json")
    brain_memory = _items_from_record_file(registry_dir / "brain-memory.json")
    hermes_agents = _items_from_record_file(registry_dir / "hermes-agents.json")
    hermes_repair = _items_from_record_file(
        registry_dir / "hermes-repair-readiness.json"
    )
    update_candidates = _items_from_record_file(registry_dir / "update-candidates.json")
    skills = _items_from_record_file(registry_dir / "skills-registry.json")
    workflows_registry = _items_from_record_file(
        registry_dir / "workflows-registry.json"
    )
    github_radar = _items_from_record_file(registry_dir / "github-radar.json")
    observability = _items_from_record_file(registry_dir / "observability-events.json")
    brain_store = build_brain_store_snapshot(canonical_root)
    departments = _items_from_record_file(registry_dir / "departments.json")
    models = _items_from_record_file(registry_dir / "models.json")
    inbox_items = _records_from_dir(memory_dir / "inbox")
    tasks = _records_from_dir(memory_dir / "tasks")
    runs = _records_from_dir(memory_dir / "runs")
    approvals = _records_from_dir(memory_dir / "approvals")
    action_requests = _records_from_dir(memory_dir / "action-requests")
    artifacts = _records_from_dir(memory_dir / "artifacts")
    return {
        "canonical_root": str(canonical_root),
        "registry": {
            "existing_work_count": len(existing_work),
            "workflow_count": len(workflows),
            "runtime_count": len(runtimes),
            "brain_count": len(brain_memory),
            "hermes_agent_count": len(hermes_agents),
            "hermes_repair_count": len(hermes_repair),
            "update_candidate_count": len(update_candidates),
            "skills_count": len(skills),
            "workflows_registry_count": len(workflows_registry),
            "github_radar_count": len(github_radar),
            "observability_count": len(observability),
            "department_count": len(departments),
            "model_count": len(models),
            "brain_store_source_count": brain_store.get("source_count", 0),
            "brain_store_episode_count": brain_store.get("episode_count", 0),
            "brain_store_candidate_count": brain_store.get("candidate_count", 0),
        },
        "queues": {
            "inbox_count": len(inbox_items),
            "task_count": len(tasks),
            "run_count": len(runs),
            "approval_count": len(approvals),
            "action_request_count": len(action_requests),
            "artifact_count": len(artifacts),
        },
        "samples": {
            "existing_work": existing_work[:8],
            "workflows": workflows[:8],
            "runtimes": runtimes[:8],
            "brain_memory": brain_memory[:8],
            "hermes_agents": hermes_agents[:8],
            "hermes_repair": hermes_repair[:8],
            "update_candidates": update_candidates[:8],
            "skills": skills[:8],
            "workflows_registry": workflows_registry[:8],
            "github_radar": github_radar[:8],
            "observability": observability[:8],
            "inbox": inbox_items[:8],
            "tasks": tasks[:8],
            "runs": runs[:8],
            "approvals": approvals[:8],
            "action_requests": action_requests[:8],
            "artifacts": artifacts[:8],
        },
    }


def autonomous_registry_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "existing_work": _items_from_record_file(registry_dir / "existing-work.json"),
        "workflows": _items_from_record_file(registry_dir / "workflows.json"),
        "departments": _items_from_record_file(registry_dir / "departments.json"),
        "models": _items_from_record_file(registry_dir / "models.json"),
        "tools": _items_from_record_file(registry_dir / "tools.json"),
        "agents": _items_from_record_file(registry_dir / "agents.json"),
        "runtime_integrations": _items_from_record_file(
            registry_dir / "runtime-integrations.json"
        ),
        "brain_memory": _items_from_record_file(registry_dir / "brain-memory.json"),
        "hermes_agents": _items_from_record_file(registry_dir / "hermes-agents.json"),
        "hermes_repair": _items_from_record_file(
            registry_dir / "hermes-repair-readiness.json"
        ),
        "update_candidates": _items_from_record_file(
            registry_dir / "update-candidates.json"
        ),
        "skills": _items_from_record_file(registry_dir / "skills-registry.json"),
        "workflows_registry": _items_from_record_file(
            registry_dir / "workflows-registry.json"
        ),
        "github_radar": _items_from_record_file(registry_dir / "github-radar.json"),
        "observability": _items_from_record_file(
            registry_dir / "observability-events.json"
        ),
    }


def autonomous_runtime_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "runtime-integrations.json"),
        "model_routing": _safe_read_json(
            canonical_root / "system" / "model-routing.yaml",
            {},
        ),
    }


def autonomous_brain_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    store = build_brain_store_snapshot(canonical_root)
    graph = build_brain_graph_snapshot(canonical_root)
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "brain-memory.json"),
        "store": store,
        "graph": graph,
        "harness": graph.get("harness", {}),
        "context_pack": build_brain_context_pack("", canonical_root, limit=6),
        "candidates": store.get("recent_candidates", []),
        "sources": store.get("sources", []),
    }


def autonomous_brain_store_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    graph = build_brain_graph_snapshot(canonical_root)
    return {
        "summary": autonomous_summary(canonical_root),
        "store": build_brain_store_snapshot(canonical_root),
        "graph": graph,
        "harness": graph.get("harness", {}),
    }


def autonomous_hermes_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "hermes-agents.json"),
    }


def autonomous_hermes_repair_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "hermes-repair-readiness.json"),
    }


def autonomous_updates_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "update-candidates.json"),
    }


def autonomous_skills_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "skills-registry.json"),
    }


def autonomous_workflows_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "workflows-registry.json"),
    }


def autonomous_integrations_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    return autonomous_runtime_payload(canonical_root)


def autonomous_github_radar_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "github-radar.json"),
    }


def autonomous_observability_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    registry_dir = canonical_root / "registry"
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _items_from_record_file(registry_dir / "observability-events.json"),
    }


def autonomous_run_timeline_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    *,
    limit: int = 25,
) -> dict[str, object]:
    run_log_path = canonical_root / "memory" / "reports" / "nerd-os-runs.jsonl"
    runs = [
        _enrich_run_record(run) for run in read_recent_runs(run_log_path, limit=limit)
    ]
    return {
        "summary": autonomous_summary(canonical_root),
        "items": runs,
    }


def autonomous_run_detail_payload(
    run_id: str,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    normalized_run_id = _safe_identifier_part(run_id, fallback="")
    if not normalized_run_id:
        raise ValueError("run_id is required")
    timeline = autonomous_run_timeline_payload(canonical_root, limit=200)
    for run in timeline["items"]:
        if isinstance(run, dict) and run.get("id") == normalized_run_id:
            return {
                "summary": autonomous_summary(canonical_root),
                "item": run,
            }
    raise ValueError(f"unknown run: {run_id}")


def autonomous_action_console_payload(
    registry: ActionRegistry | None = None,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    actions = [] if registry is None else registry.actions()
    items = []
    for action in actions:
        runnable = action.auto_mode == "allowed"
        items.append(
            {
                "id": action.id,
                "name": action.display_name,
                "group": action.group,
                "surface": action.surface,
                "status": "runnable" if runnable else "approval_required",
                "risk": action.risk,
                "execution_policy": action.auto_mode,
                "timeout_seconds": action.timeout_seconds,
                "command": ["<redacted>"],
            }
        )
    return {
        "summary": {
            "total_count": len(items),
            "allowed_count": len(
                [item for item in items if item["execution_policy"] == "allowed"]
            ),
            "disabled_count": len(
                [item for item in items if item["execution_policy"] != "allowed"]
            ),
            "high_risk_count": len([item for item in items if item["risk"] == "high"]),
            "canonical_root": str(canonical_root),
        },
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def autonomous_action_requests_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    requests = _records_from_dir(_action_requests_dir(canonical_root))
    return {
        "summary": autonomous_summary(canonical_root),
        "items": sorted(requests, key=lambda item: str(item.get("id", ""))),
    }


def create_action_approval_request(
    payload: dict[str, object],
    registry: ActionRegistry,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    action_id = str(payload.get("action_id") or payload.get("id") or "").strip()
    if not action_id:
        raise ValueError("action_id is required")
    action = registry.get(action_id)
    if action.auto_mode == "allowed":
        raise ValueError(f"action is already runnable: {action.id}")
    requester = str(payload.get("requester") or "operator").strip() or "operator"
    reason = str(payload.get("reason") or "").strip()
    request = {
        "id": f"action_request_{record_stamp()}",
        "action_id": action.id,
        "action_name": action.display_name,
        "group": action.group,
        "surface": action.surface,
        "risk": action.risk,
        "status": "approval_requested",
        "execution_allowed": False,
        "requester": requester,
        "reason": reason,
        "requested_at": iso_now(),
        "approval_mode": "manual",
        "command": ["<redacted>"],
    }
    request_path = _action_requests_dir(canonical_root) / f"{request['id']}.json"
    write_json(request_path, request)
    return {
        "request": request,
        "paths": {"request": str(request_path)},
        "summary": autonomous_summary(canonical_root),
    }


def decide_action_approval_request(
    request_id: str,
    *,
    decision: str,
    reviewer: str,
    reason: str | None = None,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required")
    request_path = _action_request_path(request_id, canonical_root)
    if request_path is None:
        raise ValueError(f"unknown action request: {request_id}")
    request = _safe_read_json(request_path, {})
    if not isinstance(request, dict):
        raise ValueError(f"invalid action request: {request_id}")
    if request.get("status") not in {"approval_requested", "approved", "rejected"}:
        raise ValueError(f"action request is not pending: {request_id}")

    decided_at = iso_now()
    request["approval_decision"] = normalized_decision
    request["reviewer"] = reviewer
    request["decided_at"] = decided_at
    if reason:
        request["decision_reason"] = reason
    if normalized_decision == "approve":
        request["status"] = "approved"
        request["execution_allowed"] = True
    else:
        request["status"] = "rejected"
        request["execution_allowed"] = False
    write_json(request_path, request)
    return {
        "request": request,
        "paths": {"request": str(request_path)},
        "summary": autonomous_summary(canonical_root),
    }


def _redacted_action_result(result: ActionResult) -> dict[str, object]:
    payload = result.to_dict()
    payload["stdout"] = "<redacted>" if result.stdout else ""
    payload["stderr"] = "<redacted>" if result.stderr else ""
    return payload


def execute_approved_action_request(
    request_id: str,
    registry: ActionRegistry,
    runner: ActionRunner,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    request_path = _action_request_path(request_id, canonical_root)
    if request_path is None:
        raise ValueError(f"unknown action request: {request_id}")
    request = _safe_read_json(request_path, {})
    if not isinstance(request, dict):
        raise ValueError(f"invalid action request: {request_id}")
    if (
        request.get("status") != "approved"
        or request.get("execution_allowed") is not True
    ):
        raise ValueError(f"action request is not approved for execution: {request_id}")
    action_id = str(request.get("action_id") or "").strip()
    if not action_id:
        raise ValueError(f"action request has no action_id: {request_id}")

    registry.get(action_id)
    result = runner.run(action_id, allow_disabled=True)
    request["status"] = "executed" if result.exit_code == 0 else "execution_failed"
    request["executed_at"] = iso_now()
    request["execution_allowed"] = False
    request["result"] = {
        "action_id": result.action_id,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "timed_out": result.timed_out,
    }
    write_json(request_path, request)
    return {
        "request": request,
        "result": _redacted_action_result(result),
        "paths": {"request": str(request_path)},
        "summary": autonomous_summary(canonical_root),
    }


def _os_cycle_actions(
    registry: ActionRegistry,
    requested_action_ids: object,
) -> list[Action]:
    actions_by_id = {action.id: action for action in registry.actions()}
    selected_ids = (
        [
            str(action_id).strip()
            for action_id in requested_action_ids
            if str(action_id).strip()
        ]
        if isinstance(requested_action_ids, list)
        else []
    )
    selected_ids = [
        action_id for action_id in selected_ids if action_id in DEFAULT_OS_CYCLE_ACTIONS
    ]
    if not selected_ids:
        selected_ids = [
            action_id
            for action_id in DEFAULT_OS_CYCLE_ACTIONS
            if action_id in actions_by_id
        ]
    if not selected_ids:
        selected_ids = [
            action.id
            for action in registry.actions()
            if action.auto_mode == "allowed" and action.risk in {"low", "medium"}
        ][:5]
    return [
        actions_by_id[action_id]
        for action_id in selected_ids
        if action_id in actions_by_id
    ]


def run_operating_cycle(
    payload: dict[str, object],
    registry: ActionRegistry,
    runner: ActionRunner,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    cycle_id = f"os_cycle_{record_stamp()}"
    started_at = iso_now()
    results = []
    for action in _os_cycle_actions(registry, payload.get("action_ids")):
        if action.auto_mode != "allowed" or action.risk == "high":
            results.append(
                {
                    "action_id": action.id,
                    "status": "skipped",
                    "exit_code": None,
                    "timed_out": False,
                    "duration_ms": 0,
                    "reason": "Manual approval required.",
                }
            )
            continue
        try:
            result = runner.run(action.id)
            redacted = _redacted_action_result(result)
            results.append(
                {
                    "action_id": action.id,
                    "status": _run_record_status(redacted),
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "duration_ms": result.duration_ms,
                    "stdout": redacted["stdout"],
                    "stderr": redacted["stderr"],
                }
            )
        except (ActionRegistryError, OSError, ValueError) as exc:
            results.append(
                {
                    "action_id": action.id,
                    "status": "failed",
                    "exit_code": 1,
                    "timed_out": False,
                    "duration_ms": 0,
                    "stderr": str(exc),
                }
            )

    failed_count = len(
        [item for item in results if item["status"] in {"failed", "timed_out"}]
    )
    cycle = {
        "id": cycle_id,
        "kind": "operating_cycle",
        "status": "attention_required" if failed_count else "success",
        "started_at": started_at,
        "finished_at": iso_now(),
        "action_count": len(results),
        "failed_count": failed_count,
        "results": results,
    }
    cycle_path = canonical_root / "memory" / "runs" / f"{cycle_id}.json"
    write_json(cycle_path, cycle)
    return {
        "cycle": cycle,
        "paths": {"cycle": str(cycle_path)},
        "summary": autonomous_summary(canonical_root),
    }


def _record_status(record: dict[str, object], default: str = "unknown") -> str:
    return str(record.get("status") or record.get("execution_policy") or default)


def _record_risk(record: dict[str, object], default: str = "unknown") -> str:
    return str(record.get("risk") or record.get("risk_level") or default)


def _record_name(record: dict[str, object]) -> str:
    record_id = str(record.get("id") or "record")
    return str(record.get("name") or record.get("title") or record_id)


AGENCY_DELIVERY_STATUSES = {
    "success",
    "partial",
    "failed",
    "blocked",
    "dry_run",
    "running",
    "planned",
    "unknown",
}
MAX_AGENCY_DELIVERY_RECORDS = 50
MAX_AGENCY_DELIVERY_TEXT_CHARS = 240
MAX_AGENCY_DELIVERY_TITLE_CHARS = 160
MAX_AGENCY_DELIVERY_KEY_CHARS = 64
AGENCY_DELIVERY_HIDDEN_VERIFICATION_KEY_PARTS = {
    "path",
    "file",
    "artifact",
    "url",
}


def _safe_jsonl_records(
    path: Path,
    *,
    limit: int = MAX_AGENCY_DELIVERY_RECORDS,
) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    records: deque[dict[str, object]] = deque(maxlen=limit)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(cast("dict[str, object]", payload))
    except OSError:
        return []
    return list(records)


def _agency_delivery_run_records(
    canonical_root: Path,
    *,
    limit: int = MAX_AGENCY_DELIVERY_RECORDS,
) -> list[dict[str, object]]:
    records = _safe_jsonl_records(
        canonical_root / "memory" / "runs" / "agency-deliveries.jsonl",
        limit=limit,
    )
    delivery_root = canonical_root / "artifacts" / "deliveries"
    if delivery_root.is_dir():
        for run_path in sorted(delivery_root.glob("*/run.json"))[-limit:]:
            payload = _safe_read_json(run_path, {})
            if isinstance(payload, dict):
                records.append(cast("dict[str, object]", payload))
    deduped: dict[str, dict[str, object]] = {}
    for index, record in enumerate(records):
        record_id = str(record.get("id") or f"agency_delivery_{index + 1}")
        deduped[record_id] = record
    return sorted(
        deduped.values(),
        key=lambda record: (
            str(record.get("created_at") or record.get("timestamp") or ""),
            str(record.get("id") or ""),
        ),
        reverse=True,
    )[:limit]


def _agency_delivery_status(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "ok": "success",
        "complete": "success",
        "completed": "success",
        "error": "failed",
        "timed_out": "failed",
        "dryrun": "dry_run",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in AGENCY_DELIVERY_STATUSES else "unknown"


def _agency_delivery_public_status(
    value: object,
    verification: dict[str, object],
) -> str:
    status = _agency_delivery_status(value)
    verification_blob = " ".join(str(item).lower() for item in verification.values())
    if any(term in verification_blob for term in ("failed", "error")):
        return "failed"
    if status == "success" and any(
        term in verification_blob
        for term in ("blocked", "missing", "not_run", "not run", "unknown")
    ):
        return "partial"
    return status


def _delivery_title(record: dict[str, object], record_id: str) -> str:
    for key in ("title", "summary", "name", "request"):
        value = str(record.get(key) or "").strip()
        if value:
            return _delivery_text(
                value.splitlines()[0],
                max_chars=MAX_AGENCY_DELIVERY_TITLE_CHARS,
            )
    return record_id


def _delivery_text(
    value: object,
    fallback: str = "",
    *,
    max_chars: int = MAX_AGENCY_DELIVERY_TEXT_CHARS,
) -> str:
    text = str(value or "").strip() or fallback
    text = cast("str", _redact_local_addresses(text))
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _delivery_artifact_count(record: dict[str, object]) -> int:
    artifacts = record.get("artifact_paths")
    if isinstance(artifacts, list):
        return len(artifacts)
    try:
        return max(0, int(record.get("artifact_count", 0)))
    except (TypeError, ValueError):
        return 0


def _delivery_verification(record: dict[str, object]) -> dict[str, object]:
    verification = record.get("verification")
    if isinstance(verification, dict):
        normalized = {
            _delivery_text(key, max_chars=MAX_AGENCY_DELIVERY_KEY_CHARS): _delivery_text(value)
            for key, value in verification.items()
            if value is not None
            and not isinstance(value, (dict, list))
            and not any(
                part
                in re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
                for part in AGENCY_DELIVERY_HIDDEN_VERIFICATION_KEY_PARTS
            )
        }
        return normalized or {"summary": "unknown"}
    if verification is None:
        return {"summary": "unknown"}
    return {"summary": _delivery_text(verification)}


def _normalize_agency_delivery(record: dict[str, object]) -> dict[str, object]:
    redacted = cast("dict[str, object]", _redact_local_addresses(record))
    record_id = str(redacted.get("id") or redacted.get("run_id") or "agency_delivery")
    verification = _delivery_verification(redacted)
    public_record: dict[str, object] = {
        "id": _safe_identifier_part(record_id, fallback="agency_delivery"),
        "title": _delivery_title(redacted, record_id),
        "status": _agency_delivery_public_status(redacted.get("status"), verification),
        "risk": _delivery_text(redacted.get("risk"), "not_set", max_chars=48),
        "mode": _delivery_text(redacted.get("mode"), "unknown", max_chars=48),
        "task_id": _delivery_text(redacted.get("task_id"), max_chars=96),
        "created_at": _delivery_text(
            redacted.get("created_at") or redacted.get("timestamp"),
            max_chars=64,
        ),
        "verification": verification,
        "artifact_count": _delivery_artifact_count(redacted),
        "next_action": _delivery_text(redacted.get("next_action"), max_chars=160),
    }
    blocker = _delivery_text(redacted.get("blocker"), max_chars=180)
    if blocker:
        public_record["blocker"] = blocker
    return public_record


def autonomous_agency_deliveries_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    *,
    limit: int = MAX_AGENCY_DELIVERY_RECORDS,
) -> dict[str, object]:
    items = [
        _normalize_agency_delivery(record)
        for record in _agency_delivery_run_records(canonical_root, limit=limit)
    ]
    return {
        "summary": {
            "count": len(items),
            "source": "agency_delivery_runs",
        },
        "items": items,
    }


def _mission_node(
    record: dict[str, object],
    *,
    kind: str,
    source: str,
) -> dict[str, object]:
    record_id = str(record.get("id") or record.get("action_id") or f"{kind}_record")
    return {
        "id": record_id,
        "kind": kind,
        "source": source,
        "name": _record_name(record),
        "status": _record_status(record),
        "risk": _record_risk(record),
        "surface": str(record.get("surface") or record.get("department") or ""),
    }


def _operation_graph_payload(
    *,
    action_console: list[dict[str, object]],
    run_timeline: list[dict[str, object]],
    tasks: list[dict[str, object]],
    agents: list[dict[str, object]],
    workflows: list[dict[str, object]],
    integrations: list[dict[str, object]],
) -> dict[str, object]:
    nodes: list[dict[str, object]] = []
    for source, kind, records in [
        ("action_console", "action", action_console),
        ("run_timeline", "run", run_timeline),
        ("tasks", "task", tasks),
        ("agents", "agent", agents),
        ("workflows", "workflow", workflows),
        ("integrations", "integration", integrations),
    ]:
        nodes.extend(
            _mission_node(record, kind=kind, source=source)
            for record in records[:40]
            if isinstance(record, dict)
        )

    node_ids = {str(node["id"]) for node in nodes}
    edges: list[dict[str, object]] = []
    for run in run_timeline[:60]:
        action_id = str(run.get("action_id") or "")
        run_id = str(run.get("id") or "")
        if action_id in node_ids and run_id in node_ids:
            edges.append({"from": action_id, "to": run_id, "kind": "produced_run"})
    for task in tasks[:60]:
        task_id = str(task.get("id") or "")
        agent_id = str(task.get("related_agent") or task.get("agent_id") or "")
        if agent_id in node_ids and task_id in node_ids:
            edges.append({"from": agent_id, "to": task_id, "kind": "owns_task"})
        workflow_id = str(task.get("workflow_id") or task.get("related_workflow") or "")
        if workflow_id in node_ids and task_id in node_ids:
            edges.append({"from": workflow_id, "to": task_id, "kind": "routes_task"})
    for workflow in workflows[:60]:
        workflow_id = str(workflow.get("id") or "")
        integration_id = str(
            workflow.get("integration_id")
            or workflow.get("runtime_id")
            or workflow.get("related_integration")
            or ""
        )
        if workflow_id in node_ids and integration_id in node_ids:
            edges.append(
                {"from": workflow_id, "to": integration_id, "kind": "uses_integration"}
            )

    return {
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source": "registry_run_brain_action_data",
        },
        "nodes": nodes,
        "edges": edges,
    }


def _attention_queue_payload(
    *,
    warnings: list[dict[str, object]],
    system_health: list[dict[str, object]],
    tasks: list[dict[str, object]],
    approvals: list[dict[str, object]],
    action_requests: list[dict[str, object]],
    run_timeline: list[dict[str, object]],
) -> dict[str, object]:
    candidates = (
        list(warnings)
        + list(system_health)
        + list(approvals)
        + list(action_requests)
        + [
            task
            for task in tasks
            if _status_needs_attention(task.get("status"))
            or task.get("required_approval") is True
        ]
        + [
            run
            for run in run_timeline
            if _status_needs_attention(run.get("status"))
        ]
    )
    severity_order = {"high": 0, "critical": 0, "medium": 1, "low": 2}
    deduped: dict[str, dict[str, object]] = {}
    for record in candidates:
        record_id = str(record.get("id") or record.get("action_id") or _record_name(record))
        deduped[record_id] = {
            "id": record_id,
            "name": _record_name(record),
            "status": _record_status(record),
            "risk": _record_risk(record),
            "source": str(record.get("source") or record.get("kind") or "mission_control"),
            "next_action": str(
                record.get("next_action")
                or record.get("notes")
                or record.get("reason")
                or "Review in Mission Control."
            ),
        }
    items = sorted(
        deduped.values(),
        key=lambda item: (
            severity_order.get(str(item.get("risk")).lower(), 3),
            str(item.get("id")),
        ),
    )
    return {
        "summary": {"count": len(items), "source": "warnings_queues_and_runs"},
        "items": items,
    }


def _evidence_index_payload(
    *,
    brain_store: object,
    brain_graph: object,
    github_radar: list[dict[str, object]],
    observability: list[dict[str, object]],
    run_timeline: list[dict[str, object]],
) -> dict[str, object]:
    store = brain_store if isinstance(brain_store, dict) else {}
    graph = brain_graph if isinstance(brain_graph, dict) else {}
    items: list[dict[str, object]] = []
    for source in _safe_record_array(store.get("sources"))[:30]:
        items.append(
            {
                "id": str(source.get("id") or _record_name(source)),
                "kind": "brain_source",
                "title": _record_name(source),
                "status": _record_status(source, "indexed"),
                "source": "brain_store",
            }
        )
    for candidate in _safe_record_array(store.get("recent_candidates"))[:30]:
        items.append(
            {
                "id": str(candidate.get("id") or candidate.get("candidate_id") or _record_name(candidate)),
                "kind": "brain_candidate",
                "title": _record_name(candidate),
                "status": _record_status(candidate),
                "source": "brain_store",
            }
        )
    for source_name, kind, records in [
        ("github_radar", "repo_signal", github_radar),
        ("observability", "observability_event", observability),
        ("run_timeline", "run_record", run_timeline),
    ]:
        for record in records[:30]:
            items.append(
                {
                    "id": str(record.get("id") or record.get("action_id") or _record_name(record)),
                    "kind": kind,
                    "title": _record_name(record),
                    "status": _record_status(record),
                    "source": source_name,
                }
            )
    return {
        "summary": {
            "count": len(items),
            "graph_status": graph.get("status", "unknown"),
            "source": "brain_github_observability_runs",
        },
        "items": items,
    }


def _domain_routes_payload(
    *,
    integrations: list[dict[str, object]],
) -> dict[str, object]:
    public_routes = [
        {
            "id": _safe_identifier_part(link["label"]).lower(),
            "label": link["label"],
            "url": link["url"],
            "description": link["description"],
            "kind": "public_service",
            "status": "published",
        }
        for link in public_service_links()
    ]
    nav_routes = [
        {
            "id": surface,
            "label": label,
            "url": f"{PUBLIC_BASE_URL}/nerd-os/{_surface_route(surface).strip('./')}",
            "kind": "nerd_os_surface",
            "status": "published",
        }
        for label, surface in OS_NAV_ITEMS
        if _surface_route(surface) != "."
    ]
    integration_routes = []
    for integration in integrations:
        metadata = integration.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        url = integration.get("url") or metadata.get("url") or metadata.get("base_url")
        if url:
            integration_routes.append(
                {
                    "id": str(integration.get("id") or _record_name(integration)),
                    "label": _record_name(integration),
                    "url": str(url),
                    "kind": "integration_endpoint",
                    "status": _record_status(integration),
                }
            )
    routes = public_routes + nav_routes + integration_routes
    return {
        "summary": {"count": len(routes), "source": "public_routes_nav_integrations"},
        "items": routes,
    }


def _policy_matrix_payload(
    *,
    action_console: list[dict[str, object]],
    tasks: list[dict[str, object]],
    approvals: list[dict[str, object]],
    updates: list[dict[str, object]],
    integrations: list[dict[str, object]],
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for action in action_console:
        items.append(
            {
                "id": str(action.get("id") or "action"),
                "kind": "action",
                "policy": str(action.get("execution_policy") or "disabled"),
                "risk": _record_risk(action),
                "status": _record_status(action),
                "execution_allowed": action.get("execution_policy") == "allowed",
            }
        )
    for task in tasks:
        items.append(
            {
                "id": str(task.get("id") or "task"),
                "kind": "task",
                "policy": "approval_required"
                if task.get("required_approval") is True
                else "standard_queue",
                "risk": _record_risk(task),
                "status": _record_status(task),
                "execution_allowed": task.get("execution_allowed") is True,
            }
        )
    for source, kind, records in [
        ("approvals", "approval", approvals),
        ("updates", "update", updates),
        ("integrations", "integration", integrations),
    ]:
        for record in records:
            items.append(
                {
                    "id": str(record.get("id") or _record_name(record)),
                    "kind": kind,
                    "policy": str(
                        record.get("policy")
                        or record.get("approval_mode")
                        or record.get("auto_mode")
                        or source
                    ),
                    "risk": _record_risk(record),
                    "status": _record_status(record),
                    "execution_allowed": record.get("execution_allowed") is True,
                }
            )
    return {
        "summary": {
            "count": len(items),
            "manual_gate_count": len(
                [
                    item
                    for item in items
                    if item["execution_allowed"] is not True
                    and str(item["risk"]).lower() in {"high", "critical"}
                ]
            ),
            "source": "actions_tasks_approvals_updates_integrations",
        },
        "items": items,
    }


def _auth_state_payload() -> dict[str, object]:
    return {
        "status": "externalized",
        "mode": "upstream_gateway",
        "principal": "not_available_to_bff",
        "notes": "Mission Control BFF does not receive request identity in this runner.",
    }


def _secret_status_payload() -> dict[str, object]:
    return {
        "status": "redaction_enabled",
        "sensitive_key_redaction": True,
        "local_backend_redaction": True,
        "redacted_value": "<redacted>",
    }


def autonomous_mission_control_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    registry: ActionRegistry | None = None,
) -> dict[str, object]:
    summary = autonomous_summary(canonical_root)
    brain_payload = autonomous_brain_payload(canonical_root)
    brain = brain_payload["items"]
    brain_store = brain_payload["store"]
    brain_graph = brain_payload["graph"]
    brain_harness = brain_payload["harness"]
    agents = autonomous_hermes_payload(canonical_root)["items"]
    updates = autonomous_updates_payload(canonical_root)["items"]
    integrations = autonomous_integrations_payload(canonical_root)["items"]
    skills = autonomous_skills_payload(canonical_root)["items"]
    workflows = autonomous_workflows_payload(canonical_root)["items"]
    github_radar = autonomous_github_radar_payload(canonical_root)["items"]
    observability = autonomous_observability_payload(canonical_root)["items"]
    run_timeline = autonomous_run_timeline_payload(canonical_root)["items"]
    tasks = autonomous_queue_payload("tasks", canonical_root)["items"]
    approvals = autonomous_approval_payload(canonical_root)["items"]
    action_requests = autonomous_action_requests_payload(canonical_root)["items"]
    action_console = autonomous_action_console_payload(
        registry,
        canonical_root=canonical_root,
    )["items"]
    agency_deliveries = autonomous_agency_deliveries_payload(canonical_root)["items"]
    trackio = brainstorming_trackio_payload(canonical_root)["items"]
    system_health = system_health_payload(canonical_root)["items"]
    queues = summary["queues"] if isinstance(summary.get("queues"), dict) else {}
    registry_counts = (
        summary["registry"] if isinstance(summary.get("registry"), dict) else {}
    )
    warnings = [
        item
        for item in list(updates) + list(integrations)
        if isinstance(item, dict)
        and str(item.get("status")) in {"blocked", "needs_attention", "failed"}
    ]
    operation_graph = _operation_graph_payload(
        action_console=_safe_record_array(action_console),
        run_timeline=_safe_record_array(run_timeline),
        tasks=_safe_record_array(tasks),
        agents=_safe_record_array(agents),
        workflows=_safe_record_array(workflows),
        integrations=_safe_record_array(integrations),
    )
    attention_queue = _attention_queue_payload(
        warnings=_safe_record_array(warnings),
        system_health=_safe_record_array(system_health),
        tasks=_safe_record_array(tasks),
        approvals=_safe_record_array(approvals),
        action_requests=_safe_record_array(action_requests),
        run_timeline=_safe_record_array(run_timeline),
    )
    evidence_index = _evidence_index_payload(
        brain_store=brain_store,
        brain_graph=brain_graph,
        github_radar=_safe_record_array(github_radar),
        observability=_safe_record_array(observability),
        run_timeline=_safe_record_array(run_timeline),
    )
    domain_routes = _domain_routes_payload(integrations=_safe_record_array(integrations))
    policy_matrix = _policy_matrix_payload(
        action_console=_safe_record_array(action_console),
        tasks=_safe_record_array(tasks),
        approvals=_safe_record_array(approvals),
        updates=_safe_record_array(updates),
        integrations=_safe_record_array(integrations),
    )
    payload: dict[str, object] = {
        "schema_version": "mission_control.v2",
        "product": "NERD OS Mission Control",
        "auth_state": _auth_state_payload(),
        "secret_status": _secret_status_payload(),
        "summary": _surface_summary(summary),
        "overview": {
            "system_status": "operational" if not warnings else "attention_required",
            "active_hermes_agents": registry_counts.get("hermes_agent_count", 0),
            "inbox_count": queues.get("inbox_count", 0),
            "task_count": queues.get("task_count", 0),
            "memory_items": registry_counts.get("brain_count", 0),
            "brain_store_episodes": registry_counts.get("brain_store_episode_count", 0),
            "brain_store_candidates": registry_counts.get(
                "brain_store_candidate_count", 0
            ),
            "update_candidates": registry_counts.get("update_candidate_count", 0),
            "runtime_integrations": registry_counts.get("runtime_count", 0),
            "warnings": len(warnings),
            "action_console_items": len(action_console),
            "run_timeline_items": len(run_timeline),
            "agency_delivery_items": len(agency_deliveries),
            "action_request_items": len(action_requests),
            "github_radar_items": len(github_radar),
            "observability_items": len(observability),
            "core_shell": "NERD OS Mission Control",
            "reference": "builderz-labs/mission-control",
        },
        "sections": {
            "action_console": action_console,
            "run_timeline": run_timeline,
            "tasks": tasks,
            "approvals": approvals,
            "action_requests": action_requests,
            "agency_deliveries": agency_deliveries,
            "agents": agents,
            "brain": brain,
            "brain_store": brain_store,
            "brain_graph": brain_graph,
            "brain_harness": brain_harness,
            "updates": updates,
            "integrations": integrations,
            "skills": skills,
            "workflows": workflows,
            "github_radar": github_radar,
            "observability": observability,
            "system_health": system_health,
            "brainstorming_trackio": trackio,
            "operation_graph": operation_graph,
            "attention_queue": attention_queue,
            "evidence_index": evidence_index,
            "domain_routes": domain_routes,
            "policy_matrix": policy_matrix,
            "warnings": warnings,
        },
    }
    return cast("dict[str, object]", _redact_local_addresses(payload))


def autonomous_api_payload(
    path: str,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    registry: ActionRegistry | None = None,
) -> dict[str, object] | None:
    parsed = urlparse(path)
    request_path = _request_path(path)
    query_params = parse_qs(parsed.query)
    path = request_path
    if path == "/api/mission-control":
        return autonomous_mission_control_payload(canonical_root, registry=registry)
    if path == "/api/autonomous/registry":
        return autonomous_registry_payload(canonical_root)
    if path == "/api/autonomous/action-requests":
        return autonomous_action_requests_payload(canonical_root)
    if path == "/api/autonomous/brainstorming-trackio":
        return brainstorming_trackio_payload(canonical_root)
    if path.startswith("/api/autonomous/run-detail/"):
        run_id = path.removeprefix("/api/autonomous/run-detail/")
        return autonomous_run_detail_payload(run_id, canonical_root)
    if path == "/api/autonomous/inbox":
        return autonomous_queue_payload("inbox", canonical_root)
    if path == "/api/autonomous/tasks":
        return autonomous_queue_payload("tasks", canonical_root)
    if path == "/api/autonomous/approvals":
        return autonomous_approval_payload(canonical_root)
    if path == "/api/autonomous/brain":
        return autonomous_brain_payload(canonical_root)
    if path == "/api/autonomous/brain-store":
        return autonomous_brain_store_payload(canonical_root)
    if path == "/api/autonomous/brain/context":
        query = (query_params.get("q") or query_params.get("query") or [""])[0]
        raw_limit = (query_params.get("limit") or ["8"])[0]
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 8
        return build_brain_context_pack(query, canonical_root, limit=limit)
    if path == "/api/autonomous/brain/search":
        query = (query_params.get("q") or query_params.get("query") or [""])[0]
        raw_limit = (query_params.get("limit") or ["8"])[0]
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 8
        return search_brain_store(query, canonical_root, limit=limit)
    if path.startswith("/api/autonomous/brain/candidates/"):
        candidate_id = unquote(path.removeprefix("/api/autonomous/brain/candidates/"))
        if not candidate_id or "/" in candidate_id:
            return None
        return brain_candidate_detail(candidate_id, canonical_root)
    if path == "/api/autonomous/hermes":
        return autonomous_hermes_payload(canonical_root)
    if path == "/api/autonomous/hermes-repair":
        return autonomous_hermes_repair_payload(canonical_root)
    if path == "/api/autonomous/runtimes":
        return autonomous_integrations_payload(canonical_root)
    if path == "/api/autonomous/updates":
        return autonomous_updates_payload(canonical_root)
    if path == "/api/autonomous/runs":
        return autonomous_queue_payload("runs", canonical_root)
    return None


def autonomous_queue_payload(
    kind: str,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    queue_dirs = {
        "inbox": canonical_root / "memory" / "inbox",
        "tasks": canonical_root / "memory" / "tasks",
        "runs": canonical_root / "memory" / "runs",
        "approvals": canonical_root / "memory" / "approvals",
        "artifacts": canonical_root / "memory" / "artifacts",
    }
    if kind not in queue_dirs:
        raise ValueError(f"Unknown queue: {kind}")
    return {
        "summary": autonomous_summary(canonical_root),
        "items": _records_from_dir(queue_dirs[kind]),
    }


def _execution_allowed_for_task(task: dict[str, object]) -> bool:
    risk = str(task.get("risk") or "")
    autonomy_level = str(task.get("autonomy_level") or "")
    department = str(task.get("department") or "")
    return risk != "high" and autonomy_level not in {"L4", "L5"} and department != "lab"


def autonomous_approval_payload(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    tasks = _records_from_dir(canonical_root / "memory" / "tasks")
    approvals = _records_from_dir(canonical_root / "memory" / "approvals")
    pending = []
    for task in tasks:
        if (
            task.get("required_approval") is True
            and task.get("status") == "approval_required"
        ):
            task = dict(task)
            task["execution_allowed"] = _execution_allowed_for_task(task)
            pending.append(task)
    return {
        "summary": autonomous_summary(canonical_root),
        "items": sorted(pending, key=lambda item: str(item.get("id"))),
        "approvals": sorted(approvals, key=lambda item: str(item.get("id"))),
    }


def _task_record_path(task_id: str, canonical_root: Path) -> Path | None:
    task_dir = canonical_root / "memory" / "tasks"
    for path in sorted(task_dir.glob("*.json")):
        task = _safe_read_json(path, {})
        if isinstance(task, dict) and task.get("id") == task_id:
            return path
    return None


def update_autonomous_task_approval(
    task_id: str,
    *,
    decision: str,
    reviewer: str,
    reason: str | None = None,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    task_path = _task_record_path(task_id, canonical_root)
    if task_path is None:
        raise ValueError(f"unknown task: {task_id}")
    task = _safe_read_json(task_path, {})
    if not isinstance(task, dict):
        raise ValueError(f"invalid task: {task_id}")
    if task.get("required_approval") is not True:
        raise ValueError(f"task does not require approval: {task_id}")

    execution_allowed = _execution_allowed_for_task(task)
    if normalized_decision == "reject":
        task["status"] = "rejected"
        task["execution_allowed"] = False
    elif execution_allowed:
        task["status"] = "approved"
        task["execution_allowed"] = True
    else:
        task["status"] = "approved_for_research"
        task["execution_allowed"] = False

    decided_at = iso_now()
    task["approval_decision"] = normalized_decision
    task["approved_by"] = reviewer.strip()
    task["approved_at"] = decided_at
    if reason:
        task["approval_reason"] = reason
    write_json(task_path, task)

    approval = ApprovalRecord(
        id=f"approval_{record_stamp()}",
        task_id=task_id,
        decision=normalized_decision,
        reviewer=reviewer.strip(),
        decided_at=decided_at,
        reason=reason,
        execution_allowed=bool(task["execution_allowed"]),
    )
    approval_path = canonical_root / "memory" / "approvals" / f"{approval.id}.json"
    write_json(approval_path, approval.to_dict())
    return {
        "task": task,
        "approval": approval.to_dict(),
        "paths": {
            "task": str(task_path),
            "approval": str(approval_path),
        },
        "summary": autonomous_summary(canonical_root),
    }


def create_autonomous_inbox_record(
    payload: dict[str, object],
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    text = str(
        payload.get("text") or payload.get("raw_text") or payload.get("message") or ""
    ).strip()
    if not text:
        raise ValueError("text is required")
    source = str(payload.get("source") or "web")
    raw_source_url = payload.get("source_url")
    source_url = str(raw_source_url).strip() if raw_source_url else None
    result = write_brain_intake(
        text,
        canonical_root=canonical_root,
        source=source,
        source_url=source_url,
    )
    paths = result["paths"]
    inbox = _safe_read_json(paths["inbox"], {})
    task = _safe_read_json(paths["task"], {})
    candidate = _safe_read_json(paths["candidate"], {})
    return {
        "inbox": inbox,
        "task": task,
        "candidate": candidate,
        "paths": {
            "inbox": str(paths["inbox"]),
            "task": str(paths["task"]),
            "candidate": str(paths["candidate"]),
            "candidate_markdown": str(paths["candidate_markdown"]),
        },
        "summary": autonomous_summary(canonical_root),
    }


def create_autonomous_brain_record(
    payload: dict[str, object],
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    brain_payload = dict(payload)
    brain_payload.setdefault("source", "brain")
    result = create_autonomous_inbox_record(
        brain_payload,
        canonical_root=canonical_root,
    )
    result["brain_store"] = build_brain_store_snapshot(canonical_root)
    return result


def _payload_bool(payload: dict[str, object], key: str, default: bool) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def create_agency_delivery(
    payload: dict[str, object],
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    request = str(
        payload.get("text") or payload.get("request") or payload.get("message") or ""
    ).strip()
    if not request:
        raise ValueError("text is required")
    mode = str(payload.get("mode") or "auto").strip() or "auto"
    if mode not in {"auto", "landing_page", "implementation"}:
        raise ValueError("mode must be auto, landing_page, or implementation")
    source = str(payload.get("source") or "operator").strip() or "operator"
    try:
        timeout_seconds = float(payload.get("timeout_seconds") or 90.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be a number") from exc
    if timeout_seconds < 5 or timeout_seconds > 300:
        raise ValueError("timeout_seconds must be between 5 and 300")

    output_root = None
    raw_output_root = str(payload.get("output_root") or "").strip()
    if raw_output_root:
        output_root = Path(raw_output_root)
    task_id = str(payload.get("task_id") or "").strip()
    no_static_site = _payload_bool(payload, "no_static_site", False)
    delivery = run_agency_delivery(
        request,
        canonical_root=canonical_root,
        output_root=output_root,
        source=source,
        task_id=task_id or None,
        mode=mode,
        model=str(payload.get("model") or AGENCY_DEFAULT_MODEL),
        base_url=str(payload.get("base_url") or AGENCY_DEFAULT_LITELLM_BASE_URL),
        timeout_seconds=timeout_seconds,
        offline=_payload_bool(payload, "offline", True),
        dry_run=_payload_bool(payload, "dry_run", False),
        no_intake=bool(task_id) or _payload_bool(payload, "no_intake", False),
        build_static_site=not no_static_site
        and _payload_bool(payload, "build_static_site", True),
        browser_smoke=_payload_bool(payload, "browser_smoke", True),
        auto_deploy=_payload_bool(payload, "auto_deploy", False),
    )
    return {
        "delivery": delivery,
        "summary": autonomous_summary(canonical_root),
    }


def promote_autonomous_brain_candidate(
    candidate_id: str,
    payload: dict[str, object] | None = None,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    payload = payload or {}
    reviewer = str(payload.get("reviewer") or "operator").strip() or "operator"
    promoted = promote_memory_candidate(
        candidate_id,
        canonical_root=canonical_root,
        reviewer=reviewer,
    )
    graph = build_brain_graph_snapshot(canonical_root)
    return {
        "promoted": {
            "artifact": promoted["artifact"],
            "candidate_path": str(promoted["candidate_path"]),
            "knowledge_path": str(promoted["knowledge_path"]),
            "brain_store": promoted["brain_store"],
        },
        "store": build_brain_store_snapshot(canonical_root),
        "graph": graph,
        "harness": graph.get("harness", {}),
        "summary": autonomous_summary(canonical_root),
    }


def _render_record_rows(records: list[dict[str, object]]) -> str:
    if not records:
        return '<tr><td colspan="4">No records yet</td></tr>'
    rows = []
    for record in records[:80]:
        record_id = str(record.get("id", "record"))
        name = str(record.get("name") or record.get("title") or record_id)
        status = str(record.get("status") or record.get("classification") or "")
        risk = str(record.get("risk") or record.get("risk_level") or "")
        rows.append(
            f"""
            <tr>
              <td><code>{html.escape(record_id)}</code></td>
              <td>{html.escape(name)}</td>
              <td>{html.escape(status)}</td>
              <td>{html.escape(risk)}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def _action_records_for_surface(
    registry: ActionRegistry,
    surface: str,
) -> list[dict[str, object]]:
    records = []
    for action in registry.actions():
        include = action.surface == surface
        if surface == "automations" and action.group == "automation_ops":
            include = True
        if surface == "lab" and (action.surface == "lab" or action.risk == "high"):
            include = True
        if include:
            records.append(
                {
                    "id": action.id,
                    "name": action.display_name,
                    "status": action.auto_mode,
                    "risk": action.risk,
                    "kind": "action",
                }
            )
    return records


def _record_text(record: dict[str, object], *keys: str, default: str = "") -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        value = _redact_local_addresses(value)
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value[:3])
        if isinstance(value, dict):
            return ", ".join(
                f"{name}: {data}" for name, data in list(value.items())[:3]
            )
        text = str(value)
        if text:
            return text
    return default


def _mission_status_class(value: object) -> str:
    status = str(value or "unknown").lower()
    if status in {
        "active",
        "present",
        "approved",
        "configured",
        "dry_run_ready",
        "runnable",
        "success",
    }:
        return "ok"
    if status in {"optional", "legacy_optional", "not_configured", "deprecated"}:
        return "muted"
    if status in {
        "blocked",
        "needs_attention",
        "failed",
        "missing",
        "approval_required",
        "approval_requested",
        "timed_out",
    }:
        return "warn"
    return "info"


def _mission_card(
    record: dict[str, object], *, detail_keys: tuple[str, ...] = ()
) -> str:
    record_id = _record_text(record, "id", default="record")
    name = _record_text(record, "name", "title", default=record_id)
    status = _record_text(record, "status", "classification", default="unknown")
    risk = _record_text(record, "risk", "risk_level", default="")
    kind = _record_text(record, "kind", "source", "category", default="")
    detail_values = [
        _record_text(record, key) for key in detail_keys if _record_text(record, key)
    ]
    notes = _record_text(record, "notes", default="")
    if notes:
        detail_values.append(notes)
    detail = " · ".join(detail_values[:2])
    meta = " / ".join(value for value in (kind, risk) if value)
    return f"""
      <article class="mc-card">
        <div class="mc-card-head">
          <div>
            <code>{html.escape(record_id)}</code>
            <h3>{html.escape(name)}</h3>
          </div>
          <span class="state state-{html.escape(_mission_status_class(status))}">{html.escape(status)}</span>
        </div>
        <p>{html.escape(detail or meta or "Registry-backed record")}</p>
        <small>{html.escape(meta)}</small>
      </article>
    """


def _mission_card_grid(
    records: list[dict[str, object]],
    *,
    empty: str,
    detail_keys: tuple[str, ...] = (),
    limit: int = 12,
) -> str:
    if not records:
        return f'<div class="empty">{html.escape(empty)}</div>'
    return "\n".join(
        _mission_card(record, detail_keys=detail_keys)
        for record in records[:limit]
        if isinstance(record, dict)
    )


def _mission_primary_records(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    hidden_statuses = {"deprecated", "legacy_optional", "not_configured", "optional"}
    hidden_classifications = {"optional_legacy_adapter", "optional_integration"}
    visible = []
    for record in records:
        if not isinstance(record, dict):
            continue
        status = str(record.get("status") or "")
        classification = str(record.get("classification") or "")
        if status in hidden_statuses or classification in hidden_classifications:
            continue
        visible.append(record)
    return visible


def _mission_filter_options(records: list[dict[str, object]], key: str) -> str:
    values = sorted(
        {str(record.get(key) or "") for record in records if isinstance(record, dict)}
        - {""}
    )
    return '<option value="all">all</option>' + "".join(
        f'<option value="{html.escape(value)}">{html.escape(value)}</option>'
        for value in values
    )


def _mission_action_console_grid(records: list[dict[str, object]]) -> str:
    filters = f"""
      <div id="actionFilters" class="filter-row" aria-label="Action filters">
        <label>Risk
          <select data-action-filter="risk">{_mission_filter_options(records, "risk")}</select>
        </label>
        <label>Surface
          <select data-action-filter="surface">{_mission_filter_options(records, "surface")}</select>
        </label>
        <label>Status
          <select data-action-filter="status">{_mission_filter_options(records, "status")}</select>
        </label>
      </div>
    """
    if not records:
        return filters + '<div class="empty">No actions loaded</div>'

    cards = []
    for record in records[:80]:
        if not isinstance(record, dict):
            continue
        record_id = _record_text(record, "id", default="action")
        name = _record_text(record, "name", "title", default=record_id)
        status = _record_text(record, "status", default="unknown")
        risk = _record_text(record, "risk", default="unknown")
        surface = _record_text(record, "surface", default="unknown")
        group = _record_text(record, "group", default="ops")
        policy = _record_text(record, "execution_policy", default="disabled")
        timeout = _record_text(record, "timeout_seconds", default="")
        runnable = policy == "allowed"
        button_class = "mc-run-action" if runnable else "mc-request-action"
        button_text = "Run" if runnable else "Request approval"
        cards.append(
            f"""
            <article class="mc-card action-card"
              data-action-id="{html.escape(record_id)}"
              data-risk="{html.escape(risk)}"
              data-surface="{html.escape(surface)}"
              data-status="{html.escape(status)}">
              <div class="mc-card-head">
                <div>
                  <code>{html.escape(record_id)}</code>
                  <h3>{html.escape(name)}</h3>
                </div>
                <span class="state state-{html.escape(_mission_status_class(status))}">{html.escape(status)}</span>
              </div>
              <p>{html.escape(group)} · {html.escape(surface)} · {html.escape(policy)}</p>
              <small>{html.escape(risk)} risk{f" · {html.escape(timeout)}s" if timeout else ""}</small>
              <button type="button" class="{button_class}" data-action-id="{html.escape(record_id)}">{button_text}</button>
            </article>
            """
        )
    return filters + f'<div class="cards action-cards">{"".join(cards)}</div>'


def _mission_run_timeline_grid(records: list[dict[str, object]]) -> str:
    if not records:
        cards = '<div class="empty">No run records yet</div>'
    else:
        rendered = []
        for record in records[:24]:
            if not isinstance(record, dict):
                continue
            run_id = _record_text(record, "id", default="run")
            action_id = _record_text(record, "action_id", default="unknown")
            status = _record_text(record, "status", default="unknown")
            timestamp = _record_text(record, "timestamp", default="")
            duration = _record_text(record, "duration_ms", default="")
            exit_code = _record_text(record, "exit_code", default="")
            rendered.append(
                f"""
                <article class="mc-card run-card" data-run-id="{html.escape(run_id)}">
                  <div class="mc-card-head">
                    <div>
                      <code>{html.escape(run_id)}</code>
                      <h3>{html.escape(action_id)}</h3>
                    </div>
                    <span class="state state-{html.escape(_mission_status_class(status))}">{html.escape(status)}</span>
                  </div>
                  <p>{html.escape(timestamp or "no timestamp")} · exit {html.escape(exit_code or "unknown")}</p>
                  <small>{html.escape(duration or "0")}ms</small>
                  <button type="button" class="mc-run-detail" data-run-id="{html.escape(run_id)}">Inspect</button>
                </article>
                """
            )
        cards = f'<div class="cards run-cards">{"".join(rendered)}</div>'
    return (
        cards
        + """
        <aside id="runDetailDrawer" class="detail-drawer" hidden>
          <div class="drawer-head">
            <h3>Run Detail</h3>
            <button type="button" id="closeRunDetail">Close</button>
          </div>
          <pre id="runDetailOutput" aria-live="polite"></pre>
        </aside>
        """
    )


def _mission_action_request_grid(records: list[dict[str, object]]) -> str:
    return _mission_card_grid(
        records,
        empty="No pending action approval requests",
        detail_keys=("action_id", "requester", "reason"),
        limit=8,
    )


def _mission_action_request_dialog() -> str:
    return """
      <dialog id="actionRequestDialog">
        <form id="actionRequestForm" method="dialog">
          <h3>Action Approval Request</h3>
          <input type="hidden" id="requestActionId" name="action_id">
          <label>Reason
            <textarea id="requestReason" name="reason" rows="4" placeholder="Why should this blocked action be reviewed?"></textarea>
          </label>
          <div class="dialog-actions">
            <button type="button" id="cancelActionRequest">Cancel</button>
            <button type="submit">Submit request</button>
          </div>
          <pre id="actionRequestResult" aria-live="polite"></pre>
        </form>
      </dialog>
    """


def render_mission_control_html(
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    registry: ActionRegistry | None = None,
) -> str:
    payload = autonomous_mission_control_payload(canonical_root, registry=registry)
    overview = payload["overview"]
    sections = payload["sections"]
    summary = payload["summary"]
    queues = summary["queues"] if isinstance(summary.get("queues"), dict) else {}
    registry_counts = (
        summary["registry"] if isinstance(summary.get("registry"), dict) else {}
    )
    nav_items = (
        ("Overview", "#overview"),
        ("Action Console", "#action-console"),
        ("Inbox", "inbox"),
        ("Agents", "#agents"),
        ("Tasks / Runs", "tasks"),
        ("Run Timeline", "#run-timeline"),
        ("Skills", "#skills"),
        ("Workflows", "#workflows"),
        ("GitHub Radar", "#github-radar"),
        ("Knowledge", "#knowledge"),
        ("Integrations", "#integrations"),
        ("Observability", "#observability"),
        ("System Updates", "#updates"),
        ("Settings", "settings"),
    )
    nav = "\n".join(
        f'<a href="{html.escape(url)}">{html.escape(label)}</a>'
        for label, url in nav_items
    )
    stat_specs = (
        ("System Status", str(overview.get("system_status", "unknown"))),
        ("Hermes Agents", str(overview.get("active_hermes_agents", 0))),
        ("Inbox", str(queues.get("inbox_count", 0))),
        (
            "Tasks / Runs",
            f"{queues.get('task_count', 0)} / {queues.get('run_count', 0)}",
        ),
        ("Memory Sources", str(registry_counts.get("brain_count", 0))),
        ("Updates", str(registry_counts.get("update_candidate_count", 0))),
        ("Integrations", str(registry_counts.get("runtime_count", 0))),
        ("Warnings", str(overview.get("warnings", 0))),
    )
    stats = "\n".join(
        f"""
        <article class="metric">
          <span>{html.escape(label)}</span>
          <strong>{html.escape(value)}</strong>
        </article>
        """
        for label, value in stat_specs
    )
    agents = sections["agents"] if isinstance(sections.get("agents"), list) else []
    action_console = (
        sections["action_console"]
        if isinstance(sections.get("action_console"), list)
        else []
    )
    run_timeline = (
        sections["run_timeline"]
        if isinstance(sections.get("run_timeline"), list)
        else []
    )
    action_requests = (
        sections["action_requests"]
        if isinstance(sections.get("action_requests"), list)
        else []
    )
    brain = _mission_primary_records(
        sections["brain"] if isinstance(sections.get("brain"), list) else []
    )
    updates = _mission_primary_records(
        sections["updates"] if isinstance(sections.get("updates"), list) else []
    )
    integrations = (
        sections["integrations"]
        if isinstance(sections.get("integrations"), list)
        else []
    )
    integrations = _mission_primary_records(integrations)
    skills = _mission_primary_records(
        sections["skills"] if isinstance(sections.get("skills"), list) else []
    )
    workflows = _mission_primary_records(
        sections["workflows"] if isinstance(sections.get("workflows"), list) else []
    )
    github_radar = (
        sections["github_radar"]
        if isinstance(sections.get("github_radar"), list)
        else []
    )
    observability = (
        sections["observability"]
        if isinstance(sections.get("observability"), list)
        else []
    )
    warnings = (
        sections["warnings"] if isinstance(sections.get("warnings"), list) else []
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NERD OS Mission Control</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07090c;
      --panel: #10151d;
      --panel-2: #151b24;
      --rail: #0b0f15;
      --line: #263241;
      --text: #eef3f8;
      --muted: #93a0af;
      --ok: #42d392;
      --warn: #f0b84b;
      --bad: #ef626c;
      --blue: #72a8ff;
      --cyan: #57d5dc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .mc-shell {{
      display: grid;
      grid-template-columns: 250px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .rail {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      border-right: 1px solid var(--line);
      background: var(--rail);
      padding: 18px 14px;
    }}
    .brand {{
      display: grid;
      gap: 4px;
      margin-bottom: 18px;
    }}
    .brand strong {{
      font-size: 18px;
      letter-spacing: 0;
    }}
    .brand span, p, small {{
      color: var(--muted);
    }}
    nav {{
      display: grid;
      gap: 7px;
    }}
    nav a {{
      min-height: 36px;
      display: flex;
      align-items: center;
      border: 1px solid transparent;
      border-radius: 7px;
      color: var(--text);
      padding: 0 10px;
      text-decoration: none;
      font-size: 13px;
    }}
    nav a:hover {{
      border-color: var(--line);
      background: #111923;
    }}
    main {{
      min-width: 0;
      padding: 22px;
    }}
    .top {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: start;
      margin-bottom: 16px;
    }}
    h1, h2, h3, p {{
      margin: 0;
      letter-spacing: 0;
    }}
    h1 {{
      font-size: 26px;
      line-height: 1.15;
    }}
    h2 {{
      font-size: 16px;
      margin-bottom: 10px;
    }}
    h3 {{
      font-size: 14px;
      line-height: 1.25;
      margin-top: 6px;
    }}
    p {{
      line-height: 1.45;
      font-size: 13px;
    }}
    .top-actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: end;
    }}
    .pill, .top-actions a {{
      min-height: 32px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 7px;
      color: var(--text);
      padding: 0 10px;
      text-decoration: none;
      font-size: 12px;
      white-space: nowrap;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}
    .metric, .panel, .mc-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .metric {{
      min-height: 88px;
      padding: 12px;
      display: grid;
      align-content: space-between;
    }}
    .metric span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .metric strong {{
      font-size: 24px;
      overflow-wrap: anywhere;
    }}
    .ops-grid {{
      display: grid;
      grid-template-columns: 1.35fr .85fr;
      gap: 12px;
      align-items: start;
    }}
    .panel {{
      padding: 14px;
      min-width: 0;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 10px;
    }}
    .filter-row {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 10px;
    }}
    .filter-row label {{
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 11px;
    }}
    .filter-row select,
    #actionRequestDialog textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #0a1018;
      color: var(--text);
      padding: 9px;
      font: inherit;
    }}
    .mc-card {{
      min-height: 142px;
      padding: 12px;
      display: grid;
      gap: 10px;
      align-content: space-between;
    }}
    .mc-card button,
    .dialog-actions button,
    #closeRunDetail {{
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel-2);
      color: var(--text);
      font-weight: 700;
      cursor: pointer;
    }}
    .mc-run-action,
    .dialog-actions button[type="submit"] {{
      border-color: rgba(114, 168, 255, .55) !important;
      background: #172b48 !important;
      color: #dbe9ff !important;
    }}
    .mc-request-action {{
      border-color: rgba(240, 184, 75, .5) !important;
      background: #2b2416 !important;
      color: #f7d590 !important;
    }}
    .detail-drawer,
    #actionRequestDialog {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      padding: 12px;
    }}
    .detail-drawer {{
      margin-top: 10px;
    }}
    .drawer-head,
    .dialog-actions {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }}
    #actionRequestForm {{
      display: grid;
      gap: 10px;
      min-width: min(520px, 82vw);
    }}
    #actionRequestForm label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .mc-card-head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
    }}
    code {{
      color: var(--blue);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      overflow-wrap: anywhere;
    }}
    .state {{
      min-height: 24px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 7px;
      font-size: 11px;
      white-space: nowrap;
    }}
    .state-ok {{ color: var(--ok); border-color: rgba(66, 211, 146, .45); }}
    .state-warn {{ color: var(--warn); border-color: rgba(240, 184, 75, .45); }}
    .state-muted {{ color: var(--muted); }}
    .state-info {{ color: var(--cyan); border-color: rgba(87, 213, 220, .35); }}
    .section-stack {{
      display: grid;
      gap: 12px;
    }}
    .queue {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }}
    .queue a {{
      min-height: 72px;
      display: grid;
      align-content: center;
      gap: 4px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-2);
      color: var(--text);
      padding: 10px;
      text-decoration: none;
    }}
    .queue span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .empty {{
      min-height: 82px;
      display: grid;
      place-items: center;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      padding: 14px;
    }}
    pre {{
      max-height: 340px;
      overflow: auto;
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #05070b;
      padding: 12px;
      color: #cbd6e2;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    @media (max-width: 1080px) {{
      .mc-shell {{ grid-template-columns: 1fr; }}
      .rail {{ position: static; height: auto; }}
      nav {{ grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }}
      .ops-grid, .top {{ grid-template-columns: 1fr; }}
      .top-actions {{ justify-content: start; }}
    }}
    @media (max-width: 780px) {{
      main {{ padding: 16px; }}
      .metrics, .queue, .filter-row {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 540px) {{
      .metrics, .queue, .filter-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="mc-shell">
    <aside class="rail">
      <div class="brand">
        <strong>NERD OS</strong>
        <span>Mission Control reference: builderz-labs/mission-control</span>
      </div>
      <nav aria-label="Mission Control navigation">{nav}</nav>
    </aside>
    <main>
      <section class="top" id="overview">
        <div>
          <h1>NERD OS Mission Control</h1>
          <p>AI agent command center for Hermes agents, inbox, tasks, runs, approvals, skills, workflows, memory, integrations, updates, and operational telemetry.</p>
        </div>
        <div class="top-actions">
          <a href="brain">Brain</a>
          <a href="hermes">Hermes</a>
          <a href="updates">Updates</a>
          <a href="hermes-repair">Repair</a>
        </div>
      </section>
      <section class="metrics">{stats}</section>
      <section class="ops-grid">
        <div class="section-stack">
          <section class="panel">
            <h2>Command Queues</h2>
            <div class="queue">
              <a href="inbox"><strong>{html.escape(str(queues.get("inbox_count", 0)))}</strong><span>Inbox</span></a>
              <a href="tasks"><strong>{html.escape(str(queues.get("task_count", 0)))}</strong><span>Tasks</span></a>
              <a href="runs"><strong>{html.escape(str(queues.get("run_count", 0)))}</strong><span>Runs</span></a>
            </div>
          </section>
          <section class="panel" id="action-console">
            <h2>Action Console</h2>
            {_mission_action_console_grid(action_console)}
            <pre id="missionConsoleOutput" aria-live="polite">Ready. Runnable actions execute through /api/run; blocked actions create /api/autonomous/action-requests records.</pre>
          </section>
          <section class="panel" id="approval-requests">
            <h2>Approval Requests</h2>
            <div id="actionRequestList">{_mission_action_request_grid(action_requests)}</div>
          </section>
          <section class="panel" id="run-timeline">
            <h2>Run Timeline</h2>
            {_mission_run_timeline_grid(run_timeline)}
          </section>
          <section class="panel" id="agents">
            <h2>Agents</h2>
            <div class="cards">{_mission_card_grid(agents, empty="No Hermes agents registered", detail_keys=("department", "role", "objectives", "tools"))}</div>
          </section>
          <section class="panel" id="skills">
            <h2>Skills</h2>
            <div class="cards">{_mission_card_grid(skills, empty="Skills registry is ready for curated skill imports", detail_keys=("source", "category", "tools_required"))}</div>
          </section>
          <section class="panel" id="workflows">
            <h2>Workflows</h2>
            <div class="cards">{_mission_card_grid(workflows, empty="Workflow registry is empty", detail_keys=("source", "trigger", "approval_required"))}</div>
          </section>
          <section class="panel" id="github-radar">
            <h2>GitHub Radar</h2>
            <div class="cards">{_mission_card_grid(github_radar, empty="GitHub Radar registry is empty", detail_keys=("kind", "metadata"))}</div>
          </section>
          <section class="panel" id="knowledge">
            <h2>Knowledge</h2>
            <div class="cards">{_mission_card_grid(brain, empty="Brain registry is empty", detail_keys=("classification", "kind", "metadata"))}</div>
          </section>
        </div>
        <aside class="section-stack">
          <section class="panel" id="integrations">
            <h2>Integrations</h2>
            <div class="cards">{_mission_card_grid(integrations, empty="No runtime integrations registered", detail_keys=("classification", "metadata"))}</div>
          </section>
          <section class="panel" id="updates">
            <h2>System Updates</h2>
            <div class="cards">{_mission_card_grid(updates, empty="No update candidates", detail_keys=("current_version", "target_version", "approval_required"))}</div>
          </section>
          <section class="panel" id="observability">
            <h2>Observability</h2>
            <div class="cards">{_mission_card_grid(observability, empty="No observability records", detail_keys=("kind", "metadata"))}</div>
          </section>
          <section class="panel">
            <h2>Warnings</h2>
            <div class="cards">{_mission_card_grid(warnings, empty="No blocked or failed registry records", detail_keys=("classification", "evidence"))}</div>
          </section>
        </aside>
      </section>
    </main>
  </div>
  {_mission_action_request_dialog()}
  <script>
    const basePath = location.pathname.startsWith('/nerd-os') ? '/nerd-os' : '';
    const missionOutput = document.getElementById('missionConsoleOutput');
    const requestDialog = document.getElementById('actionRequestDialog');
    const requestForm = document.getElementById('actionRequestForm');
    const requestActionId = document.getElementById('requestActionId');
    const requestReason = document.getElementById('requestReason');
    const requestResult = document.getElementById('actionRequestResult');
    const runDrawer = document.getElementById('runDetailDrawer');
    const runDetailOutput = document.getElementById('runDetailOutput');

    function showMissionOutput(value) {{
      if (missionOutput) missionOutput.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    }}
    function appendActionRequest(record) {{
      const list = document.getElementById('actionRequestList');
      if (!list || !record) return;
      const id = record.id || 'request';
      const actionId = record.action_id || 'action';
      const status = record.status || 'approval_requested';
      list.innerHTML = `
        <div class="cards">
          <article class="mc-card">
            <div class="mc-card-head">
              <div><code>${{id}}</code><h3>${{actionId}}</h3></div>
              <span class="state state-warn">${{status}}</span>
            </div>
            <p>${{record.reason || 'Manual approval requested'}}</p>
            <small>${{record.requester || 'operator'}}</small>
          </article>
        </div>`;
    }}

    document.querySelectorAll('.mc-run-action').forEach(button => {{
      button.addEventListener('click', async () => {{
        const id = button.dataset.actionId;
        showMissionOutput(`Running ${{id}}...`);
        button.disabled = true;
        try {{
          const response = await fetch(`${{basePath}}/api/run`, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{id}})
          }});
          const data = await response.json();
          showMissionOutput(data);
        }} catch (error) {{
          showMissionOutput(String(error));
        }} finally {{
          button.disabled = false;
        }}
      }});
    }});

    document.querySelectorAll('.mc-request-action').forEach(button => {{
      button.addEventListener('click', () => {{
        requestActionId.value = button.dataset.actionId || '';
        requestReason.value = '';
        requestResult.textContent = '';
        if (requestDialog.showModal) requestDialog.showModal();
        else requestDialog.removeAttribute('hidden');
      }});
    }});

    document.getElementById('cancelActionRequest')?.addEventListener('click', () => {{
      if (requestDialog.close) requestDialog.close();
      else requestDialog.setAttribute('hidden', 'hidden');
    }});

    requestForm?.addEventListener('submit', async event => {{
      event.preventDefault();
      requestResult.textContent = 'Creating approval request...';
      try {{
        const response = await fetch(`${{basePath}}/api/autonomous/action-requests`, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{
            action_id: requestActionId.value,
            requester: 'operator',
            reason: requestReason.value.trim()
          }})
        }});
        const data = await response.json();
        requestResult.textContent = JSON.stringify(data, null, 2);
        appendActionRequest(data.request);
        showMissionOutput(data);
      }} catch (error) {{
        requestResult.textContent = String(error);
      }}
    }});

    document.querySelectorAll('.mc-run-detail').forEach(button => {{
      button.addEventListener('click', async () => {{
        const runId = button.dataset.runId;
        runDetailOutput.textContent = `Loading ${{runId}}...`;
        runDrawer.hidden = false;
        try {{
          const response = await fetch(`${{basePath}}/api/autonomous/run-detail/${{runId}}`);
          const data = await response.json();
          runDetailOutput.textContent = JSON.stringify(data, null, 2);
        }} catch (error) {{
          runDetailOutput.textContent = String(error);
        }}
      }});
    }});

    document.getElementById('closeRunDetail')?.addEventListener('click', () => {{
      runDrawer.hidden = true;
    }});

    document.querySelectorAll('[data-action-filter]').forEach(select => {{
      select.addEventListener('change', () => {{
        const filters = {{}};
        document.querySelectorAll('[data-action-filter]').forEach(active => {{
          filters[active.dataset.actionFilter] = active.value;
        }});
        document.querySelectorAll('.action-card').forEach(card => {{
          const hidden = Object.entries(filters).some(([key, value]) => value !== 'all' && card.dataset[key] !== value);
          card.hidden = hidden;
        }});
      }});
    }});
  </script>
</body>
</html>
"""


def _brain_metric_card(label: str, value: object, detail: str) -> str:
    return f"""
      <article class="brain-metric">
        <span>{html.escape(label)}</span>
        <strong>{html.escape(str(value))}</strong>
        <p>{html.escape(detail)}</p>
      </article>
    """


def _brain_source_cards(records: list[dict[str, object]]) -> str:
    if not records:
        return '<div class="empty">No DB sources have been ingested yet</div>'
    cards = []
    for record in records[:8]:
        record_id = _record_text(record, "id", default="source")
        name = _record_text(record, "name", default=record_id)
        kind = _record_text(record, "kind", default="source")
        status = _record_text(record, "status", default="active")
        updated = _record_text(record, "updated_at", default="")
        cards.append(
            f"""
            <article class="brain-source">
              <span class="pulse" aria-hidden="true"></span>
              <div>
                <code>{html.escape(record_id)}</code>
                <h3>{html.escape(name)}</h3>
                <p>{html.escape(kind)}{html.escape(f" · {updated}" if updated else "")}</p>
              </div>
              <span class="state state-{html.escape(_mission_status_class(status))}">{html.escape(status)}</span>
            </article>
            """
        )
    return "".join(cards)


def _brain_candidate_cards(records: list[dict[str, object]]) -> str:
    if not records:
        return '<div class="empty">No memory candidates have been written into the DB yet</div>'
    cards = []
    for record in records[:8]:
        record_id = _record_text(record, "id", default="candidate")
        name = _record_text(record, "name", "title", default=record_id)
        status = _record_text(record, "promotion_status", "status", default="candidate")
        risk = _record_text(record, "risk", default="unknown")
        summary = _record_text(record, "summary", default="Awaiting summary")
        task_id = _record_text(record, "task_id", default="")
        cards.append(
            f"""
            <article class="brain-candidate">
              <div class="candidate-head">
                <div>
                  <code>{html.escape(record_id)}</code>
                  <h3>{html.escape(name)}</h3>
                </div>
                <span class="state state-{html.escape(_mission_status_class(status))}">{html.escape(status)}</span>
              </div>
              <p>{html.escape(summary)}</p>
              <small>{html.escape(" / ".join(value for value in (risk, task_id) if value))}</small>
            </article>
            """
        )
    return "".join(cards)


def render_brain_html(
    registry: ActionRegistry,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> str:
    payload = autonomous_brain_payload(canonical_root)
    summary = payload["summary"] if isinstance(payload.get("summary"), dict) else {}
    store = payload["store"] if isinstance(payload.get("store"), dict) else {}
    records = _active_product_records(
        _mission_primary_records(
            payload["items"] if isinstance(payload.get("items"), list) else []
        )
    )
    candidates = _safe_record_array(store.get("recent_candidates"))
    sources = _safe_record_array(store.get("sources"))
    actions = _action_records_for_surface(registry, "brain")
    summary_json = html.escape(
        json.dumps(
            _redact_local_addresses(_surface_summary(summary)),
            ensure_ascii=False,
            indent=2,
        )
    )
    action_cards = _mission_card_grid(
        actions,
        empty="No brain actions are registered",
        detail_keys=("group", "execution_policy", "timeout_seconds"),
        limit=8,
    )
    record_cards = _mission_card_grid(
        records,
        empty="Brain registry is empty",
        detail_keys=("classification", "kind", "metadata"),
        limit=10,
    )
    metrics = "".join(
        [
            _brain_metric_card(
                "Store",
                store.get("status", "missing"),
                str(store.get("db_path") or "No DB path recorded"),
            ),
            _brain_metric_card(
                "Sources",
                store.get("source_count", 0),
                "Connected intake origins and agent surfaces.",
            ),
            _brain_metric_card(
                "Episodes",
                store.get("episode_count", 0),
                "Normalized context units available for retrieval.",
            ),
            _brain_metric_card(
                "Candidates",
                store.get("candidate_count", 0),
                "Promotable memory records awaiting review.",
            ),
            _brain_metric_card(
                "Approved",
                store.get("approved_count", 0),
                "Candidates promoted into durable knowledge.",
            ),
        ]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Autonomous Brain</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070807;
      --panel: #101512;
      --panel-2: #151b18;
      --line: #2b3932;
      --line-strong: #415248;
      --text: #f2f5f2;
      --muted: #9aa99f;
      --ok: #4ed18c;
      --warn: #f3bb4b;
      --bad: #ef626c;
      --cyan: #55d6c2;
      --blue: #72a8ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: Aptos, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    h1, h2, h3, p {{ margin: 0; letter-spacing: 0; }}
    p {{ color: var(--muted); font-size: 13px; line-height: 1.45; }}
    code {{ color: var(--blue); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; overflow-wrap: anywhere; }}
    small {{ color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }}
    .brain-shell {{
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .rail {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      border-right: 1px solid var(--line);
      background: #0b0f0d;
      padding: 18px 14px;
    }}
    .brand {{ display: grid; gap: 4px; margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid var(--line); }}
    .brand strong {{ font-size: 18px; }}
    .brand span {{ color: var(--muted); font-size: 12px; }}
    nav {{ display: grid; gap: 7px; }}
    nav a, .top-actions a {{
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 7px;
      color: var(--text);
      padding: 0 10px;
      text-decoration: none;
      font-size: 13px;
    }}
    nav a[aria-current="page"] {{ border-color: var(--line-strong); box-shadow: inset 3px 0 0 var(--cyan); }}
    main {{ min-width: 0; padding: 20px; }}
    .topbar {{
      min-height: 64px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 16px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
      margin-bottom: 16px;
    }}
    h1 {{ font-size: 25px; line-height: 1.12; }}
    h2 {{ font-size: 15px; line-height: 1.25; margin-bottom: 10px; }}
    h3 {{ font-size: 13px; line-height: 1.25; }}
    .top-actions {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: end; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}
    .brain-metric, .panel, .brain-source, .brain-candidate {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .brain-metric {{
      min-height: 104px;
      display: grid;
      align-content: space-between;
      gap: 8px;
      padding: 12px;
    }}
    .brain-metric span {{ color: var(--muted); font-size: 12px; }}
    .brain-metric strong {{ font-size: 22px; overflow-wrap: anywhere; }}
    .workspace {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 12px;
      align-items: start;
    }}
    .stack {{ display: grid; gap: 12px; }}
    .panel {{ padding: 14px; min-width: 0; }}
    .brain-flow {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
    }}
    .flow-node {{
      position: relative;
      min-height: 112px;
      display: grid;
      align-content: start;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-2);
      padding: 12px;
    }}
    .flow-node span {{
      width: 30px;
      height: 28px;
      display: grid;
      place-items: center;
      border: 1px solid rgba(85, 214, 194, .45);
      border-radius: 7px;
      color: var(--cyan);
      font-size: 11px;
      font-weight: 700;
    }}
    .flow-node:not(:last-child)::after {{
      content: "";
      position: absolute;
      top: 26px;
      right: -10px;
      width: 10px;
      height: 1px;
      background: var(--line-strong);
    }}
    .brain-intake {{
      display: grid;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }}
    .brain-intake textarea, .brain-intake input {{
      width: 100%;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #070a09;
      color: var(--text);
      padding: 9px 10px;
      font: inherit;
    }}
    .brain-intake textarea {{ min-height: 110px; resize: vertical; }}
    .form-row {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }}
    button {{
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel-2);
      color: var(--text);
      font-weight: 700;
      cursor: pointer;
      padding: 0 12px;
    }}
    button:disabled {{ opacity: .6; cursor: not-allowed; }}
    .source-list, .candidate-list, .cards {{ display: grid; gap: 10px; }}
    .brain-source {{
      min-height: 76px;
      display: grid;
      grid-template-columns: 12px minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      padding: 10px;
    }}
    .pulse {{
      width: 10px;
      height: 10px;
      margin-top: 6px;
      border-radius: 50%;
      background: var(--ok);
      box-shadow: 0 0 0 4px rgba(78, 209, 140, .08);
    }}
    .brain-candidate {{
      min-height: 134px;
      display: grid;
      align-content: space-between;
      gap: 10px;
      padding: 12px;
    }}
    .candidate-head, .mc-card-head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
    }}
    .state {{
      min-height: 24px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 7px;
      font-size: 11px;
      white-space: nowrap;
    }}
    .state-ok {{ color: var(--ok); border-color: rgba(78, 209, 140, .45); }}
    .state-warn {{ color: var(--warn); border-color: rgba(243, 187, 75, .45); }}
    .state-muted {{ color: var(--muted); }}
    .state-info {{ color: var(--cyan); border-color: rgba(85, 214, 194, .35); }}
    .mc-card {{
      min-height: 126px;
      display: grid;
      align-content: space-between;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }}
    .empty {{
      min-height: 86px;
      display: grid;
      place-items: center;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      padding: 14px;
      text-align: center;
    }}
    pre {{
      max-height: 360px;
      overflow: auto;
      margin: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #05070a;
      color: var(--muted);
      padding: 10px;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    @media (max-width: 1180px) {{
      .workspace {{ grid-template-columns: 1fr; }}
      .metrics {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    }}
    @media (max-width: 920px) {{
      .brain-shell {{ grid-template-columns: 1fr; }}
      .rail {{ position: static; height: auto; }}
      nav {{ grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }}
      .brain-flow {{ grid-template-columns: 1fr; }}
      .flow-node::after {{ display: none; }}
    }}
    @media (max-width: 680px) {{
      main {{ padding: 14px; }}
      .topbar, .form-row {{ grid-template-columns: 1fr; }}
      .top-actions {{ justify-content: start; }}
      .metrics {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="brain-shell">
    <aside class="rail">
      <div class="brand">
        <strong>NERD OS</strong>
        <span>Second Brain</span>
      </div>
      <nav aria-label="Brain navigation">
        <a href="mission-control">Mission Control</a>
        <a href="brain" aria-current="page">Brain</a>
        <a href="inbox">Inbox</a>
        <a href="tasks">Tasks</a>
        <a href="approvals">Approvals</a>
        <a href="registry">Registry</a>
        <a href="runtimes">Runtimes</a>
      </nav>
    </aside>
    <main>
      <header class="topbar">
        <div>
          <p>Autonomous Brain</p>
          <h1>NERD OS Second Brain</h1>
        </div>
        <div class="top-actions">
          <a href="mission-control">Mission Control</a>
          <a href="/api/autonomous/brain">API</a>
          <a href="/api/autonomous/brain-store">Store</a>
        </div>
      </header>
      <section class="metrics">{metrics}</section>
      <section class="workspace">
        <div class="stack">
          <section class="panel">
            <h2>Context Flow</h2>
            <div class="brain-flow" aria-label="Second brain context flow">
              <article class="flow-node"><span>01</span><h3>Capture</h3><p>Operator, Telegram, n8n, files, repos, and agent notes.</p></article>
              <article class="flow-node"><span>02</span><h3>Normalize</h3><p>Risk, privacy, source, task route, and candidate summary.</p></article>
              <article class="flow-node"><span>03</span><h3>Store</h3><p>SQLite-backed canonical DB with JSON registry mirrors.</p></article>
              <article class="flow-node"><span>04</span><h3>Retrieve</h3><p>FTS-ready records for agents, UI, and future MCP access.</p></article>
              <article class="flow-node"><span>05</span><h3>Context Pack</h3><p>Promoted knowledge feeds every AI layer without losing state.</p></article>
            </div>
          </section>
          <section class="panel">
            <h2>Brain Intake</h2>
            <form id="brainIntakeForm" class="brain-intake">
              <textarea id="brainText" name="text" placeholder="Capture a memory, decision, repo signal, architecture note, research lead, or operating context."></textarea>
              <div class="form-row">
                <input id="brainSource" name="source" value="brain" aria-label="Brain intake source">
                <button type="submit">Capture Memory</button>
              </div>
              <pre id="brainIntakeResult" aria-live="polite">Ready. Records write to /api/autonomous/brain and mirror into the brain store.</pre>
            </form>
          </section>
          <section class="panel">
            <h2>Recent Candidates</h2>
            <div class="candidate-list">{_brain_candidate_cards(candidates)}</div>
          </section>
          <section class="panel">
            <h2>Canonical Memory Records</h2>
            <div class="cards">{record_cards}</div>
          </section>
        </div>
        <aside class="stack">
          <section class="panel">
            <h2>Sources</h2>
            <div class="source-list">{_brain_source_cards(sources)}</div>
          </section>
          <section class="panel">
            <h2>Brain Actions</h2>
            <div class="cards">{action_cards}</div>
          </section>
          <section class="panel">
            <h2>Registry Mirror</h2>
            <pre>{summary_json}</pre>
          </section>
        </aside>
      </section>
    </main>
  </div>
  <script>
    const form = document.getElementById('brainIntakeForm');
    const result = document.getElementById('brainIntakeResult');
    const basePath = location.pathname.startsWith('/nerd-os') ? '/nerd-os' : '';
    form?.addEventListener('submit', async event => {{
      event.preventDefault();
      const text = document.getElementById('brainText').value.trim();
      const source = document.getElementById('brainSource').value.trim() || 'brain';
      if (!text) {{
        result.textContent = 'Memory text is required.';
        return;
      }}
      result.textContent = 'Capturing memory...';
      try {{
        const response = await fetch(`${{basePath}}/api/autonomous/brain`, {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify({{text, source}})
        }});
        const data = await response.json();
        result.textContent = JSON.stringify(data, null, 2);
      }} catch (error) {{
        result.textContent = String(error);
      }}
    }});
  </script>
</body>
</html>
"""


def render_surface_html(
    surface: str,
    registry: ActionRegistry,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> str:
    label_by_surface = {surface_id: label for label, surface_id in OS_NAV_ITEMS}
    title = f"NERD OS {label_by_surface.get(surface, _surface_label(surface))}"
    payload = autonomous_registry_payload(canonical_root)
    records = _action_records_for_surface(registry, surface)
    if surface == "automations":
        records.extend(payload["workflows"])  # type: ignore[arg-type]
    elif surface == "brain":
        records.extend(payload["brain_memory"])  # type: ignore[arg-type]
    elif surface == "hermes":
        records.extend(payload["hermes_agents"])  # type: ignore[arg-type]
    elif surface == "hermes_repair":
        records.extend(payload["hermes_repair"])  # type: ignore[arg-type]
    elif surface == "runtimes":
        records.extend(payload["runtime_integrations"])  # type: ignore[arg-type]
    elif surface == "models":
        records.extend(
            [
                item
                for item in payload["runtime_integrations"]  # type: ignore[index]
                if isinstance(item, dict)
                and str(item.get("kind"))
                in {"model_gateway", "local_llm_runtime", "model_router"}
            ]
        )
        records.extend(payload["models"])  # type: ignore[arg-type]
    elif surface == "agents":
        records.extend(payload["departments"])  # type: ignore[arg-type]
        records.extend(payload["agents"])  # type: ignore[arg-type]
        records.extend(payload["hermes_agents"])  # type: ignore[arg-type]
    elif surface == "memory":
        records.extend(payload["tools"])  # type: ignore[arg-type]
        records.extend(payload["brain_memory"])  # type: ignore[arg-type]
    elif surface == "updates":
        records.extend(payload["update_candidates"])  # type: ignore[arg-type]
    elif surface == "skills":
        records.extend(payload["skills"])  # type: ignore[arg-type]
    elif surface == "workflows_registry":
        records.extend(payload["workflows_registry"])  # type: ignore[arg-type]
    elif surface == "integrations":
        records.extend(payload["runtime_integrations"])  # type: ignore[arg-type]
    elif surface == "github":
        records.extend(payload["github_radar"])  # type: ignore[arg-type]
    elif surface == "observability":
        records.extend(payload["observability"])  # type: ignore[arg-type]
    elif surface == "lab":
        records.extend(
            [
                item
                for item in payload["existing_work"]  # type: ignore[index]
                if isinstance(item, dict)
                and (item.get("risk") == "high" or item.get("domain") == "lab")
            ]
        )
    return render_autonomous_records_html(
        title=title,
        description="Domain-accessible NERD OS surface backed by canonical records and gated actions.",
        records=records,
        summary=payload["summary"],  # type: ignore[arg-type]
    )


def render_autonomous_records_html(
    *,
    title: str,
    description: str,
    records: list[dict[str, object]],
    summary: dict[str, object],
) -> str:
    records = _active_product_records(records)
    summary_json = html.escape(
        json.dumps(
            _redact_local_addresses(_surface_summary(summary)),
            ensure_ascii=False,
            indent=2,
        )
    )
    rows = _render_record_rows(records)
    intake_form = ""
    if title == "Autonomous Inbox":
        intake_form = """
      <form id="inboxForm" class="intake-form">
        <label>Manual intake
          <textarea id="inboxText" name="text" rows="4" placeholder="Paste a repo, link, task, idea, or note"></textarea>
        </label>
        <div class="form-row">
          <label>Source
            <input id="inboxSource" name="source" value="web">
          </label>
          <button type="submit">Create Draft Task</button>
        </div>
        <pre id="inboxResult" aria-live="polite"></pre>
      </form>
        """
    if title == "Autonomous Approvals":
        intake_form = """
      <form id="approvalForm" class="intake-form">
        <label>Task ID
          <input id="approvalTaskId" name="task_id" placeholder="task_20260524_000001">
        </label>
        <div class="form-row">
          <label>Decision
            <select id="approvalDecision" name="decision">
              <option value="approve">approve</option>
              <option value="reject">reject</option>
            </select>
          </label>
          <label>Reviewer
            <input id="approvalReviewer" name="reviewer" value="operator">
          </label>
        </div>
        <label>Reason
          <textarea id="approvalReason" name="reason" rows="3" placeholder="Decision context"></textarea>
        </label>
        <div class="form-row">
          <span>/api/autonomous/approvals</span>
          <button type="submit">Record Decision</button>
        </div>
        <pre id="approvalResult" aria-live="polite"></pre>
      </form>
        """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08090b;
      --panel: #10151c;
      --line: #2c3745;
      --text: #f1f5f9;
      --muted: #9ba8b7;
      --blue: #6ea8fe;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .wrap {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 22px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 14px;
      margin-bottom: 16px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      letter-spacing: 0;
    }}
    p {{
      margin: 6px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    nav {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    a {{
      min-height: 34px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 7px;
      color: var(--text);
      padding: 0 10px;
      text-decoration: none;
      white-space: nowrap;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 12px;
      align-items: start;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      overflow: hidden;
    }}
    .intake-form {{
      display: grid;
      gap: 10px;
      margin-bottom: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }}
    .intake-form label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .intake-form textarea,
    .intake-form input,
    .intake-form select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #0a1018;
      color: var(--text);
      padding: 10px;
      font: inherit;
    }}
    .form-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: end;
    }}
    .form-row button {{
      min-height: 38px;
      border: 0;
      border-radius: 7px;
      background: var(--blue);
      color: #06101f;
      font-weight: 700;
      padding: 0 12px;
      cursor: pointer;
    }}
    .intake-form pre {{
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #05070b;
      padding: 10px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
      font-size: 13px;
    }}
    th {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    code {{
      color: var(--blue);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    aside {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      header {{ display: grid; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>{html.escape(title)}</h1>
        <p>{html.escape(description)}</p>
      </div>
      <nav>
        <a href="/">Command Center</a>
        <a href="inbox">Inbox</a>
        <a href="tasks">Tasks</a>
        <a href="approvals">Approvals</a>
        <a href="brain">Brain</a>
        <a href="hermes">Hermes</a>
        <a href="hermes-repair">Hermes Repair</a>
        <a href="updates">Updates</a>
        <a href="runs">Runs</a>
        <a href="registry">Registry</a>
      </nav>
    </header>
    <section class="layout">
      <main>
        {intake_form}
        <table>
          <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Risk</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </main>
      <aside>
        <pre>{summary_json}</pre>
      </aside>
    </section>
  </div>
  <script>
    const form = document.getElementById('inboxForm');
    if (form) {{
      const result = document.getElementById('inboxResult');
      const basePath = location.pathname.startsWith('/nerd-os') ? '/nerd-os' : '';
      form.addEventListener('submit', async event => {{
        event.preventDefault();
        result.textContent = 'Creating draft task...';
        const text = document.getElementById('inboxText').value.trim();
        const source = document.getElementById('inboxSource').value.trim() || 'web';
        try {{
          const response = await fetch(`${{basePath}}/api/autonomous/inbox`, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{text, source}})
          }});
          const data = await response.json();
          result.textContent = JSON.stringify(data, null, 2);
        }} catch (error) {{
          result.textContent = String(error);
        }}
      }});
    }}
    const approvalForm = document.getElementById('approvalForm');
    if (approvalForm) {{
      const result = document.getElementById('approvalResult');
      const basePath = location.pathname.startsWith('/nerd-os') ? '/nerd-os' : '';
      approvalForm.addEventListener('submit', async event => {{
        event.preventDefault();
        result.textContent = 'Recording decision...';
        const task_id = document.getElementById('approvalTaskId').value.trim();
        const decision = document.getElementById('approvalDecision').value;
        const reviewer = document.getElementById('approvalReviewer').value.trim() || 'operator';
        const reason = document.getElementById('approvalReason').value.trim();
        try {{
          const response = await fetch(`${{basePath}}/api/autonomous/approvals`, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{task_id, decision, reviewer, reason}})
          }});
          const data = await response.json();
          result.textContent = JSON.stringify(data, null, 2);
        }} catch (error) {{
          result.textContent = String(error);
        }}
      }});
    }}
  </script>
</body>
</html>
"""


def _git_output(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _remote_repo_name(url: str) -> str:
    cleaned = url.strip()
    if not cleaned or cleaned in {"DISABLED", "no_push"}:
        return ""
    cleaned = cleaned.removesuffix(".git")
    patterns = (
        r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)$",
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+)$",
        r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    return ""


def _count_lines(value: str) -> int:
    return len([line for line in value.splitlines() if line.strip()])


def git_status_summary(repo_path: Path = DEFAULT_GIT_REPO_PATH) -> dict[str, object]:
    branch = _git_output(repo_path, "branch", "--show-current")
    origin_fetch_url = _git_output(repo_path, "remote", "get-url", "origin")
    origin_push_url = _git_output(repo_path, "remote", "get-url", "--push", "origin")
    upstream_fetch_url = _git_output(repo_path, "remote", "get-url", "upstream")
    upstream_push_url = _git_output(
        repo_path, "remote", "get-url", "--push", "upstream"
    )
    tracking_branch = _git_output(
        repo_path,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
    )
    unpushed = _git_output(repo_path, "rev-list", "--count", "@{u}..HEAD")
    dirty = _git_output(repo_path, "status", "--porcelain")
    upstream_push_protected = upstream_push_url in {"", "DISABLED", "no_push"}
    return {
        "repo_path": str(repo_path),
        "branch": branch,
        "tracking_branch": tracking_branch,
        "canonical_repo": _remote_repo_name(origin_push_url or origin_fetch_url),
        "origin_fetch_url": origin_fetch_url,
        "origin_push_url": origin_push_url,
        "upstream_fetch_url": upstream_fetch_url,
        "upstream_push_url": upstream_push_url,
        "dirty_count": _count_lines(dirty),
        "unpushed_commits": int(unpushed) if unpushed.isdigit() else 0,
        "last_commit": _git_output(repo_path, "rev-parse", "--short", "HEAD"),
        "upstream_push_protected": upstream_push_protected,
    }


def render_blueprint_html(registry: ActionRegistry) -> str:
    surfaces = registry.surfaces()
    groups = registry.groups()
    surface_cards = "\n".join(
        f"""
        <article class="node">
          <p>{html.escape(_surface_label(surface))}</p>
          <strong>{len(action_ids)} modules</strong>
          <span>{html.escape(", ".join(action_ids[:3]))}</span>
        </article>
        """
        for surface, action_ids in surfaces.items()
    )
    group_cards = "\n".join(
        f"""
        <article class="node compact">
          <p>{html.escape(group)}</p>
          <strong>{len(action_ids)}</strong>
          <span>{html.escape(", ".join(action_ids))}</span>
        </article>
        """
        for group, action_ids in groups.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NERD OS Blueprint</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08090b;
      --panel: #11151b;
      --panel-2: #171d24;
      --line: #303844;
      --text: #f3f6f9;
      --muted: #9aa4b2;
      --green: #42d17f;
      --amber: #ddb04a;
      --blue: #6ea8fe;
      --pink: #ec7aa8;
      --cyan: #63d4dc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .wrap {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 18px;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 28px;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    a {{
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 9px 12px;
      text-decoration: none;
      white-space: nowrap;
    }}
    .map {{
      display: grid;
      grid-template-columns: 1.1fr 1.3fr 1.1fr;
      gap: 14px;
      align-items: stretch;
    }}
    .layer {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
      min-height: 180px;
    }}
    .layer h2 {{
      margin: 0 0 12px;
      font-size: 15px;
      letter-spacing: 0;
    }}
    .stack {{
      display: grid;
      gap: 10px;
    }}
    .node {{
      min-height: 92px;
      display: grid;
      gap: 6px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel-2);
    }}
    .node p {{
      color: var(--blue);
      font-size: 12px;
    }}
    .node strong {{
      font-size: 15px;
    }}
    .node span {{
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .compact {{
      min-height: 72px;
    }}
    .brain {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      border-color: rgba(66, 209, 127, .5);
    }}
    .brain .node p {{ color: var(--green); }}
    .entry .node p {{ color: var(--cyan); }}
    .tools .node p {{ color: var(--blue); }}
    .automation .node p {{ color: var(--amber); }}
    .observability .node p {{ color: var(--pink); }}
    .wide {{
      grid-column: 1 / -1;
    }}
    .flow {{
      margin-top: 14px;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
    }}
    .flow span {{
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 10px;
      color: var(--muted);
      background: #0d1117;
      text-align: center;
      font-size: 12px;
    }}
    @media (max-width: 980px) {{
      .map, .brain, .flow {{ grid-template-columns: 1fr; }}
      header {{ display: grid; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>NERD OS Blueprint</h1>
        <p>One operational shell for ClaudeCore, automation, shared memory, GitInspired modules, CMS commerce, data work, and observability.</p>
      </div>
      <a href="/">Command Center</a>
    </header>
    <section class="map">
      <section class="layer entry">
        <h2>Entry Points</h2>
        <div class="stack">
          <article class="node"><p>Public UI</p><strong>NERD OS Mission Control</strong><span>agency.umanoff-analytics.space</span></article>
          <article class="node"><p>CLI</p><strong>free-claude / nerd-os</strong><span>server and future Mac node</span></article>
        </div>
      </section>
      <section class="layer brain">
        <div>
          <h2>Shared Brain</h2>
          <p>Single durable memory layer used by every entry point.</p>
        </div>
        <article class="node"><p>Inventory</p><strong>NERD-METHOD reports</strong><span>services, repos, skills, source cache</span></article>
        <article class="node"><p>Knowledge</p><strong>NERD OS knowledge</strong><span>reviewed memory, docs, and manifests</span></article>
        <article class="node"><p>Vault</p><strong>Obsidian / NotebookLM</strong><span>notes, reports, prompt library</span></article>
        <article class="node"><p>Code Memory</p><strong>GitNexus / CodeGraph</strong><span>symbol graph, impact, traces</span></article>
      </section>
      <section class="layer observability">
        <h2>Observability</h2>
        <div class="stack">
          <article class="node"><p>Traces</p><strong>Langfuse</strong><span>LLM and agent execution traces</span></article>
          <article class="node"><p>Ops</p><strong>Grafana / Loki / Uptime Kuma</strong><span>logs, metrics, uptime</span></article>
        </div>
      </section>
      <section class="layer tools wide">
        <h2>Tool Mesh</h2>
        <div class="flow">
          <span>LiteLLM / Ollama / providers</span>
          <span>NERD-CLAUDE-free</span>
          <span>GitInspired source cache</span>
          <span>CMS commerce modules</span>
          <span>Data and browser modules</span>
        </div>
      </section>
      <section class="layer automation wide">
        <h2>Automation Fabric</h2>
        <div class="flow">
          <span>n8n workflows</span>
          <span>MCP / OpenAPI gates</span>
          <span>risk policy</span>
          <span>run history</span>
          <span>kill switches</span>
        </div>
      </section>
      <section class="layer wide">
        <h2>Current Control Surfaces</h2>
        <div class="flow">{surface_cards}</div>
      </section>
      <section class="layer wide">
        <h2>Action Groups</h2>
        <div class="flow">{group_cards}</div>
      </section>
    </section>
  </div>
</body>
</html>
"""


def render_office_html(registry: ActionRegistry) -> str:
    groups = registry.groups()
    actions = {action.id: action for action in registry.actions()}
    department_specs = [
        (
            "Strategy Room",
            "core_ops",
            "Mission planning, policy gates, operator handoffs",
            "Director",
        ),
        (
            "Automation Bay",
            "automation_ops",
            "Allowlisted workflows, repeatable runs, guarded execution",
            "Automation Lead",
        ),
        (
            "Memory Desk",
            "memory_ops",
            "Knowledge capture, prompt records, source inventory",
            "Memory Steward",
        ),
        (
            "Build Studio",
            "build_ops",
            "Repos, site generation, CMS and commerce delivery",
            "Builder",
        ),
        (
            "Observability Wall",
            "observability_ops",
            "Traces, health, logs, uptime and run history",
            "Ops Watch",
        ),
        (
            "Lab",
            "lab",
            "Experimental modules visible with blocked controls",
            "Researcher",
        ),
    ]
    assigned_ids = {
        action_id
        for _, group, _, _ in department_specs
        for action_id in groups.get(group, [])
    }
    fallback_ids = [
        action.id for action in registry.actions() if action.id not in assigned_ids
    ]
    rooms = []
    for title, group, summary, role in department_specs:
        action_ids = groups.get(group, [])
        if title == "Lab":
            action_ids = action_ids + fallback_ids
        visible_ids = action_ids[:3]
        modules = ", ".join(visible_ids) if visible_ids else "standing by"
        status = "active" if visible_ids else "idle"
        risk = "low"
        if visible_ids:
            visible_actions = [actions[action_id] for action_id in visible_ids]
            if any(action.risk == "high" for action in visible_actions):
                risk = "high"
            elif any(action.risk == "medium" for action in visible_actions):
                risk = "medium"
        rooms.append(
            f"""
            <article class="room room-{html.escape(risk)}">
              <div class="room-head">
                <span class="avatar" aria-hidden="true"></span>
                <div>
                  <p>{html.escape(role)}</p>
                  <h2>{html.escape(title)}</h2>
                </div>
                <strong>{html.escape(status)}</strong>
              </div>
              <p class="summary">{html.escape(summary)}</p>
              <div class="module-strip">{html.escape(modules)}</div>
            </article>
            """
        )
    lane_ids = [action.id for action in registry.actions()[:6]]
    lanes = "\n".join(
        f"""
        <li>
          <span>{html.escape(action_id)}</span>
          <div class="track"><i style="--delay:{index}s"></i></div>
        </li>
        """
        for index, action_id in enumerate(lane_ids)
    )
    if not lanes:
        lanes = '<li><span>agency_idle</span><div class="track"><i></i></div></li>'
    rooms_html = "\n".join(rooms)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NERD OS Office</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080a0d;
      --panel: #10151c;
      --panel-2: #151c25;
      --line: #2c3745;
      --text: #f1f5f9;
      --muted: #9ba8b7;
      --green: #46d37f;
      --amber: #dfb34d;
      --red: #ee6570;
      --blue: #6ea8fe;
      --cyan: #63d4dc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .wrap {{
      max-width: 1420px;
      margin: 0 auto;
      padding: 22px;
    }}
    header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: 26px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0;
      font-size: 15px;
      line-height: 1.25;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    a {{
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 7px;
      color: var(--text);
      padding: 0 11px;
      text-decoration: none;
      white-space: nowrap;
    }}
    .office {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 12px;
    }}
    .rooms {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .room, .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      min-width: 0;
    }}
    .room {{
      min-height: 176px;
      padding: 13px;
      display: grid;
      align-content: space-between;
      gap: 12px;
    }}
    .room-head {{
      display: grid;
      grid-template-columns: 34px minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
    }}
    .room-head p {{
      color: var(--blue);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .room-head strong {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 4px 7px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 600;
    }}
    .avatar {{
      width: 34px;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel-2);
      position: relative;
    }}
    .avatar::before {{
      content: "";
      position: absolute;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--green);
      top: 7px;
      left: 11px;
      animation: pulse 2.6s ease-in-out infinite;
    }}
    .avatar::after {{
      content: "";
      position: absolute;
      width: 18px;
      height: 8px;
      border-radius: 7px 7px 3px 3px;
      background: #243145;
      bottom: 7px;
      left: 7px;
    }}
    .summary {{
      font-size: 12px;
    }}
    .module-strip {{
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px;
      color: var(--muted);
      background: #0b1017;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .room-low .room-head strong {{ color: var(--green); border-color: rgba(70, 211, 127, .45); }}
    .room-medium .room-head strong {{ color: var(--amber); border-color: rgba(223, 179, 77, .45); }}
    .room-high .room-head strong {{ color: var(--red); border-color: rgba(238, 101, 112, .45); }}
    .side {{
      display: grid;
      gap: 12px;
      align-content: start;
    }}
    .panel {{
      padding: 14px;
    }}
    .panel h2 {{
      margin-bottom: 10px;
    }}
    .lanes {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 9px;
    }}
    .lanes li {{
      display: grid;
      grid-template-columns: minmax(92px, 1fr) 1.4fr;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
    }}
    .lanes span {{
      overflow-wrap: anywhere;
    }}
    .track {{
      height: 12px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #090d13;
      overflow: hidden;
      position: relative;
    }}
    .track i {{
      position: absolute;
      top: 2px;
      left: 3px;
      width: 28px;
      height: 6px;
      border-radius: 6px;
      background: var(--cyan);
      animation: move 4.8s linear infinite;
      animation-delay: calc(var(--delay, 0) * -.45);
    }}
    .connections {{
      display: grid;
      gap: 8px;
    }}
    .connection {{
      display: grid;
      grid-template-columns: 10px minmax(0, 1fr);
      gap: 9px;
      align-items: start;
      padding: 9px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel-2);
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }}
    .dot {{
      width: 10px;
      height: 10px;
      margin-top: 4px;
      border-radius: 50%;
      background: var(--blue);
    }}
    @keyframes move {{
      from {{ transform: translateX(-34px); }}
      to {{ transform: translateX(240px); }}
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: .5; }}
      50% {{ opacity: 1; }}
    }}
    @media (max-width: 1080px) {{
      .office {{ grid-template-columns: 1fr; }}
      .rooms {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 680px) {{
      .wrap {{ padding: 16px; }}
      header {{ display: grid; }}
      .rooms {{ grid-template-columns: 1fr; }}
      .lanes li {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>NERD OS Office</h1>
        <p>Virtual Office for an autonomous AI agency: visible roles, working rooms, live lanes, memory, automation, and observability links.</p>
      </div>
      <a href="/">Command Center</a>
    </header>
    <section class="office" aria-label="Virtual Office">
      <main class="rooms">
        {rooms_html}
      </main>
      <aside class="side">
        <section class="panel">
          <h2>Agent activity lanes</h2>
          <ul class="lanes">{lanes}</ul>
        </section>
        <section class="panel">
          <h2>Agency connections</h2>
          <div class="connections">
            <div class="connection"><span class="dot"></span><span>Memory feeds role context, prompts, source inventory, and run reports back into each room.</span></div>
            <div class="connection"><span class="dot"></span><span>Automation gates move approved work from planning into repeatable n8n and runner actions.</span></div>
            <div class="connection"><span class="dot"></span><span>Observability connects traces, health, logs, and recent runs so agents stay inspectable.</span></div>
          </div>
        </section>
      </aside>
    </section>
  </div>
</body>
</html>
"""


def render_dashboard_html(registry: ActionRegistry) -> str:
    surfaces = registry.surfaces()
    surface_counts = {
        surface: len(action_ids) for surface, action_ids in surfaces.items()
    }
    actions = {action.id: action for action in registry.actions()}
    nav = "\n".join(
        f'<a class="surface-tab" href="{html.escape(_surface_route(surface))}" '
        f'data-surface="{html.escape(surface)}">'
        f"{html.escape(label)}"
        f"<span>{surface_counts.get(surface, 0)}</span></a>"
        for label, surface in OS_NAV_ITEMS
    )
    service_links = "\n".join(
        f"""
        <a class="service-link" href="{html.escape(link["url"])}">
          <strong>{html.escape(link["label"])}</strong>
          <span>{html.escape(link["description"])}</span>
        </a>
        """
        for link in public_service_links()
    )
    cards = []
    for surface, action_ids in surfaces.items():
        for action_id in action_ids:
            action = actions[action_id]
            cards.append(
                f"""
                <article class="module-card" data-surface="{html.escape(surface)}">
                  <div>
                    <p class="eyebrow">{html.escape(action.group)}</p>
                    <h2>{html.escape(action.display_name)}</h2>
                    <p class="action-id">{html.escape(action.id)}</p>
                  </div>
                  <div class="module-meta">
                    <span class="pill risk-{html.escape(action.risk)}">{html.escape(action.risk)}</span>
                    <span class="pill mode-{html.escape(action.auto_mode)}">{html.escape(action.auto_mode)}</span>
                    <span class="pill">{action.timeout_seconds}s</span>
                  </div>
                  <button class="run-button" data-action="{html.escape(action.id)}"
                    {"disabled" if action.auto_mode != "allowed" else ""}>
                    {"Blocked" if action.auto_mode != "allowed" else "Run"}
                  </button>
                </article>
                """
            )
    cards_html = "\n".join(cards)
    initial_payload = json.dumps(action_summary(registry), ensure_ascii=False)
    try:
        git_payload = git_status_summary()
    except OSError as exc:
        git_payload = {"error": str(exc)}
    escaped_payload = html.escape(initial_payload)
    escaped_git_payload = html.escape(json.dumps(git_payload, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NERD OS</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07090d;
      --panel: #101620;
      --panel-2: #151d2a;
      --line: #263245;
      --text: #eef3fb;
      --muted: #8b99ad;
      --green: #41d392;
      --amber: #e3b341;
      --red: #ef626c;
      --blue: #6ea8fe;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .shell {{
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr) 420px;
      min-height: 100vh;
    }}
    aside, main, .console {{
      border-right: 1px solid var(--line);
    }}
    aside {{
      padding: 20px 16px;
      background: #080d13;
    }}
    .brand {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-bottom: 24px;
    }}
    .brand strong {{ font-size: 18px; }}
    .brand span {{ color: var(--muted); font-size: 12px; }}
    .nav-kicker {{
      margin: 18px 0 8px;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .surface-tab {{
      width: 100%;
      min-height: 40px;
      margin-bottom: 8px;
      padding: 0 10px;
      border: 1px solid var(--line);
      background: transparent;
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-radius: 7px;
      cursor: pointer;
      text-align: left;
      text-decoration: none;
    }}
    .surface-tab.active {{
      border-color: var(--blue);
      background: #13233a;
    }}
    main {{
      min-width: 0;
      padding: 22px;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      letter-spacing: 0;
    }}
    .status-row {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .command-bar {{
      display: grid;
      grid-template-columns: minmax(220px, 1.4fr) repeat(3, minmax(130px, .55fr)) auto;
      gap: 8px;
      margin-bottom: 14px;
      align-items: center;
    }}
    .command-bar label {{
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 11px;
    }}
    .command-bar input,
    .command-bar select {{
      min-height: 36px;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #0a1018;
      color: var(--text);
      padding: 0 10px;
    }}
    .launcher {{
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      color: var(--text);
      background: var(--panel-2);
      font-weight: 700;
    }}
    .service-launcher {{
      margin-bottom: 14px;
      display: grid;
      gap: 8px;
    }}
    .service-launcher h2 {{
      font-size: 13px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    .service-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 8px;
    }}
    .service-link {{
      min-height: 58px;
      display: grid;
      gap: 4px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0a1018;
      color: var(--text);
      text-decoration: none;
      overflow-wrap: anywhere;
    }}
    .service-link span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .link-pill {{
      text-decoration: none;
    }}
    .risk-low, .mode-allowed {{ color: var(--green); border-color: rgba(65, 211, 146, .45); }}
    .risk-medium {{ color: var(--amber); border-color: rgba(227, 179, 65, .45); }}
    .risk-high, .mode-disabled {{ color: var(--red); border-color: rgba(239, 98, 108, .45); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
      gap: 12px;
    }}
    .module-card {{
      min-height: 178px;
      padding: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 14px;
    }}
    .eyebrow {{
      margin: 0 0 6px;
      color: var(--blue);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0;
      font-size: 16px;
      letter-spacing: 0;
      line-height: 1.25;
    }}
    .action-id {{
      margin: 8px 0 0;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .module-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .run-button {{
      height: 38px;
      border: 0;
      border-radius: 7px;
      background: var(--blue);
      color: #06101f;
      font-weight: 700;
      cursor: pointer;
    }}
    .run-button:disabled {{
      background: #2b3341;
      color: #9ba6b8;
      cursor: not-allowed;
    }}
    .console {{
      padding: 22px;
      background: #090d14;
      min-width: 0;
    }}
    .console h2 {{
      font-size: 15px;
      margin-bottom: 12px;
    }}
    .ops-panels {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .ops-panel {{
      min-height: 116px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }}
    .ops-panel h3 {{
      margin: 0 0 8px;
      font-size: 13px;
      letter-spacing: 0;
    }}
    .ops-panel p {{
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }}
    .history {{
      margin-top: 14px;
      display: grid;
      gap: 8px;
    }}
    .history-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel);
      color: var(--muted);
      font-size: 12px;
    }}
    .history-row strong {{
      color: var(--text);
      overflow-wrap: anywhere;
    }}
    pre {{
      min-height: 420px;
      max-height: calc(100vh - 120px);
      overflow: auto;
      margin: 0;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #05070b;
      color: #d7e0ee;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    @media (max-width: 1100px) {{
      .shell {{ grid-template-columns: 220px minmax(0, 1fr); }}
      .console {{ grid-column: 1 / -1; border-top: 1px solid var(--line); }}
      .command-bar {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 760px) {{
      .shell {{ display: block; }}
      aside {{ border-bottom: 1px solid var(--line); }}
      main, .console {{ padding: 16px; }}
      .command-bar, .ops-panels {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">
        <strong>NERD OS</strong>
        <span>Mission Control Kernel</span>
      </div>
      <p class="nav-kicker">Global Navigation</p>
      <nav>{nav}</nav>
    </aside>
    <main>
      <div class="topbar">
        <h1 id="surfaceTitle">Command Center</h1>
        <div class="status-row">
          <span class="pill" id="moduleCount">{len(registry.actions())} modules</span>
          <span class="pill">policy gated</span>
          <a class="pill link-pill" href="blueprint">blueprint</a>
          <a class="pill link-pill" href="office">office</a>
        </div>
      </div>
      <section class="command-bar" aria-label="Command Bar">
        <label>Command Bar
          <input type="search" placeholder="Search modules, memory, runs, clients">
        </label>
        <label>User
          <select><option>Ruslan Umanoff</option></select>
        </label>
        <label>Project
          <select><option>NERD-METHOD</option></select>
        </label>
        <label>Client
          <select><option>Personal Agency OS</option></select>
        </label>
        <button class="launcher" type="button">Service Launcher</button>
      </section>
      <section class="service-launcher" aria-label="Public Service Launcher">
        <h2>Service Launcher</h2>
        <div class="service-grid">{service_links}</div>
      </section>
      <section class="grid" id="moduleGrid">{cards_html}</section>
    </main>
    <section class="console">
      <section class="ops-panels" aria-label="Mission State">
        <article class="ops-panel">
          <h3>GitHub Status</h3>
          <p id="gitStatus">Loading GitHub health...</p>
        </article>
        <article class="ops-panel">
          <h3>Task Queue</h3>
          <p>Intake, triage, active runs, and handoffs attach to project/client context.</p>
        </article>
        <article class="ops-panel">
          <h3>Module Registry</h3>
          <p>{len(registry.actions())} manifest-backed modules are loaded from the action registry.</p>
        </article>
        <article class="ops-panel">
          <h3>Notifications</h3>
          <p>Git state, blocked actions, failed runs, and service attention markers collect here.</p>
        </article>
        <article class="ops-panel">
          <h3>Agent Roster</h3>
          <p>Strategy, automation, memory, build, observability, and lab roles remain visible.</p>
        </article>
        <article class="ops-panel">
          <h3>Memory Graph</h3>
          <p>Inventory, prompts, source cache, traces, NotebookLM, Obsidian, and client memory.</p>
        </article>
        <article class="ops-panel">
          <h3>Risk Indicators</h3>
          <p>Low-risk runs are direct; medium-risk actions stay contextual; high-risk modules are blocked.</p>
        </article>
        <article class="ops-panel">
          <h3>Kill Switches</h3>
          <p>Automation env, action auto_mode, nginx route, n8n active flag, and Git guard policy.</p>
        </article>
      </section>
      <h2>Run Console</h2>
      <pre id="output">Ready. Select a runnable module.</pre>
      <h2>Recent Runs</h2>
      <div class="history" id="runHistory"></div>
    </section>
  </div>
  <script type="application/json" id="registry-data">{escaped_payload}</script>
  <script type="application/json" id="git-data">{escaped_git_payload}</script>
  <script>
    const registry = JSON.parse(document.getElementById('registry-data').textContent);
    const initialGit = JSON.parse(document.getElementById('git-data').textContent);
    const basePath = location.pathname.startsWith('/nerd-os') ? '/nerd-os' : '';
    const output = document.getElementById('output');
    const history = document.getElementById('runHistory');
    const gitStatus = document.getElementById('gitStatus');
    const tabs = [...document.querySelectorAll('.surface-tab')];
    const cards = [...document.querySelectorAll('.module-card')];
    const title = document.getElementById('surfaceTitle');

    function label(surface) {{
      return surface.split('_').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
    }}
    function selectSurface(surface) {{
      tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.surface === surface));
      cards.forEach(card => card.hidden = card.dataset.surface !== surface);
      title.textContent = label(surface);
    }}
    tabs.forEach(tab => tab.addEventListener('click', () => selectSurface(tab.dataset.surface)));
    if (tabs.length) selectSurface(tabs[0].dataset.surface);

    document.querySelectorAll('.run-button:not([disabled])').forEach(button => {{
      button.addEventListener('click', async () => {{
        const id = button.dataset.action;
        output.textContent = `Running ${{id}}...`;
        button.disabled = true;
        try {{
          const response = await fetch(`${{basePath}}/api/run`, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{id}})
          }});
          const data = await response.json();
          output.textContent = JSON.stringify(data, null, 2);
          await refreshRuns();
        }} catch (error) {{
          output.textContent = String(error);
        }} finally {{
          button.disabled = false;
        }}
      }});
    }});

    async function refreshRuns() {{
      try {{
        const response = await fetch(`${{basePath}}/api/runs`);
        const data = await response.json();
        const rows = (data.items || []).slice(0, 8).map(item => `
          <div class="history-row">
            <div><strong>${{item.action_id}}</strong><br>${{item.timestamp || ''}}</div>
            <span class="pill">${{item.exit_code}}</span>
          </div>
        `).join('');
        history.innerHTML = rows || '<span class="pill">no runs yet</span>';
      }} catch (error) {{
        history.innerHTML = '<span class="pill">history unavailable</span>';
      }}
    }}

    function renderGitStatus(data) {{
      if (data.error) return data.error;
      const dirty = data.dirty_count === 0 ? 'clean' : `${{data.dirty_count}} dirty`;
      const protectedText = data.upstream_push_protected ? 'upstream protected' : 'upstream writable';
      return `${{data.canonical_repo || 'unknown repo'}} · ${{data.branch || 'unknown branch'}} · ${{dirty}} · ${{data.unpushed_commits || 0}} unpushed · ${{protectedText}}`;
    }}

    fetch(`${{basePath}}/api/actions`).catch(() => null);
    gitStatus.textContent = renderGitStatus(initialGit);
    fetch(`${{basePath}}/api/git/status`)
      .then(response => response.json())
      .then(data => {{ gitStatus.textContent = renderGitStatus(data); }})
      .catch(() => null);
    refreshRuns();
  </script>
</body>
</html>
"""


def _request_path(path: str) -> str:
    clean = path.split("?", 1)[0]
    if clean.startswith("/nerd-os"):
        clean = clean.removeprefix("/nerd-os") or "/"
    return clean


def _read_json_body(headers: Any, body_stream: Any) -> dict[str, object]:
    raw_length = str(headers.get("Content-Length", "0") or "0").strip()
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise ValueError("Content-Length must be an integer") from exc
    if length < 0:
        raise ValueError("Content-Length must be non-negative")
    if length > MAX_JSON_BODY_BYTES:
        raise ValueError(f"JSON body exceeds {MAX_JSON_BODY_BYTES} bytes")
    raw_body = body_stream.read(length) if length else b"{}"
    try:
        body_text = (raw_body or b"{}").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("JSON body must be valid UTF-8") from exc
    payload = json.loads(body_text or "{}")
    if not isinstance(payload, dict):
        raise ValueError("JSON object is required")
    return cast("dict[str, object]", payload)


def render_page_html(
    path: str,
    registry: ActionRegistry,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> str | None:
    path = _request_path(path)
    if path in {"/", "/index.html", "/mission-control", "/mission-control/"}:
        return render_mission_control_html(
            canonical_root=canonical_root,
            registry=registry,
        )
    if path in {"/command-center", "/command-center/"}:
        return render_dashboard_html(registry)
    if path in {"/blueprint", "/blueprint/"}:
        return render_blueprint_html(registry)
    if path in {"/office", "/office/"}:
        return render_office_html(registry)
    if path in {"/registry", "/registry/"}:
        payload = autonomous_registry_payload(canonical_root)
        records = list(payload["existing_work"]) + list(payload["workflows"])
        return render_autonomous_records_html(
            title="Autonomous Registry",
            description="Canonical existing-work and workflow records from /root/nerd-method.",
            records=records,
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/inbox", "/inbox/"}:
        payload = autonomous_queue_payload("inbox", canonical_root)
        return render_autonomous_records_html(
            title="Autonomous Inbox",
            description="Manual, Telegram, repo, file, and link intake records.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/tasks", "/tasks/"}:
        payload = autonomous_queue_payload("tasks", canonical_root)
        return render_autonomous_records_html(
            title="Autonomous Tasks",
            description="Draft and routed tasks created from classified inbox records.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/approvals", "/approvals/"}:
        payload = autonomous_approval_payload(canonical_root)
        return render_autonomous_records_html(
            title="Autonomous Approvals",
            description="Gated task decisions. Approval records state policy, but do not execute workflows.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/brain", "/brain/"}:
        return render_brain_html(registry, canonical_root=canonical_root)
    if path in {"/hermes", "/hermes/"}:
        payload = autonomous_hermes_payload(canonical_root)
        return render_autonomous_records_html(
            title="Hermes Agents",
            description="Read-only Hermes CEO, objective, status, and NERD agency mirror records.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/hermes-repair", "/hermes-repair/"}:
        payload = autonomous_hermes_repair_payload(canonical_root)
        return render_autonomous_records_html(
            title="Hermes Repair Readiness",
            description="Read-only Hermes bundle, source, systemd, script, and container repair readiness gates.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/runtimes", "/runtimes/"}:
        payload = autonomous_runtime_payload(canonical_root)
        return render_autonomous_records_html(
            title="Autonomous Runtimes",
            description="Hermes, OpenClaw, local LLM, router, and model gateway records.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/models", "/models/"}:
        payload = autonomous_runtime_payload(canonical_root)
        items = [
            item
            for item in payload["items"]  # type: ignore[index]
            if isinstance(item, dict)
            and str(item.get("kind"))
            in {"model_gateway", "local_llm_runtime", "model_router"}
        ]
        return render_autonomous_records_html(
            title="Autonomous Models",
            description="Model routing bindings and local/private runtime status.",
            records=items,
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/updates", "/updates/"}:
        payload = autonomous_updates_payload(canonical_root)
        return render_autonomous_records_html(
            title="Update Control",
            description="Guarded update candidates, safe refreshes, blockers, and approval boundaries.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/skills", "/skills/"}:
        payload = autonomous_skills_payload(canonical_root)
        return render_autonomous_records_html(
            title="Skills Registry",
            description="Curated, quarantined, custom, and deprecated skills for the NERD OS agent layer.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/workflows", "/workflows/"}:
        payload = autonomous_workflows_payload(canonical_root)
        return render_autonomous_records_html(
            title="Workflow Registry",
            description="Internal, n8n, cron, and webhook workflows with dry-run and approval metadata.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/integrations", "/integrations/"}:
        payload = autonomous_integrations_payload(canonical_root)
        return render_autonomous_records_html(
            title="Runtime Integrations",
            description="Runtime integrations, optional adapters, model gateways, and observability surfaces.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    if path in {"/runs", "/runs/"}:
        payload = autonomous_queue_payload("runs", canonical_root)
        return render_autonomous_records_html(
            title="Autonomous Runs",
            description="Autonomous Core run records and writeback status.",
            records=payload["items"],  # type: ignore[arg-type]
            summary=payload["summary"],  # type: ignore[arg-type]
        )
    surface = _route_to_surface(path)
    if surface is not None:
        return render_surface_html(surface, registry, canonical_root=canonical_root)
    return None


def _surface_label(surface: str) -> str:
    return " ".join(part.capitalize() for part in surface.split("_"))


def serve(
    *,
    actions_path: Path = DEFAULT_ACTIONS_PATH,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    registry = ActionRegistry.load(actions_path)
    runner = ActionRunner(registry)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = _request_path(self.path)
            page = render_page_html(path, registry)
            if page is not None:
                self._html(page)
                return
            if path == "/health":
                self._json({"status": "ok", "actions": len(registry.actions())})
                return
            if path == "/api/actions":
                self._json(action_summary(registry))
                return
            if path == "/api/runs":
                self._json({"items": read_recent_runs()})
                return
            if path == "/api/git/status":
                self._json(git_status_summary())
                return
            try:
                autonomous_payload = autonomous_api_payload(self.path, registry=registry)
            except ValueError as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            if autonomous_payload is not None:
                self._json(autonomous_payload)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = _request_path(self.path)
            if path == "/api/autonomous/agency-delivery":
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = create_agency_delivery(payload)
                except (json.JSONDecodeError, ValueError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path == "/api/autonomous/brain":
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = create_autonomous_brain_record(payload)
                except (json.JSONDecodeError, ValueError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path == "/api/autonomous/inbox":
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = create_autonomous_inbox_record(payload)
                except (json.JSONDecodeError, ValueError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path == "/api/autonomous/brainstorming-trackio":
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = create_brainstorming_trackio_idea(payload)
                except (json.JSONDecodeError, ValueError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path.startswith(
                "/api/autonomous/brainstorming-trackio/"
            ) and path.endswith("/promote"):
                idea_id = path.removeprefix(
                    "/api/autonomous/brainstorming-trackio/"
                ).removesuffix("/promote")
                try:
                    result = promote_brainstorming_trackio_idea(idea_id)
                except ValueError as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path.startswith("/api/autonomous/brain/candidates/") and path.endswith(
                "/promote"
            ):
                candidate_id = path.removeprefix(
                    "/api/autonomous/brain/candidates/"
                ).removesuffix("/promote")
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = promote_autonomous_brain_candidate(candidate_id, payload)
                except (json.JSONDecodeError, ValueError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path == "/api/autonomous/action-requests":
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = create_action_approval_request(payload, registry)
                except (json.JSONDecodeError, ValueError, ActionRegistryError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path == "/api/autonomous/os-cycle":
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = run_operating_cycle(payload, registry, runner)
                except (json.JSONDecodeError, ValueError, ActionRegistryError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path.startswith("/api/autonomous/action-requests/") and path.endswith(
                "/decision"
            ):
                request_id = path.removeprefix(
                    "/api/autonomous/action-requests/"
                ).removesuffix("/decision")
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = decide_action_approval_request(
                        request_id,
                        decision=str(payload.get("decision") or ""),
                        reviewer=str(payload.get("reviewer") or ""),
                        reason=str(payload.get("reason") or "") or None,
                    )
                except (json.JSONDecodeError, ValueError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result)
                return
            if path.startswith("/api/autonomous/action-requests/") and path.endswith(
                "/execute"
            ):
                request_id = path.removeprefix(
                    "/api/autonomous/action-requests/"
                ).removesuffix("/execute")
                try:
                    result = execute_approved_action_request(
                        request_id,
                        registry,
                        runner,
                    )
                except (ValueError, ActionRegistryError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result)
                return
            if path == "/api/autonomous/approvals":
                try:
                    payload = _read_json_body(self.headers, self.rfile)
                    result = update_autonomous_task_approval(
                        str(payload.get("task_id") or ""),
                        decision=str(payload.get("decision") or ""),
                        reviewer=str(payload.get("reviewer") or ""),
                        reason=str(payload.get("reason") or "") or None,
                    )
                except (json.JSONDecodeError, ValueError) as exc:
                    self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._json(result, status=HTTPStatus.CREATED)
                return
            if path != "/api/run":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                payload = _read_json_body(self.headers, self.rfile)
            except (json.JSONDecodeError, ValueError) as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            action_id = str(payload.get("id", ""))
            try:
                result = runner.run(action_id)
            except DisabledActionError as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.FORBIDDEN)
                return
            except ActionRegistryError as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                return
            self._json(result.to_dict())

        def log_message(self, format: str, *args: object) -> None:
            return

        def _json(
            self,
            payload: dict[str, object],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _html(
            self,
            markup: str,
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = markup.encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NERD OS action runner")
    parser.add_argument(
        "--actions",
        type=Path,
        default=DEFAULT_ACTIONS_PATH,
        help="Path to nerd-os.actions.yaml",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("action_id")
    run_parser.add_argument("--allow-disabled", action="store_true")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default=DEFAULT_HOST)
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    args = parser.parse_args(argv)
    registry = ActionRegistry.load(args.actions)
    if args.command == "list":
        print(json.dumps(action_summary(registry), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        try:
            result = ActionRunner(registry).run(
                args.action_id,
                allow_disabled=args.allow_disabled,
            )
        except (ActionRegistryError, DisabledActionError) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return result.exit_code
    if args.command == "serve":
        serve(actions_path=args.actions, host=args.host, port=args.port)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
