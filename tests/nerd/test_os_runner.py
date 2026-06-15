from __future__ import annotations

import io
import json
import subprocess
import sys
from email.message import Message
from pathlib import Path
from typing import cast

import pytest

from scripts.nerd.os.runner import (
    MAX_JSON_BODY_BYTES,
    ActionRegistry,
    ActionRunner,
    DisabledActionError,
    _read_json_body,
    action_summary,
    autonomous_action_console_payload,
    autonomous_action_requests_payload,
    autonomous_api_payload,
    autonomous_approval_payload,
    autonomous_brain_payload,
    autonomous_brain_store_payload,
    autonomous_github_radar_payload,
    autonomous_hermes_payload,
    autonomous_hermes_repair_payload,
    autonomous_integrations_payload,
    autonomous_mission_control_payload,
    autonomous_observability_payload,
    autonomous_run_detail_payload,
    autonomous_run_timeline_payload,
    autonomous_skills_payload,
    autonomous_summary,
    autonomous_updates_payload,
    autonomous_workflows_payload,
    create_action_approval_request,
    create_agency_delivery,
    create_autonomous_brain_record,
    create_autonomous_inbox_record,
    create_brainstorming_trackio_idea,
    decide_action_approval_request,
    execute_approved_action_request,
    git_status_summary,
    main,
    promote_autonomous_brain_candidate,
    promote_brainstorming_trackio_idea,
    public_service_links,
    read_recent_runs,
    render_blueprint_html,
    render_brain_html,
    render_dashboard_html,
    render_office_html,
    render_page_html,
    run_operating_cycle,
    update_autonomous_task_approval,
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
    assert registry.groups() == {
        "core_ops": ["stack_status"],
        "automation_ops": ["cloakbrowser_start"],
    }


def test_runner_executes_allowed_action_and_captures_output(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    runner = ActionRunner(ActionRegistry.load(actions_path))

    result = runner.run("stack_status")

    assert result.action_id == "stack_status"
    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert result.timed_out is False


def test_runner_writes_bounded_run_history(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    log_path = tmp_path / "runs.jsonl"
    write_actions(actions_path)
    runner = ActionRunner(ActionRegistry.load(actions_path), log_path=log_path)

    runner.run("stack_status")
    runs = read_recent_runs(log_path, limit=1)

    assert len(runs) == 1
    assert runs[0]["action_id"] == "stack_status"
    assert runs[0]["exit_code"] == 0
    assert runs[0]["risk"] == "low"
    assert runs[0]["auto_mode"] == "allowed"
    assert "stdout" not in runs[0]


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


def test_action_console_payload_groups_actions_without_commands(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    payload = autonomous_action_console_payload(registry, canonical_root=tmp_path)

    items = {item["id"]: item for item in payload["items"]}
    assert items["stack_status"]["status"] == "runnable"
    assert items["stack_status"]["execution_policy"] == "allowed"
    assert items["cloakbrowser_start"]["status"] == "approval_required"
    assert items["cloakbrowser_start"]["execution_policy"] == "disabled"
    assert items["stack_status"]["command"] == ["<redacted>"]
    assert payload["summary"]["allowed_count"] == 1
    assert payload["summary"]["disabled_count"] == 1


def test_create_action_approval_request_records_disabled_action(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    result = create_action_approval_request(
        {
            "action_id": "cloakbrowser_start",
            "requester": "operator",
            "reason": "Need lab review",
        },
        registry,
        canonical_root=tmp_path,
    )

    request = result["request"]
    assert request["action_id"] == "cloakbrowser_start"
    assert request["status"] == "approval_requested"
    assert request["execution_allowed"] is False
    assert request["risk"] == "high"
    assert Path(result["paths"]["request"]).is_file()
    payload = autonomous_action_requests_payload(tmp_path)
    assert payload["items"][0]["id"] == request["id"]


def test_create_action_approval_request_rejects_allowed_action(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    with pytest.raises(ValueError, match="already runnable"):
        create_action_approval_request(
            {"action_id": "stack_status", "requester": "operator"},
            registry,
            canonical_root=tmp_path,
        )


def test_action_request_approve_reject_and_execute_flow(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    log_path = tmp_path / "memory" / "reports" / "nerd-os-runs.jsonl"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    runner = ActionRunner(registry, log_path=log_path)

    requested = create_action_approval_request(
        {
            "action_id": "cloakbrowser_start",
            "requester": "operator",
            "reason": "Need gated lab action",
        },
        registry,
        canonical_root=tmp_path,
    )["request"]

    rejected = decide_action_approval_request(
        str(requested["id"]),
        decision="reject",
        reviewer="operator",
        reason="Not needed",
        canonical_root=tmp_path,
    )
    assert rejected["request"]["status"] == "rejected"
    assert rejected["request"]["execution_allowed"] is False

    requested_again = create_action_approval_request(
        {
            "action_id": "cloakbrowser_start",
            "requester": "operator",
            "reason": "Run after review",
        },
        registry,
        canonical_root=tmp_path,
    )["request"]
    approved = decide_action_approval_request(
        str(requested_again["id"]),
        decision="approve",
        reviewer="operator",
        reason="One-shot run allowed",
        canonical_root=tmp_path,
    )
    executed = execute_approved_action_request(
        str(requested_again["id"]),
        registry,
        runner,
        canonical_root=tmp_path,
    )

    assert approved["request"]["status"] == "approved"
    assert approved["request"]["execution_allowed"] is True
    assert executed["request"]["status"] == "executed"
    assert executed["result"]["action_id"] == "cloakbrowser_start"
    assert executed["result"]["stdout"] == "<redacted>"
    assert read_recent_runs(log_path, limit=1)[0]["action_id"] == "cloakbrowser_start"


def test_operating_cycle_runs_safe_actions_and_writes_cycle_record(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    log_path = tmp_path / "memory" / "reports" / "nerd-os-runs.jsonl"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    runner = ActionRunner(registry, log_path=log_path)

    result = run_operating_cycle(
        {"action_ids": ["stack_status", "cloakbrowser_start"]},
        registry,
        runner,
        canonical_root=tmp_path,
    )

    cycle = result["cycle"]
    assert isinstance(cycle, dict)
    cycle = cast("dict[str, object]", cycle)
    results = cycle["results"]
    assert isinstance(results, list)
    assert cycle["kind"] == "operating_cycle"
    assert cycle["action_count"] == 1
    assert results[0]["action_id"] == "stack_status"
    assert results[0]["status"] == "success"
    paths = result["paths"]
    assert isinstance(paths, dict)
    paths = cast("dict[str, object]", paths)
    assert Path(str(paths["cycle"])).is_file()
    assert read_recent_runs(log_path, limit=1)[0]["action_id"] == "stack_status"


def test_run_timeline_detail_payload_finds_enriched_run(tmp_path):
    run_log = tmp_path / "memory" / "reports" / "nerd-os-runs.jsonl"
    run_log.parent.mkdir(parents=True)
    run_log.write_text(
        '{"timestamp": "2026-05-25T01:00:00Z", "action_id": "stack_status", "exit_code": 0, "duration_ms": 10}\n',
        encoding="utf-8",
    )

    timeline = autonomous_run_timeline_payload(tmp_path)
    run_id = timeline["items"][0]["id"]
    detail = autonomous_run_detail_payload(run_id, tmp_path)

    assert detail["item"]["id"] == run_id
    assert detail["item"]["action_id"] == "stack_status"
    assert detail["item"]["status"] == "success"


def test_action_registry_contains_autonomous_core_actions():
    registry = ActionRegistry.load()
    action_ids = {action.id for action in registry.actions()}
    action_text = "\n".join(
        f"{action.id} {action.display_name} {action.group} {action.surface}"
        for action in registry.actions()
    ).lower()

    assert "autonomous_core_bootstrap" in action_ids
    assert "autonomous_existing_work_refresh" in action_ids
    assert "autonomous_runtime_registry_refresh" in action_ids
    assert "autonomous_brain_memory_refresh" in action_ids
    assert "autonomous_brain_store_sync" in action_ids
    assert "autonomous_brain_intake_n8n_dry_run" in action_ids
    assert "autonomous_brain_intake_telegram_dry_run" in action_ids
    assert "autonomous_hermes_agents_refresh" in action_ids
    assert "autonomous_hermes_repair_readiness_refresh" in action_ids
    assert "autonomous_update_candidates_refresh" in action_ids
    assert "autonomous_skills_registry_refresh" in action_ids
    assert "autonomous_workflows_registry_refresh" in action_ids
    assert "autonomous_github_radar_refresh" in action_ids
    assert "autonomous_observability_registry_refresh" in action_ids
    assert "hermes_status" in action_ids
    assert "hermes_doctor" in action_ids
    assert "ollama_list" in action_ids
    assert "paperclip" not in action_text


def test_cli_reports_disabled_action_without_traceback(tmp_path, capsys):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)

    exit_code = main(["--actions", str(actions_path), "run", "cloakbrowser_start"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "disabled" in captured.out
    assert "Traceback" not in captured.err


def test_dashboard_html_exposes_shell_without_commands(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    html = render_dashboard_html(registry)

    assert "NERD OS" in html
    assert "Command Center" in html
    assert "stack_status" in html
    assert "cloakbrowser_start" in html
    assert "disabled" in html
    assert "print('ok')" not in html
    assert "/api/actions" in html
    assert "/api/run" in html
    assert "/api/runs" in html
    assert 'href="blueprint"' in html
    assert 'href="office"' in html
    for label in [
        "Virtual Office",
        "Tasks",
        "Automations",
        "Knowledge",
        "GitHub",
        "Build Studio",
        "CMS/Commerce",
        "Data Studio",
        "Product/Growth",
        "Settings",
    ]:
        assert label in html
    assert "Command Bar" in html
    assert "Service Launcher" in html
    assert "Task Queue" in html
    assert "Agent Roster" in html
    assert "Memory Graph" in html
    assert "Kill Switches" in html
    assert "/api/git/status" in html
    assert 'href="automations"' in html
    assert 'href="lab"' in html
    assert 'href="cms-commerce"' in html


def test_dashboard_uses_public_domain_links_not_local_ips(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    html = render_dashboard_html(registry)

    assert "https://agency.umanoff-analytics.space/nerd-os/" in html
    assert "https://agency.umanoff-analytics.space/nerd-os/blueprint" in html
    assert "https://agency.umanoff-analytics.space/nerd-os/office" in html
    assert "https://automations.umanoff-analytics.space" in html
    assert "https://memory.umanoff-analytics.space" in html
    assert "http://127.0.0.1" not in html
    assert "http://172.20.0.1" not in html
    assert "localhost" not in html


def test_public_service_links_are_domain_only():
    links = public_service_links()
    urls = {item["url"] for item in links}

    assert "https://agency.umanoff-analytics.space/nerd-os/" in urls
    assert "https://agency.umanoff-analytics.space/nerd-os/blueprint" in urls
    assert "https://agency.umanoff-analytics.space/nerd-os/office" in urls
    assert all(str(url).startswith("https://") for url in urls)
    assert not any("127.0.0.1" in str(url) for url in urls)


def test_git_status_summary_reports_safe_remote_policy(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            capture_output=True,
            check=True,
        )

    run("init", "-b", "nerd/safe-upgrade")
    run("config", "user.email", "nerd@example.test")
    run("config", "user.name", "NERD Test")
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    run("add", "README.md")
    run("commit", "-m", "init")
    run("remote", "add", "origin", "https://github.com/Sw1BeS/free-claude-code.git")
    run(
        "remote",
        "add",
        "upstream",
        "https://github.com/Alishahryar1/free-claude-code.git",
    )
    run("remote", "set-url", "--push", "upstream", "DISABLED")

    summary = git_status_summary(repo)

    assert summary["branch"] == "nerd/safe-upgrade"
    assert summary["canonical_repo"] == "Sw1BeS/free-claude-code"
    assert (
        summary["origin_push_url"] == "https://github.com/Sw1BeS/free-claude-code.git"
    )
    assert summary["upstream_push_url"] == "DISABLED"
    assert summary["dirty_count"] == 0
    assert summary["upstream_push_protected"] is True


def test_blueprint_html_maps_nerd_os_layers_without_commands(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    html = render_blueprint_html(registry)

    assert "NERD OS Blueprint" in html
    assert "Entry Points" in html
    assert "Shared Brain" in html
    assert "Tool Mesh" in html
    assert "Automation Fabric" in html
    assert "Observability" in html
    assert "stack_status" in html
    assert "cloakbrowser_start" in html
    assert "print('ok')" not in html


def test_office_html_shows_visible_agent_agency_without_commands(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    html = render_office_html(registry)

    assert "NERD OS Office" in html
    assert "Virtual Office" in html
    assert "Strategy Room" in html
    assert "Automation Bay" in html
    assert "Memory Desk" in html
    assert "Observability Wall" in html
    assert "Agent activity lanes" in html
    assert "stack_status" in html
    assert "cloakbrowser_start" in html
    assert "print('ok')" not in html


def test_internal_office_route_renders_office_page(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    html = render_page_html("/office", registry)

    assert "NERD OS Office" in html
    assert "Virtual Office" in html


def test_autonomous_summary_reads_canonical_records(tmp_path):
    registry_dir = tmp_path / "registry"
    inbox_dir = tmp_path / "memory" / "inbox"
    tasks_dir = tmp_path / "memory" / "tasks"
    runs_dir = tmp_path / "memory" / "runs"
    registry_dir.mkdir(parents=True)
    inbox_dir.mkdir(parents=True)
    tasks_dir.mkdir(parents=True)
    runs_dir.mkdir(parents=True)
    (registry_dir / "existing-work.json").write_text(
        '{"items": [{"id": "root-nerd-method", "name": "NERD Method"}]}',
        encoding="utf-8",
    )
    (registry_dir / "workflows.json").write_text(
        '{"items": [{"id": "health_status", "risk": "low"}]}',
        encoding="utf-8",
    )
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": [{"id": "runtime-hermes", "name": "Hermes", "status": "active"}]}',
        encoding="utf-8",
    )
    (registry_dir / "brain-memory.json").write_text(
        '{"items": [{"id": "brain-memory-root", "name": "Memory", "status": "present"}]}',
        encoding="utf-8",
    )
    (registry_dir / "hermes-agents.json").write_text(
        '{"items": [{"id": "hermes-agent-ceo", "name": "Hermes CEO", "status": "active"}]}',
        encoding="utf-8",
    )
    (registry_dir / "update-candidates.json").write_text(
        '{"items": [{"id": "update-hermes-agent-runtime", "name": "Hermes Update", "status": "blocked"}]}',
        encoding="utf-8",
    )
    (registry_dir / "skills-registry.json").write_text(
        '{"items": [{"id": "skill-memory-curation"}]}',
        encoding="utf-8",
    )
    (registry_dir / "workflows-registry.json").write_text(
        '{"items": [{"id": "workflow-brain-intake-n8n"}]}',
        encoding="utf-8",
    )
    (registry_dir / "github-radar.json").write_text(
        '{"items": [{"id": "github-radar-staging-repo"}]}',
        encoding="utf-8",
    )
    (registry_dir / "observability-events.json").write_text(
        '{"items": [{"id": "observability-run-log"}]}',
        encoding="utf-8",
    )
    run_log = tmp_path / "memory" / "reports" / "nerd-os-runs.jsonl"
    run_log.parent.mkdir(parents=True)
    run_log.write_text(
        '{"timestamp": "2026-05-25T01:00:00Z", "action_id": "stack_status", "exit_code": 0, "duration_ms": 10}\n',
        encoding="utf-8",
    )
    (inbox_dir / "inbox_1.json").write_text('{"id": "inbox_1"}', encoding="utf-8")
    (tasks_dir / "task_1.json").write_text('{"id": "task_1"}', encoding="utf-8")
    (runs_dir / "run_1.json").write_text('{"id": "run_1"}', encoding="utf-8")

    summary = autonomous_summary(tmp_path)

    assert summary["canonical_root"] == str(tmp_path)
    assert summary["registry"]["existing_work_count"] == 1
    assert summary["registry"]["workflow_count"] == 1
    assert summary["registry"]["runtime_count"] == 1
    assert summary["registry"]["brain_count"] == 1
    assert summary["registry"]["hermes_agent_count"] == 1
    assert summary["registry"]["update_candidate_count"] == 1
    assert summary["registry"]["skills_count"] == 1
    assert summary["registry"]["workflows_registry_count"] == 1
    assert "decommissioned_count" not in summary["registry"]
    assert summary["queues"]["inbox_count"] == 1
    assert summary["queues"]["task_count"] == 1
    assert summary["queues"]["run_count"] == 1


def test_autonomous_pages_render_from_canonical_records(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "existing-work.json").write_text(
        '{"items": [{"id": "root-nerd-method", "name": "NERD Method"}]}',
        encoding="utf-8",
    )

    registry_html = render_page_html("/registry", registry, canonical_root=tmp_path)
    inbox_html = render_page_html("/inbox", registry, canonical_root=tmp_path)
    tasks_html = render_page_html("/tasks", registry, canonical_root=tmp_path)
    runs_html = render_page_html("/runs", registry, canonical_root=tmp_path)

    assert registry_html is not None
    assert "Autonomous Registry" in registry_html
    assert "root-nerd-method" in registry_html
    assert "Autonomous Inbox" in inbox_html
    assert "Autonomous Tasks" in tasks_html
    assert "Autonomous Runs" in runs_html


def test_surface_routes_render_domain_accessible_sections(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "workflows.json").write_text(
        '{"items": [{"id": "health_status", "name": "Health", "risk": "low"}]}',
        encoding="utf-8",
    )

    lab_html = render_page_html("/lab", registry, canonical_root=tmp_path)
    automations_html = render_page_html(
        "/automations", registry, canonical_root=tmp_path
    )
    prefixed_html = render_page_html("/nerd-os/lab", registry, canonical_root=tmp_path)

    assert lab_html is not None
    assert "NERD OS Lab" in lab_html
    assert "cloakbrowser_start" in lab_html
    assert automations_html is not None
    assert "NERD OS Automations" in automations_html
    assert "health_status" in automations_html
    assert prefixed_html is not None
    assert "NERD OS Lab" in prefixed_html


def test_runtime_routes_render_hermes_openclaw_and_local_llm_records(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": ['
        '{"id": "runtime-hermes", "name": "Hermes", "kind": "runtime", "status": "active", "risk": "medium"},'
        '{"id": "source-openclaw-skills", "name": "OpenClaw Skills", "kind": "skillpack", "status": "present", "risk": "low"},'
        '{"id": "runtime-ollama", "name": "Ollama", "kind": "local_llm_runtime", "status": "needs_attention", "risk": "low"}'
        "]}",
        encoding="utf-8",
    )

    runtimes_html = render_page_html("/runtimes", registry, canonical_root=tmp_path)
    models_html = render_page_html("/models", registry, canonical_root=tmp_path)

    assert runtimes_html is not None
    assert "Autonomous Runtimes" in runtimes_html
    assert "runtime-hermes" in runtimes_html
    assert "source-openclaw-skills" in runtimes_html
    assert models_html is not None
    assert "Autonomous Models" in models_html
    assert "runtime-ollama" in models_html


def test_brain_hermes_and_update_routes_render_canonical_records(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "brain-memory.json").write_text(
        '{"items": ['
        '{"id": "brain-srv-nerd-knowledge", "name": "Ops Vault", "status": "present", "risk": "medium"},'
        '{"id": "brain-openwebui-seed", "name": "Open WebUI Optional Seed Script", "status": "present", "classification": "optional_legacy_adapter"},'
        '{"id": "brain-paperclip-old", "name": "Paperclip Old Knowledge", "status": "approved"}'
        "]}",
        encoding="utf-8",
    )
    (registry_dir / "hermes-agents.json").write_text(
        '{"items": [{"id": "hermes-agent-ceo", "name": "Hermes CEO", "status": "active", "risk": "medium"}]}',
        encoding="utf-8",
    )
    (registry_dir / "update-candidates.json").write_text(
        '{"items": [{"id": "update-hermes-agent-runtime", "name": "Hermes Update", "status": "blocked", "risk": "high"}]}',
        encoding="utf-8",
    )
    (registry_dir / "hermes-repair-readiness.json").write_text(
        '{"items": [{"id": "hermes-runtime-bundle-layout", "name": "Bundle Layout", "status": "blocked", "risk": "high"}]}',
        encoding="utf-8",
    )

    brain_html = render_page_html("/brain", registry, canonical_root=tmp_path)
    hermes_html = render_page_html("/hermes", registry, canonical_root=tmp_path)
    updates_html = render_page_html("/updates", registry, canonical_root=tmp_path)
    repair_html = render_page_html("/hermes-repair", registry, canonical_root=tmp_path)
    prefixed_html = render_page_html(
        "/nerd-os/brain", registry, canonical_root=tmp_path
    )

    assert brain_html is not None
    assert "Autonomous Brain" in brain_html
    assert "NERD OS Second Brain" in brain_html
    assert 'id="brainIntakeForm"' in brain_html
    assert "/api/autonomous/brain" in brain_html
    assert "brain-srv-nerd-knowledge" in brain_html
    assert "Open WebUI" not in brain_html
    assert "Paperclip" not in brain_html
    assert hermes_html is not None
    assert "Hermes Agents" in hermes_html
    assert "hermes-agent-ceo" in hermes_html
    assert updates_html is not None
    assert "Update Control" in updates_html
    assert "update-hermes-agent-runtime" in updates_html
    assert repair_html is not None
    assert "Hermes Repair Readiness" in repair_html
    assert "hermes-runtime-bundle-layout" in repair_html
    assert prefixed_html is not None
    assert "Autonomous Brain" in prefixed_html


def test_brain_html_renders_store_snapshot_sources_and_candidates(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    result = create_autonomous_brain_record(
        {"text": "Remember: the second brain has a DB-backed store.", "source": "operator"},
        canonical_root=tmp_path,
    )

    html = render_brain_html(registry, canonical_root=tmp_path)

    assert result["brain_store"]["candidate_count"] == 1
    assert "NERD OS Second Brain" in html
    assert "source_operator" in html
    assert result["candidate"]["id"] in html
    assert "/api/autonomous/brain-store" in html


def test_mission_control_route_renders_operator_shell_sections(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "hermes-agents.json").write_text(
        '{"items": [{"id": "hermes-agent-ceo", "name": "Hermes CEO", "status": "active", "risk": "medium"}]}',
        encoding="utf-8",
    )
    (registry_dir / "brain-memory.json").write_text(
        '{"items": [{"id": "brain-memory-root", "name": "Memory", "status": "present", "risk": "medium"}]}',
        encoding="utf-8",
    )
    (registry_dir / "update-candidates.json").write_text(
        '{"items": [{"id": "update-hermes-agent-runtime", "name": "Hermes Update", "status": "candidate", "risk": "medium"}]}',
        encoding="utf-8",
    )
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": [{"id": "integration-openwebui", "name": "Open WebUI", "status": "optional", "risk": "medium", "metadata": {"core_shell": false}}, {"id": "runtime-hermes", "name": "Hermes", "status": "active", "risk": "medium"}]}',
        encoding="utf-8",
    )
    (registry_dir / "skills-registry.json").write_text(
        '{"items": [{"id": "skill-memory-curation", "name": "Memory Curation", "status": "approved", "risk_level": "low"}]}',
        encoding="utf-8",
    )
    (registry_dir / "workflows-registry.json").write_text(
        '{"items": [{"id": "workflow-brain-intake-n8n", "name": "Brain Intake", "status": "dry_run_ready"}]}',
        encoding="utf-8",
    )
    (registry_dir / "github-radar.json").write_text(
        '{"items": [{"id": "github-radar-staging-repo", "name": "Staging Repo", "status": "clean", "risk": "low"}]}',
        encoding="utf-8",
    )
    (registry_dir / "observability-events.json").write_text(
        '{"items": [{"id": "observability-run-log", "name": "Run Log", "status": "active", "risk": "low"}]}',
        encoding="utf-8",
    )
    runs_dir = tmp_path / "memory" / "reports"
    runs_dir.mkdir(parents=True)
    (runs_dir / "nerd-os-runs.jsonl").write_text(
        '{"timestamp": "2026-05-25T01:00:00Z", "action_id": "stack_status", "exit_code": 0, "duration_ms": 10}\n',
        encoding="utf-8",
    )

    html = render_page_html("/mission-control", registry, canonical_root=tmp_path)
    prefixed_html = render_page_html(
        "/nerd-os/mission-control", registry, canonical_root=tmp_path
    )

    assert html is not None
    assert "NERD OS Mission Control" in html
    assert "Mission Control reference" in html
    for label in [
        "Overview",
        "Inbox",
        "Agents",
        "Tasks / Runs",
        "Skills",
        "Workflows",
        "GitHub Radar",
        "Knowledge",
        "Integrations",
        "Observability",
        "System Updates",
        "Settings",
    ]:
        assert label in html
    assert "skill-memory-curation" in html
    assert "workflow-brain-intake-n8n" in html
    assert "Action Console" in html
    assert "Run Timeline" in html
    assert "github-radar-staging-repo" in html
    assert "observability-run-log" in html
    assert "stack_status" in html
    assert 'id="actionFilters"' in html
    assert 'id="runDetailDrawer"' in html
    assert 'id="actionRequestDialog"' in html
    assert 'data-action-id="stack_status"' in html
    assert 'data-action-id="cloakbrowser_start"' in html
    assert "data-run-id=" in html
    assert "/api/autonomous/action-requests" in html
    assert "/api/autonomous/run-detail/" in html
    assert "Legacy / Archive" not in html
    assert "component-paperclip" not in html
    assert "Paperclip" not in html
    assert "Open WebUI" not in html
    assert "optional_chat_surface" not in html
    assert prefixed_html is not None
    assert "NERD OS Mission Control" in prefixed_html


def test_mission_control_redacts_internal_backend_addresses(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": [{"id": "gateway-litellm-local", "name": "LiteLLM", '
        '"status": "configured", "metadata": {"base_url": "http://127.0.0.1:44000/v1"}}]}',
        encoding="utf-8",
    )

    html = render_page_html("/mission-control", registry, canonical_root=tmp_path)

    assert html is not None
    assert "gateway-litellm-local" in html
    assert "[internal backend]" in html
    assert "127.0.0.1" not in html
    assert "172.20." not in html
    assert "localhost" not in html


def test_autonomous_specialized_payloads_read_new_registries(tmp_path):
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "brain-memory.json").write_text(
        '{"items": [{"id": "brain-memory-root"}]}',
        encoding="utf-8",
    )
    (registry_dir / "hermes-agents.json").write_text(
        '{"items": [{"id": "hermes-agent-ceo"}]}',
        encoding="utf-8",
    )
    (registry_dir / "update-candidates.json").write_text(
        '{"items": [{"id": "update-hermes-agent-runtime"}]}',
        encoding="utf-8",
    )
    (registry_dir / "hermes-repair-readiness.json").write_text(
        '{"items": [{"id": "hermes-runtime-bundle-layout"}]}',
        encoding="utf-8",
    )
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": [{"id": "runtime-hermes"}]}',
        encoding="utf-8",
    )
    (registry_dir / "skills-registry.json").write_text(
        '{"items": [{"id": "skill-memory-curation"}]}',
        encoding="utf-8",
    )
    (registry_dir / "workflows-registry.json").write_text(
        '{"items": [{"id": "workflow-brain-intake-n8n"}]}',
        encoding="utf-8",
    )
    (registry_dir / "github-radar.json").write_text(
        '{"items": [{"id": "github-radar-staging-repo"}]}',
        encoding="utf-8",
    )
    (registry_dir / "observability-events.json").write_text(
        '{"items": [{"id": "observability-run-log"}]}',
        encoding="utf-8",
    )
    run_log = tmp_path / "memory" / "reports" / "nerd-os-runs.jsonl"
    run_log.parent.mkdir(parents=True)
    run_log.write_text(
        '{"timestamp": "2026-05-25T01:00:00Z", "action_id": "stack_status", "exit_code": 0, "duration_ms": 10}\n',
        encoding="utf-8",
    )

    assert autonomous_brain_payload(tmp_path)["items"][0]["id"] == "brain-memory-root"
    assert autonomous_brain_store_payload(tmp_path)["store"]["status"] == "missing"
    assert autonomous_hermes_payload(tmp_path)["items"][0]["id"] == "hermes-agent-ceo"
    assert autonomous_updates_payload(tmp_path)["items"][0]["id"] == (
        "update-hermes-agent-runtime"
    )
    assert autonomous_hermes_repair_payload(tmp_path)["items"][0]["id"] == (
        "hermes-runtime-bundle-layout"
    )
    assert (
        autonomous_integrations_payload(tmp_path)["items"][0]["id"] == "runtime-hermes"
    )
    assert (
        autonomous_skills_payload(tmp_path)["items"][0]["id"] == "skill-memory-curation"
    )
    assert autonomous_workflows_payload(tmp_path)["items"][0]["id"] == (
        "workflow-brain-intake-n8n"
    )
    assert (
        autonomous_github_radar_payload(tmp_path)["items"][0]["id"]
        == "github-radar-staging-repo"
    )
    assert (
        autonomous_observability_payload(tmp_path)["items"][0]["id"]
        == "observability-run-log"
    )
    assert (
        autonomous_run_timeline_payload(tmp_path)["items"][0]["action_id"]
        == "stack_status"
    )
    mission = autonomous_mission_control_payload(tmp_path)
    assert "overview" in mission
    assert mission["sections"]["skills"][0]["id"] == "skill-memory-curation"
    assert mission["sections"]["github_radar"][0]["id"] == "github-radar-staging-repo"
    assert "brain_store" in mission["sections"]
    assert "brain_graph" in mission["sections"]
    assert "brain_harness" in mission["sections"]
    assert mission["sections"]["brain_graph"]["status"] == "missing"
    assert mission["sections"]["brain_harness"]["candidate_count"] == 0


def test_autonomous_api_payload_maps_mission_control_and_registry_routes(tmp_path):
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "skills-registry.json").write_text(
        '{"items": [{"id": "skill-memory-curation"}]}',
        encoding="utf-8",
    )
    (registry_dir / "workflows-registry.json").write_text(
        '{"items": [{"id": "workflow-brain-intake-n8n"}]}',
        encoding="utf-8",
    )
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": [{"id": "integration-openwebui", "metadata": {"core_shell": false}}]}',
        encoding="utf-8",
    )
    (registry_dir / "github-radar.json").write_text(
        '{"items": [{"id": "github-radar-staging-repo"}]}',
        encoding="utf-8",
    )
    (registry_dir / "observability-events.json").write_text(
        '{"items": [{"id": "observability-run-log"}]}',
        encoding="utf-8",
    )
    run_log = tmp_path / "memory" / "reports" / "nerd-os-runs.jsonl"
    run_log.parent.mkdir(parents=True)
    run_log.write_text(
        '{"timestamp": "2026-05-25T01:00:00Z", "action_id": "stack_status", "exit_code": 0, "duration_ms": 10}\n',
        encoding="utf-8",
    )

    action_requests = autonomous_api_payload(
        "/api/autonomous/action-requests", tmp_path
    )
    trackio_payload = autonomous_api_payload(
        "/api/autonomous/brainstorming-trackio", tmp_path
    )
    run_detail = autonomous_api_payload(
        "/api/autonomous/run-detail/run_20260525T010000Z_stack_status",
        tmp_path,
    )
    brain_store = autonomous_api_payload("/api/autonomous/brain-store", tmp_path)
    created_brain = create_autonomous_brain_record(
        {"text": "Searchable brain API memory", "source": "operator"},
        canonical_root=tmp_path,
    )
    brain_search = autonomous_api_payload(
        "/api/autonomous/brain/search?q=Searchable&limit=3",
        tmp_path,
    )
    brain_context = autonomous_api_payload(
        "/api/autonomous/brain/context?q=Searchable&limit=3",
        tmp_path,
    )
    brain_detail = autonomous_api_payload(
        f"/api/autonomous/brain/candidates/{created_brain['candidate']['id']}",
        tmp_path,
    )

    mission_payload = autonomous_api_payload("/api/mission-control", tmp_path)

    for removed_path in [
        "/nerd-os/api/autonomous/mission-control",
        "/api/autonomous/skills",
        "/api/autonomous/workflows",
        "/api/autonomous/integrations",
        "/api/autonomous/decommissioned",
        "/api/autonomous/action-console",
        "/api/autonomous/run-timeline",
        "/api/autonomous/github-radar",
        "/api/autonomous/observability",
    ]:
        assert autonomous_api_payload(removed_path, tmp_path) is None

    assert mission_payload is not None
    assert mission_payload["product"] == "NERD OS Mission Control"
    assert "samples" not in mission_payload["summary"]
    for section in [
        "agents",
        "tasks",
        "run_timeline",
        "approvals",
        "skills",
        "workflows",
        "github_radar",
        "brain",
        "brain_store",
        "brain_graph",
        "brain_harness",
        "integrations",
        "observability",
        "system_health",
        "brainstorming_trackio",
        "action_console",
        "action_requests",
        "operation_graph",
        "attention_queue",
        "evidence_index",
        "domain_routes",
        "policy_matrix",
        "agency_deliveries",
    ]:
        assert section in mission_payload["sections"]
    assert mission_payload["schema_version"] == "mission_control.v2"
    assert mission_payload["auth_state"]["status"] == "externalized"
    assert mission_payload["secret_status"]["status"] == "redaction_enabled"
    assert action_requests is not None
    assert action_requests["items"] == []
    assert trackio_payload is not None
    assert trackio_payload["items"] == []
    assert run_detail is not None
    assert run_detail["item"]["action_id"] == "stack_status"
    assert brain_store is not None
    assert brain_store["store"]["status"] == "missing"
    assert brain_search is not None
    assert brain_search["status"] == "ok"
    assert brain_search["results"][0]["candidate_id"] == created_brain["candidate"]["id"]
    assert brain_context is not None
    assert brain_context["recall_status"] == "ok"
    assert brain_context["recall"][0]["candidate_id"] == created_brain["candidate"]["id"]
    assert "NERD OS Second Brain Context Pack" in brain_context["markdown"]
    assert brain_detail is not None
    assert brain_detail["candidate"]["id"] == created_brain["candidate"]["id"]
    assert brain_detail["source"]["id"] == "source_operator"


def test_mission_control_payload_exposes_agency_deliveries(tmp_path):
    deliveries_path = tmp_path / "memory" / "runs" / "agency-deliveries.jsonl"
    deliveries_path.parent.mkdir(parents=True)
    records = [
        {
            "id": "agency_delivery_old_001",
            "status": "mystery",
            "request": "Historical delivery with sparse fields",
        },
        {
            "id": "agency_delivery_test_001",
            "title": "Создай лендос для агентства NERD",
            "status": "partial",
            "risk": "medium",
            "mode": "landing_page",
            "task_id": "task_test_001",
            "created_at": "2026-06-14T10:00:00Z",
            "verification": {
                "html_smoke": "passed",
                "browser_smoke": "blocked_missing_browser",
                "deploy_smoke": "blocked_missing_deployment_target",
            },
            "artifact_paths": [
                "/tmp/delivery/01-brief.md",
                "/tmp/delivery/site/index.html",
            ],
            "next_action": "review_or_deploy",
            "blocker": "Browser smoke is blocked until browser tooling is available.",
        },
        {
            "id": "agency_delivery_success_with_blocked_verification",
            "title": "Successful package with incomplete smoke",
            "status": "success",
            "verification": {
                "html_smoke": "passed",
                "browser_smoke": "not_run",
            },
        },
        {
            "id": "agency_delivery_success_with_failed_verification",
            "title": "Successful package with failed smoke",
            "status": "success",
            "verification": {
                "html_smoke": "failed",
            },
        },
    ]
    deliveries_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
        + "\n{not-json}\n",
        encoding="utf-8",
    )

    mission = autonomous_mission_control_payload(tmp_path)
    deliveries = mission["sections"]["agency_deliveries"]

    assert isinstance(deliveries, list)
    by_id = {delivery["id"]: delivery for delivery in deliveries}
    delivery = by_id["agency_delivery_test_001"]
    assert delivery == {
        "id": "agency_delivery_test_001",
        "title": "Создай лендос для агентства NERD",
        "status": "partial",
        "risk": "medium",
        "mode": "landing_page",
        "task_id": "task_test_001",
        "created_at": "2026-06-14T10:00:00Z",
        "verification": {
            "html_smoke": "passed",
            "browser_smoke": "blocked_missing_browser",
            "deploy_smoke": "blocked_missing_deployment_target",
        },
        "artifact_count": 2,
        "next_action": "review_or_deploy",
        "blocker": "Browser smoke is blocked until browser tooling is available.",
    }
    assert by_id["agency_delivery_old_001"]["status"] == "unknown"
    assert by_id["agency_delivery_old_001"]["verification"] == {
        "summary": "unknown"
    }
    assert by_id["agency_delivery_success_with_blocked_verification"]["status"] == (
        "partial"
    )
    assert by_id["agency_delivery_success_with_failed_verification"]["status"] == (
        "failed"
    )
    assert "artifact_paths" not in delivery


def test_mission_control_payload_redacts_sensitive_agency_delivery_fields(tmp_path):
    deliveries_path = tmp_path / "memory" / "runs" / "agency-deliveries.jsonl"
    deliveries_path.parent.mkdir(parents=True)
    deliveries_path.write_text(
        json.dumps(
            {
                "id": "agency_delivery_sensitive_001",
                "title": "Sensitive delivery api_key: sk-live-secret password: hunter2",
                "status": "success",
                "mode": "landing_page",
                "task_id": "task_sensitive_001",
                "created_at": "2026-06-14T10:15:00Z",
                "api_key": "sk-test-secret-value",
                "authorization": "Bearer hidden-token",
                "url": "http://127.0.0.1:9999/internal",
                "password": "do-not-render",
                "next_action": "rotate access_token=secret-next-token before deploy",
                "blocker": "client_secret: sk-blocker-secret " + ("x" * 700),
                "verification": {
                    "html_smoke": "passed",
                    "browser_smoke": "http://127.0.0.1:9999/internal",
                    "token_probe": "api_key: sk-verify-secret",
                    "verification_path": "/root/nerd-method/artifacts/deliveries/05-verification.md",
                },
                "artifact_paths": ["/tmp/delivery/run.json"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    mission = autonomous_mission_control_payload(tmp_path)
    serialized = json.dumps(mission, ensure_ascii=False)

    assert "sk-test-secret-value" not in serialized
    assert "sk-live-secret" not in serialized
    assert "hunter2" not in serialized
    assert "Bearer hidden-token" not in serialized
    assert "secret-next-token" not in serialized
    assert "sk-blocker-secret" not in serialized
    assert "sk-verify-secret" not in serialized
    assert "do-not-render" not in serialized
    assert "127.0.0.1:9999" not in serialized
    assert "/root/nerd-method" not in serialized
    assert "x" * 700 not in serialized
    assert "[internal backend]" in serialized
    assert "<redacted>" in serialized


def test_mission_control_payload_redacts_local_paths_recursively(tmp_path):
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "brain-memory.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "brain-local-path-test",
                        "name": "Local path probe",
                        "status": "present",
                        "detail": "/root/hermes/core/objectives.json",
                        "notes": "Mirror /home/alice/private.env and /etc/nginx/nginx.conf",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (registry_dir / "runtime-integrations.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "runtime-path-test",
                        "name": "Runtime path probe",
                        "status": "configured",
                        "workspace": "/var/lib/nerd-os/state",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    mission = autonomous_mission_control_payload(tmp_path)
    serialized = json.dumps(mission, ensure_ascii=False)

    assert str(tmp_path) not in serialized
    assert "/root/hermes" not in serialized
    assert "/home/alice" not in serialized
    assert "/etc/nginx" not in serialized
    assert "/var/lib/nerd-os" not in serialized
    assert "[local path]" in serialized


def test_mission_control_v2_sections_reuse_registry_runs_and_actions(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    registry_dir = tmp_path / "registry"
    tasks_dir = tmp_path / "memory" / "tasks"
    registry_dir.mkdir(parents=True)
    tasks_dir.mkdir(parents=True)
    (registry_dir / "hermes-agents.json").write_text(
        '{"items": [{"id": "hermes-agent-ceo", "name": "Hermes CEO", "status": "active", "risk": "medium"}]}',
        encoding="utf-8",
    )
    (registry_dir / "workflows-registry.json").write_text(
        '{"items": [{"id": "workflow-brain-intake-n8n", "name": "Brain Intake", "status": "dry_run_ready", "related_integration": "gateway-litellm-local"}]}',
        encoding="utf-8",
    )
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": [{"id": "gateway-litellm-local", "name": "LiteLLM", '
        '"status": "needs_attention", "risk": "medium", '
        '"metadata": {"base_url": "http://127.0.0.1:44000/v1"}}]}',
        encoding="utf-8",
    )
    (tasks_dir / "task_1.json").write_text(
        '{"id": "task_1", "title": "Review route", "status": "approval_required", '
        '"required_approval": true, "risk": "high", "related_agent": "hermes-agent-ceo"}',
        encoding="utf-8",
    )
    run_log = tmp_path / "memory" / "reports" / "nerd-os-runs.jsonl"
    run_log.parent.mkdir(parents=True)
    run_log.write_text(
        '{"timestamp": "2026-05-25T01:00:00Z", "action_id": "stack_status", "exit_code": 0, "duration_ms": 10}\n',
        encoding="utf-8",
    )

    mission = autonomous_mission_control_payload(tmp_path, registry=registry)

    graph = mission["sections"]["operation_graph"]
    assert isinstance(graph, dict)
    node_ids = {node["id"] for node in graph["nodes"]}
    edges = {(edge["from"], edge["to"], edge["kind"]) for edge in graph["edges"]}
    assert {"stack_status", "task_1", "hermes-agent-ceo"} <= node_ids
    assert ("hermes-agent-ceo", "task_1", "owns_task") in edges
    assert mission["sections"]["attention_queue"]["summary"]["count"] >= 2
    assert mission["sections"]["policy_matrix"]["summary"]["manual_gate_count"] >= 1
    routes = mission["sections"]["domain_routes"]["items"]
    assert any(route["url"] == "[internal backend]" for route in routes)
    assert mission["sections"]["evidence_index"]["summary"]["source"] == (
        "brain_github_observability_runs"
    )


def test_mission_control_redacts_sensitive_key_names_recursively(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "runtime-integrations.json").write_text(
        '{"items": [{"id": "gateway-secret-test", "name": "Gateway", '
        '"status": "configured", "metadata": {'
        '"api_key": "sk-test-value", '
        '"clientSecret": "client-secret-value", '
        '"nested": {"password": "p4ssw0rd", "authorization": "Bearer token-value"}, '
        '"base_url": "http://localhost:44000/v1"}}]}',
        encoding="utf-8",
    )

    mission = autonomous_mission_control_payload(tmp_path, registry=registry)
    serialized = str(mission)

    assert mission["secret_status"]["status"] == "redaction_enabled"
    assert "sk-test-value" not in serialized
    assert "client-secret-value" not in serialized
    assert "p4ssw0rd" not in serialized
    assert "Bearer token-value" not in serialized
    assert "localhost" not in serialized
    assert serialized.count("<redacted>") >= 4


def test_brainstorming_trackio_creates_ideas_and_promotes_task_candidates(tmp_path):
    created = create_brainstorming_trackio_idea(
        {
            "title": "Repo radar workflow",
            "description": "Promote repo signals into guarded tasks",
            "source": "manual",
            "priority": "high",
            "related_agent": "hermes-agent-ceo",
            "related_skill": "skill-repo-radar",
            "related_repo": "Sw1BeS/free-claude-code",
            "next_action": "promote",
        },
        canonical_root=tmp_path,
    )

    idea = created["idea"]
    assert isinstance(idea, dict)
    idea = cast("dict[str, object]", idea)
    assert idea["status"] == "idea"
    assert idea["priority"] == "high"
    created_summary = created["summary"]
    assert isinstance(created_summary, dict)
    created_summary = cast("dict[str, object]", created_summary)
    assert Path(str(created_summary["path"])).is_file()

    promoted = promote_brainstorming_trackio_idea(
        str(idea["id"]),
        canonical_root=tmp_path,
    )

    promoted_idea = promoted["idea"]
    promoted_task = promoted["task"]
    promoted_paths = promoted["paths"]
    assert isinstance(promoted_idea, dict)
    assert isinstance(promoted_task, dict)
    assert isinstance(promoted_paths, dict)
    promoted_idea = cast("dict[str, object]", promoted_idea)
    promoted_task = cast("dict[str, object]", promoted_task)
    promoted_paths = cast("dict[str, object]", promoted_paths)
    assert promoted_idea["status"] == "planned"
    assert promoted_task["source_idea_id"] == idea["id"]
    assert promoted_task["status"] == "approval_required"
    assert promoted_task["execution_allowed"] is False
    assert Path(str(promoted_paths["task"])).is_file()


def test_autonomous_inbox_page_exposes_manual_intake_form(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)

    html = render_page_html("/inbox", registry, canonical_root=tmp_path)

    assert html is not None
    assert 'id="inboxForm"' in html
    assert "/api/autonomous/inbox" in html
    assert "Create Draft Task" in html


def test_create_autonomous_inbox_record_writes_inbox_and_task(tmp_path):
    result = create_autonomous_inbox_record(
        {"text": "Analyze https://github.com/github/spec-kit", "source": "web"},
        canonical_root=tmp_path,
    )

    assert result["inbox"]["detected_type"] == "repo"
    assert result["task"]["department"] == "research"
    assert result["task"]["required_approval"] is False
    assert result["candidate"]["promotion_status"] == "candidate"
    assert Path(result["paths"]["inbox"]).is_file()
    assert Path(result["paths"]["task"]).is_file()
    assert Path(result["paths"]["candidate"]).is_file()
    assert autonomous_summary(tmp_path)["queues"]["inbox_count"] == 1
    assert autonomous_summary(tmp_path)["queues"]["task_count"] == 1
    assert autonomous_summary(tmp_path)["queues"]["artifact_count"] == 1


def test_create_agency_delivery_runs_delivery_and_writes_evidence(tmp_path):
    result = create_agency_delivery(
        {
            "text": "Create a landing page for the NERD OS execution desk.",
            "source": "operator",
            "mode": "landing_page",
            "browser_smoke": False,
            "auto_deploy": False,
        },
        canonical_root=tmp_path,
    )

    delivery = result["delivery"]
    assert delivery["status"] in {"success", "partial"}
    assert delivery["mode"] == "landing_page"
    assert delivery["task_id"]
    assert Path(delivery["paths"]["run"]).is_file()
    assert Path(delivery["paths"]["site"]).is_file()
    assert len(delivery["artifact_paths"]) >= 6
    assert result["summary"]["queues"]["task_count"] == 1
    assert (tmp_path / "memory" / "runs" / "agency-deliveries.jsonl").is_file()


def test_create_agency_delivery_can_attach_to_existing_task(tmp_path):
    task = create_autonomous_inbox_record(
        {"text": "Build task execution binding.", "source": "operator"},
        canonical_root=tmp_path,
    )["task"]

    result = create_agency_delivery(
        {
            "text": "Build task execution binding.",
            "source": f"task:{task['id']}",
            "task_id": task["id"],
            "mode": "implementation",
            "browser_smoke": False,
            "auto_deploy": False,
        },
        canonical_root=tmp_path,
    )

    assert result["delivery"]["task_id"] == task["id"]
    assert result["summary"]["queues"]["task_count"] == 1
    run_record = json.loads(Path(result["delivery"]["paths"]["run"]).read_text())
    assert run_record["task_id"] == task["id"]


def test_read_json_body_rejects_malformed_or_oversized_content_length():
    malformed = Message()
    malformed["Content-Length"] = "not-an-int"
    with pytest.raises(ValueError, match="Content-Length must be an integer"):
        _read_json_body(malformed, io.BytesIO(b"{}"))

    oversized = Message()
    oversized["Content-Length"] = str(MAX_JSON_BODY_BYTES + 1)
    with pytest.raises(ValueError, match="JSON body exceeds"):
        _read_json_body(oversized, io.BytesIO(b"{}"))

    invalid_utf8 = Message()
    invalid_utf8["Content-Length"] = "1"
    with pytest.raises(ValueError, match="valid UTF-8"):
        _read_json_body(invalid_utf8, io.BytesIO(b"\xff"))

    not_object = Message()
    not_object["Content-Length"] = "2"
    with pytest.raises(ValueError, match="JSON object is required"):
        _read_json_body(not_object, io.BytesIO(b"[]"))

    valid = Message()
    valid["Content-Length"] = "17"
    assert _read_json_body(valid, io.BytesIO(b'{"reviewer":"op"}')) == {
        "reviewer": "op"
    }


def test_autonomous_brain_payload_includes_graph_and_harness(tmp_path):
    result = create_autonomous_brain_record(
        {"text": "Graph contract should be available to brain UI.", "source": "operator"},
        canonical_root=tmp_path,
    )

    payload = autonomous_brain_payload(tmp_path)
    node_ids = {node["id"] for node in payload["graph"]["nodes"]}

    assert payload["store"]["candidate_count"] == 1
    assert payload["harness"]["candidate_count"] == 1
    assert "brain-store-db" in node_ids
    assert result["candidate"]["id"] in node_ids
    assert payload["context_pack"]["recall"][0]["candidate_id"] == result["candidate"]["id"]
    assert "Second Brain Context Pack" in payload["context_pack"]["markdown"]
    assert payload["candidates"][0]["id"] == result["candidate"]["id"]
    assert payload["sources"][0]["id"] == "source_operator"


def test_promote_autonomous_brain_candidate_returns_refreshed_store_graph_and_harness(tmp_path):
    result = create_autonomous_brain_record(
        {"text": "Promote this candidate through the route helper.", "source": "operator"},
        canonical_root=tmp_path,
    )
    candidate_id = result["candidate"]["id"]

    promoted = promote_autonomous_brain_candidate(
        candidate_id,
        {"reviewer": "memory-curator"},
        canonical_root=tmp_path,
    )

    node_ids = {node["id"] for node in promoted["graph"]["nodes"]}
    assert promoted["promoted"]["artifact"]["promotion_status"] == "approved"
    assert promoted["promoted"]["artifact"]["approved_by"] == "memory-curator"
    assert promoted["store"]["approved_count"] == 1
    assert promoted["harness"]["approved_count"] == 1
    assert f"knowledge_{candidate_id}" in node_ids


def test_create_autonomous_inbox_record_gates_high_risk_lab_requests(tmp_path):
    result = create_autonomous_inbox_record(
        {"text": "darkweb offensive automation farming idea", "source": "web"},
        canonical_root=tmp_path,
    )

    assert result["inbox"]["risk"] == "high"
    assert result["task"]["department"] == "lab"
    assert result["task"]["required_approval"] is True
    assert result["task"]["status"] == "approval_required"


def test_approval_payload_lists_tasks_requiring_approval(tmp_path):
    high_risk = create_autonomous_inbox_record(
        {"text": "darkweb offensive automation farming idea", "source": "web"},
        canonical_root=tmp_path,
    )
    create_autonomous_inbox_record(
        {"text": "Analyze https://github.com/github/spec-kit", "source": "web"},
        canonical_root=tmp_path,
    )

    payload = autonomous_approval_payload(tmp_path)

    assert [item["id"] for item in payload["items"]] == [high_risk["task"]["id"]]
    assert payload["items"][0]["status"] == "approval_required"
    assert payload["items"][0]["execution_allowed"] is False


def test_update_autonomous_task_approval_keeps_lab_execution_disabled(tmp_path):
    result = create_autonomous_inbox_record(
        {"text": "darkweb offensive automation farming idea", "source": "web"},
        canonical_root=tmp_path,
    )

    approval = update_autonomous_task_approval(
        result["task"]["id"],
        decision="approve",
        reviewer="operator",
        reason="research only",
        canonical_root=tmp_path,
    )

    assert approval["task"]["status"] == "approved_for_research"
    assert approval["task"]["execution_allowed"] is False
    assert approval["approval"]["decision"] == "approve"
    assert Path(approval["paths"]["approval"]).is_file()


def test_approval_page_renders_pending_queue(tmp_path):
    actions_path = tmp_path / "actions.yaml"
    write_actions(actions_path)
    registry = ActionRegistry.load(actions_path)
    create_autonomous_inbox_record(
        {"text": "darkweb offensive automation farming idea", "source": "web"},
        canonical_root=tmp_path,
    )

    html = render_page_html("/approvals", registry, canonical_root=tmp_path)

    assert html is not None
    assert "Autonomous Approvals" in html
    assert "approval_required" in html
    assert "/api/autonomous/approvals" in html
