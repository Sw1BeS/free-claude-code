import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "scripts" / "nerd" / "agency" / "openwebui_seed.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mission_control_prompts_define_core_workspace_commands():
    seed = load_module("agency_openwebui_seed_prompts", SEED_PATH)

    prompts = seed.mission_control_prompts()
    by_command = {prompt.command: prompt for prompt in prompts}

    assert {
        "mission_control",
        "automation_ops",
        "cms_commerce",
        "knowledge_vault",
        "observability",
    }.issubset(by_command)
    mission = by_command["mission_control"]
    assert mission.name == "NERD Agency Mission Control"
    assert "https://agency.umanoff-analytics.space" in mission.content
    assert "loopback-only" in mission.content
    assert "nerd-agency" in mission.tags
    assert "secret" not in mission.content.lower()


def test_prompt_upsert_plan_creates_updates_and_keeps_by_command():
    seed = load_module("agency_openwebui_seed_prompt_plan", SEED_PATH)
    desired = seed.mission_control_prompts()
    mission = next(prompt for prompt in desired if prompt.command == "mission_control")
    automation = next(
        prompt for prompt in desired if prompt.command == "automation_ops"
    )
    existing = [
        {
            "id": "mission-id",
            "command": mission.command,
            "name": mission.name,
            "content": mission.content,
            "tags": list(mission.tags),
        },
        {
            "id": "automation-id",
            "command": automation.command,
            "name": "Old Automation",
            "content": automation.content,
            "tags": list(automation.tags),
        },
    ]

    plan = seed.plan_prompt_upserts(existing, desired)
    actions = {(change.action, change.key): change for change in plan}

    assert actions[("keep", "mission_control")].object_id == "mission-id"
    assert actions[("update", "automation_ops")].object_id == "automation-id"
    assert actions[("create", "cms_commerce")].object_id is None
    assert (
        actions[("create", "knowledge_vault")].payload["command"] == "knowledge_vault"
    )


def test_mission_control_memories_are_marker_based_and_idempotent():
    seed = load_module("agency_openwebui_seed_memory_plan", SEED_PATH)

    memories = seed.mission_control_memories()
    markers = {memory.marker for memory in memories}

    assert {
        "[NERD-AGENCY memory:system]",
        "[NERD-AGENCY memory:automation]",
        "[NERD-AGENCY memory:knowledge]",
        "[NERD-AGENCY memory:safety]",
    }.issubset(markers)
    assert all(memory.content.startswith(memory.marker) for memory in memories)
    assert any("Open WebUI knowledge" in memory.content for memory in memories)

    system = next(memory for memory in memories if memory.marker.endswith(":system]"))
    safety = next(memory for memory in memories if memory.marker.endswith(":safety]"))
    existing = [
        {"id": "system-id", "content": system.content},
        {"id": "safety-id", "content": safety.marker + "\nold policy"},
    ]

    plan = seed.plan_memory_upserts(existing, memories)
    actions = {(change.action, change.key): change for change in plan}

    assert actions[("keep", system.marker)].object_id == "system-id"
    assert actions[("update", safety.marker)].object_id == "safety-id"
    assert actions[("create", "[NERD-AGENCY memory:automation]")].payload == {
        "content": next(
            memory.content
            for memory in memories
            if memory.marker == "[NERD-AGENCY memory:automation]"
        )
    }


def test_knowledge_prompt_and_memory_name_versioned_reports_as_canonical_source():
    seed = load_module("agency_openwebui_seed_knowledge_canonical", SEED_PATH)

    prompts = seed.mission_control_prompts()
    knowledge_prompt = next(
        prompt for prompt in prompts if prompt.command == "knowledge_vault"
    )
    knowledge_memory = next(
        memory
        for memory in seed.mission_control_memories()
        if memory.marker == "[NERD-AGENCY memory:knowledge]"
    )

    for content in (knowledge_prompt.content, knowledge_memory.content):
        assert "versioned NERD reports plus runtime sync targets" in content
        assert "not scattered chat memory" in content
        assert "secret" not in content.lower()


def test_seed_summary_contains_actions_without_credentials():
    seed = load_module("agency_openwebui_seed_summary", SEED_PATH)
    changes = [
        seed.SeedChange(
            kind="prompt",
            action="create",
            key="mission_control",
            payload={"content": "payload"},
        ),
        seed.SeedChange(
            kind="memory",
            action="update",
            key="[NERD-AGENCY memory:safety]",
            payload={"content": "payload"},
            object_id="memory-id",
        ),
    ]

    text = seed.render_seed_plan(changes)

    assert "CREATE prompt mission_control" in text
    assert "UPDATE memory [NERD-AGENCY memory:safety]" in text
    assert "memory-id" not in text
    assert "payload" not in text


def test_knowledge_seed_collects_existing_docs_with_stable_hashed_filenames(tmp_path):
    seed = load_module("agency_openwebui_seed_knowledge_docs", SEED_PATH)
    stack_dir = tmp_path / "stack"
    staging_dir = tmp_path / "staging"
    (stack_dir / "docs").mkdir(parents=True)
    (staging_dir / "docs" / "nerd_inventory").mkdir(parents=True)
    (stack_dir / "README.md").write_text("# stack\n", encoding="utf-8")
    (stack_dir / "nerd-agency.manifest.yaml").write_text(
        "id: nerd\n",
        encoding="utf-8",
    )
    (staging_dir / "docs" / "nerd_inventory" / "mission-control-stack.md").write_text(
        "# mission\n",
        encoding="utf-8",
    )

    docs = seed.mission_control_knowledge_documents(stack_dir, staging_dir)
    filenames = {doc.filename for doc in docs}

    assert len(docs) == 3
    assert all(filename.startswith("nerd-agency--") for filename in filenames)
    assert any(filename.endswith(".md") for filename in filenames)
    assert any(
        "manifest" in filename and filename.endswith(".yaml") for filename in filenames
    )
    assert docs == seed.mission_control_knowledge_documents(stack_dir, staging_dir)


def test_knowledge_seed_collects_brain_report_when_present(tmp_path):
    seed = load_module("agency_openwebui_seed_brain_docs", SEED_PATH)
    stack_dir = tmp_path / "stack"
    staging_dir = tmp_path / "staging"
    inventory_dir = staging_dir / "docs" / "nerd_inventory"
    stack_dir.mkdir(parents=True)
    inventory_dir.mkdir(parents=True)
    (inventory_dir / "nerd-method-brain.md").write_text(
        "# NERD-METHOD Brain\n",
        encoding="utf-8",
    )
    (inventory_dir / "workspace-map.md").write_text(
        "# Workspace Map\n",
        encoding="utf-8",
    )

    docs = seed.mission_control_knowledge_documents(stack_dir, staging_dir)
    filenames = {doc.filename for doc in docs}

    assert len(docs) == 2
    assert any("nerd-method-brain" in filename for filename in filenames)
    assert any("workspace-map" in filename for filename in filenames)


def test_knowledge_base_description_names_shared_brain_surfaces():
    seed = load_module("agency_openwebui_seed_knowledge_description", SEED_PATH)

    description = seed.mission_control_knowledge_base().description

    for phrase in (
        "NERD-METHOD shared brain",
        "GitNexus",
        "Obsidian",
        "NotebookLM",
        "n8n",
    ):
        assert phrase in description


def test_knowledge_base_upsert_plan_uses_name_as_identity():
    seed = load_module("agency_openwebui_seed_knowledge_plan", SEED_PATH)
    desired = seed.mission_control_knowledge_base()

    create_plan = seed.plan_knowledge_base_upsert([], desired)
    keep_plan = seed.plan_knowledge_base_upsert(
        [
            {
                "id": "knowledge-id",
                "name": desired.name,
                "description": desired.description,
            }
        ],
        desired,
    )
    update_plan = seed.plan_knowledge_base_upsert(
        [{"id": "knowledge-id", "name": desired.name, "description": "old"}],
        desired,
    )

    assert create_plan.action == "create"
    assert create_plan.kind == "knowledge"
    assert create_plan.key == desired.name
    assert keep_plan.action == "keep"
    assert keep_plan.object_id == "knowledge-id"
    assert update_plan.action == "update"
    assert update_plan.object_id == "knowledge-id"


def test_knowledge_file_plan_adds_missing_docs_by_filename(tmp_path):
    seed = load_module("agency_openwebui_seed_knowledge_file_plan", SEED_PATH)
    doc_a = tmp_path / "a.md"
    doc_b = tmp_path / "b.md"
    doc_a.write_text("alpha", encoding="utf-8")
    doc_b.write_text("beta", encoding="utf-8")
    docs = [
        seed.KnowledgeDocument.from_path(doc_a, source_root=tmp_path),
        seed.KnowledgeDocument.from_path(doc_b, source_root=tmp_path),
    ]

    plan = seed.plan_knowledge_file_adds(
        [{"filename": docs[0].filename}],
        docs,
    )

    assert [doc.filename for doc in plan] == [docs[1].filename]


def test_knowledge_requests_allow_large_inventory_embedding_timeout():
    seed = load_module("agency_openwebui_seed_timeout", SEED_PATH)

    assert seed.KNOWLEDGE_REQUEST_TIMEOUT_SECONDS >= 180
