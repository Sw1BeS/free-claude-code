from __future__ import annotations

import argparse
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
    def __init__(self, registry: ActionRegistry) -> None:
        self.registry = registry

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
            return ActionResult(
                action_id=action.id,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=_elapsed_ms(started),
            )
        except subprocess.TimeoutExpired as exc:
            return ActionResult(
                action_id=action.id,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or f"Timed out after {action.timeout_seconds}s",
                duration_ms=_elapsed_ms(started),
                timed_out=True,
            )


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
            if self.path == "/health":
                self._json({"status": "ok", "actions": len(registry.actions())})
                return
            if self.path == "/api/actions":
                self._json(action_summary(registry))
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
