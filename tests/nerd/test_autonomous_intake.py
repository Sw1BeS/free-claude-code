from __future__ import annotations

import json


def test_manual_github_url_creates_research_task():
    from scripts.nerd.autonomous.intake import create_inbox_item, create_task_from_inbox

    item = create_inbox_item("https://github.com/unclecode/crawl4ai", source="manual")
    task = create_task_from_inbox(item)

    assert item.detected_type == "repo"
    assert item.tags == ["github", "repo"]
    assert task.department == "research"
    assert task.model_profile == "research_deep"
    assert task.required_approval is False


def test_high_risk_text_routes_to_lab_with_approval():
    from scripts.nerd.autonomous.intake import create_inbox_item, create_task_from_inbox

    item = create_inbox_item("darkweb offensive automation farming idea", source="manual")
    task = create_task_from_inbox(item)

    assert item.risk == "high"
    assert item.tags == ["high-risk", "lab"]
    assert task.department == "lab"
    assert task.required_approval is True
    assert task.status == "approval_required"


def test_shopify_text_routes_to_cms_commerce():
    from scripts.nerd.autonomous.intake import create_inbox_item, create_task_from_inbox

    item = create_inbox_item("Build a Shopify theme analytics helper", source="manual")
    task = create_task_from_inbox(item)

    assert item.detected_type == "task"
    assert task.department == "cms-commerce"
    assert task.model_profile == "coding_deep"


def test_write_manual_inbox_item_and_task(tmp_path):
    from scripts.nerd.autonomous.intake import write_manual_inbox_item

    result = write_manual_inbox_item(
        "Analyze https://github.com/github/spec-kit",
        canonical_root=tmp_path,
        source="manual",
    )

    inbox_payload = json.loads(result["inbox_path"].read_text(encoding="utf-8"))
    task_payload = json.loads(result["task_path"].read_text(encoding="utf-8"))
    assert inbox_payload["detected_type"] == "repo"
    assert task_payload["department"] == "research"


def test_write_brain_intake_file_creates_memory_candidate(tmp_path):
    from scripts.nerd.autonomous.intake import write_brain_intake

    source_file = tmp_path / "notes.md"
    source_file.write_text("# Hermes\nRuntime source consistency notes.\n", encoding="utf-8")

    result = write_brain_intake(
        text="Promote Hermes runtime notes",
        file_path=source_file,
        canonical_root=tmp_path / "nerd-method",
        source="manual-file",
    )

    inbox_payload = json.loads(result["paths"]["inbox"].read_text(encoding="utf-8"))
    task_payload = json.loads(result["paths"]["task"].read_text(encoding="utf-8"))
    candidate_payload = json.loads(result["paths"]["candidate"].read_text(encoding="utf-8"))

    assert result["dry_run"] is False
    assert inbox_payload["detected_type"] == "file"
    assert inbox_payload["raw_path"] == str(source_file)
    assert task_payload["department"] == "memory"
    assert candidate_payload["promotion_status"] == "candidate"
    assert candidate_payload["artifact_type"] == "memory_candidate"
    assert str(source_file) in candidate_payload["provenance"]
    assert result["paths"]["candidate_markdown"].is_file()


def test_write_brain_intake_dry_run_does_not_write(tmp_path):
    from scripts.nerd.autonomous.intake import write_brain_intake

    result = write_brain_intake(
        text="https://github.com/github/spec-kit",
        canonical_root=tmp_path / "nerd-method",
        source="telegram",
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["inbox"]["detected_type"] == "repo"
    assert result["task"]["department"] == "research"
    assert result["candidate"]["promotion_status"] == "candidate"
    assert not (tmp_path / "nerd-method" / "memory" / "inbox").exists()


def test_promote_memory_candidate_writes_approved_knowledge(tmp_path):
    from scripts.nerd.autonomous.intake import (
        promote_memory_candidate,
        write_brain_intake,
    )

    intake = write_brain_intake(
        text="Remember: Hermes objectives map to managed NERD OS agents.",
        canonical_root=tmp_path / "nerd-method",
        source="manual",
    )

    result = promote_memory_candidate(
        intake["candidate"]["id"],
        canonical_root=tmp_path / "nerd-method",
        reviewer="operator",
    )

    approved_payload = json.loads(intake["paths"]["candidate"].read_text(encoding="utf-8"))
    knowledge_text = result["knowledge_path"].read_text(encoding="utf-8")
    assert approved_payload["promotion_status"] == "approved"
    assert approved_payload["approved_by"] == "operator"
    assert result["artifact"]["path"] == str(result["knowledge_path"])
    assert "Hermes objectives map" in knowledge_text
