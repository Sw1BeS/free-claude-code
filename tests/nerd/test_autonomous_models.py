from __future__ import annotations

import json

import yaml


def test_bootstrap_writes_policy_and_registry_files(tmp_path):
    from scripts.nerd.autonomous.bootstrap import bootstrap_autonomous_core

    result = bootstrap_autonomous_core(tmp_path)

    assert (tmp_path / "system" / "model-routing.yaml").is_file()
    assert (tmp_path / "system" / "autonomy-policy.yaml").is_file()
    assert (tmp_path / "system" / "memory-contract.yaml").is_file()
    assert (tmp_path / "registry" / "departments.json").is_file()
    assert (tmp_path / "registry" / "models.json").is_file()
    assert (tmp_path / "memory" / "inbox").is_dir()
    assert (tmp_path / "memory" / "brain").is_dir()
    assert (tmp_path / "memory" / "brain" / "candidates").is_dir()
    assert (tmp_path / "memory" / "agents").is_dir()
    assert (tmp_path / "operations" / "updates").is_dir()
    assert result["canonical_root"] == str(tmp_path)


def test_bootstrap_models_include_required_profiles(tmp_path):
    from scripts.nerd.autonomous.bootstrap import bootstrap_autonomous_core

    bootstrap_autonomous_core(tmp_path)

    models = json.loads((tmp_path / "registry" / "models.json").read_text())
    model_ids = {item["id"] for item in models["items"]}

    assert {
        "coding_deep",
        "coding_fast",
        "research_deep",
        "data_extract",
        "ops_fast",
        "design_ui",
        "private_local",
        "lab_research",
    }.issubset(model_ids)


def test_bootstrap_model_routing_materializes_local_runtime_bindings(tmp_path):
    from scripts.nerd.autonomous.bootstrap import bootstrap_autonomous_core

    bootstrap_autonomous_core(tmp_path)

    routing = yaml.safe_load((tmp_path / "system" / "model-routing.yaml").read_text())

    assert routing["runtimes"]["litellm-local"]["base_url"] == "http://127.0.0.1:44000/v1"
    assert routing["runtimes"]["ollama"]["kind"] == "local_llm_runtime"
    assert routing["runtimes"]["9router"]["kind"] == "coding_agent_router"
    assert routing["profile_bindings"]["ops_fast"]["runtime"] == "litellm-local"
    assert routing["profile_bindings"]["private_local"]["runtime"] == "ollama"
    assert routing["profile_bindings"]["coding_fast"]["runtime"] == "9router"
    assert routing["hermes_aliases"]["ops-fast"] == "ops_fast"
    assert routing["policy"]["external_metered_spend"] == "approval_required"


def test_bootstrap_domain_routes_include_brain_hermes_and_updates(tmp_path):
    from scripts.nerd.autonomous.bootstrap import bootstrap_autonomous_core

    bootstrap_autonomous_core(tmp_path)

    routes = yaml.safe_load((tmp_path / "system" / "domain-routes.yaml").read_text())

    assert "/nerd-os/brain" in routes["routes"]
    assert "/nerd-os/hermes" in routes["routes"]
    assert "/nerd-os/updates" in routes["routes"]


def test_inbox_item_serializes_sorted_tags_and_policy_fields():
    from scripts.nerd.autonomous.models import InboxItem

    item = InboxItem(
        id="inbox_20260524_000001",
        created_at="2026-05-24T00:00:00Z",
        source="manual",
        raw_text="Analyze https://github.com/example/repo",
        detected_type="repo",
        tags=["repo", "github"],
        risk="low",
        privacy="project",
        status="classified",
    )

    assert item.to_dict()["tags"] == ["github", "repo"]
    assert item.to_dict()["risk"] == "low"
    assert item.to_dict()["privacy"] == "project"


def test_task_marks_high_risk_as_approval_required():
    from scripts.nerd.autonomous.models import Task

    task = Task(
        id="task_20260524_000001",
        inbox_id="inbox_20260524_000001",
        title="Research high-risk request",
        department="lab",
        risk="high",
        autonomy_level="L4",
        assigned_agent_role="lab_researcher",
        model_profile="lab_research",
        required_approval=True,
        status="approval_required",
    )

    assert task.to_dict()["required_approval"] is True
    assert task.to_dict()["department"] == "lab"


def test_pretty_json_is_stable_and_ascii_safe():
    from scripts.nerd.autonomous.models import to_pretty_json

    text = to_pretty_json({"b": 2, "a": "NERD"})

    assert text == '{\n  "a": "NERD",\n  "b": 2\n}\n'


def test_approval_record_serializes_decision_and_execution_gate():
    from scripts.nerd.autonomous.models import ApprovalRecord

    record = ApprovalRecord(
        id="approval_20260524_000001",
        task_id="task_20260524_000001",
        decision="approve",
        reviewer="operator",
        decided_at="2026-05-24T00:00:00Z",
        reason="research only",
        execution_allowed=False,
    )

    assert record.to_dict()["decision"] == "approve"
    assert record.to_dict()["execution_allowed"] is False
    assert record.to_dict()["reason"] == "research only"
