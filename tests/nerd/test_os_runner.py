from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.nerd.os.runner import (
    ActionRegistry,
    ActionRunner,
    DisabledActionError,
    action_summary,
    main,
)


def write_actions(path: Path, *, command: list[str] | None = None) -> None:
    command = command or [sys.executable, "-c", "print('ok')"]
    path.write_text(
        f"""
version: 1
actions:
  - id: stack_status
    display_name: Stack Status
    group: core_ops
    surface: command_center
    risk: low
    auto_mode: allowed
    cwd: {path.parent}
    timeout_seconds: 5
    command:
{chr(10).join(f"      - {part!r}" for part in command)}
  - id: cloakbrowser_start
    display_name: CloakBrowser Start
    group: automation_ops
    surface: lab
    risk: high
    auto_mode: disabled
    cwd: {path.parent}
    timeout_seconds: 5
    command:
      - {sys.executable!r}
      - "-c"
      - "print('blocked')"
""".lstrip(),
        encoding="utf-8",
    )


def test_registry_loads_actions_with_ui_surface(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)

    registry = ActionRegistry.load(actions_path)

    assert registry.get("stack_status").surface == "command_center"
    assert registry.get("stack_status").auto_mode == "allowed"
    assert registry.groups() == {"core_ops": ["stack_status"], "automation_ops": ["cloakbrowser_start"]}


def test_runner_executes_allowed_action_and_captures_output(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    runner = ActionRunner(ActionRegistry.load(actions_path))

    result = runner.run("stack_status")

    assert result.action_id == "stack_status"
    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert result.timed_out is False


def test_runner_blocks_disabled_action_by_default(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    runner = ActionRunner(ActionRegistry.load(actions_path))

    with pytest.raises(DisabledActionError):
        runner.run("cloakbrowser_start")


def test_action_summary_is_safe_for_ui(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    summary = action_summary(registry)

    assert summary["count"] == 2
    assert summary["groups"]["core_ops"] == ["stack_status"]
    assert summary["surfaces"]["command_center"] == ["stack_status"]
    assert summary["actions"][0]["command"] == ["<redacted>"]


def test_cli_reports_disabled_action_without_traceback(tmp_path, capsys):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)

    exit_code = main(["--actions", str(actions_path), "run", "cloakbrowser_start"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "disabled" in captured.out
    assert "Traceback" not in captured.err
