from __future__ import annotations

import argparse
import html
import json
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ACTIONS_PATH = Path("/root/nerd-agency-stack/nerd-os.actions.yaml")
DEFAULT_RUN_LOG_PATH = Path("/root/nerd-method/memory/reports/nerd-os-runs.jsonl")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 38181


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
        <p>One operational shell for ClaudeCore, Open WebUI, automation, shared memory, GitInspired modules, CMS commerce, data work, and observability.</p>
      </div>
      <a href="/">Command Center</a>
    </header>
    <section class="map">
      <section class="layer entry">
        <h2>Entry Points</h2>
        <div class="stack">
          <article class="node"><p>Public UI</p><strong>Open WebUI + NERD OS</strong><span>agency.umanoff-analytics.space</span></article>
          <article class="node"><p>CLI</p><strong>free-claude / nerd-os</strong><span>server and future Mac node</span></article>
        </div>
      </section>
      <section class="layer brain">
        <div>
          <h2>Shared Brain</h2>
          <p>Single durable memory layer used by every entry point.</p>
        </div>
        <article class="node"><p>Inventory</p><strong>NERD-METHOD reports</strong><span>services, repos, skills, source cache</span></article>
        <article class="node"><p>Knowledge</p><strong>Open WebUI knowledge</strong><span>seeded docs and manifests</span></article>
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
    assigned_ids = {action_id for _, group, _, _ in department_specs for action_id in groups.get(group, [])}
    fallback_ids = [action.id for action in registry.actions() if action.id not in assigned_ids]
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
        lanes = "<li><span>agency_idle</span><div class=\"track\"><i></i></div></li>"
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
    actions = {action.id: action for action in registry.actions()}
    nav = "\n".join(
        f'<button class="surface-tab" data-surface="{html.escape(surface)}">'
        f"{html.escape(_surface_label(surface))}"
        f"<span>{len(action_ids)}</span></button>"
        for surface, action_ids in surfaces.items()
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
    escaped_payload = html.escape(initial_payload)
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
    }}
    @media (max-width: 760px) {{
      .shell {{ display: block; }}
      aside {{ border-bottom: 1px solid var(--line); }}
      main, .console {{ padding: 16px; }}
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
      <section class="grid" id="moduleGrid">{cards_html}</section>
    </main>
    <section class="console">
      <h2>Run Console</h2>
      <pre id="output">Ready. Select a runnable module.</pre>
      <h2>Recent Runs</h2>
      <div class="history" id="runHistory"></div>
    </section>
  </div>
  <script type="application/json" id="registry-data">{escaped_payload}</script>
  <script>
    const registry = JSON.parse(document.getElementById('registry-data').textContent);
    const basePath = location.pathname.startsWith('/nerd-os') ? '/nerd-os' : '';
    const output = document.getElementById('output');
    const history = document.getElementById('runHistory');
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

    fetch(`${{basePath}}/api/actions`).catch(() => null);
    refreshRuns();
  </script>
</body>
</html>
"""


def render_page_html(path: str, registry: ActionRegistry) -> str | None:
    if path in {"/", "/index.html"}:
        return render_dashboard_html(registry)
    if path in {"/blueprint", "/blueprint/"}:
        return render_blueprint_html(registry)
    if path in {"/office", "/office/"}:
        return render_office_html(registry)
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
            page = render_page_html(self.path, registry)
            if page is not None:
                self._html(page)
                return
            if self.path == "/health":
                self._json({"status": "ok", "actions": len(registry.actions())})
                return
            if self.path == "/api/actions":
                self._json(action_summary(registry))
                return
            if self.path == "/api/runs":
                self._json({"items": read_recent_runs()})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path != "/api/run":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
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
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(
            self,
            markup: str,
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = markup.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
