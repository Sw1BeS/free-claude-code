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
            if self.path in {"/", "/index.html"}:
                self._html(render_dashboard_html(registry))
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
