import importlib.util
import json
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


def test_knowledge_seed_collects_existing_docs_with_stable_filenames(tmp_path):
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


def test_knowledge_document_filename_is_stable_when_content_changes(tmp_path):
    seed = load_module("agency_openwebui_seed_stable_filename", SEED_PATH)
    report = tmp_path / "docs" / "nerd_inventory" / "nerd-method-brain.md"
    report.parent.mkdir(parents=True)
    report.write_text("# NERD-METHOD Brain\nGenerated: one\n", encoding="utf-8")

    first = seed.KnowledgeDocument.from_path(report, source_root=tmp_path)
    report.write_text("# NERD-METHOD Brain\nGenerated: two\n", encoding="utf-8")
    second = seed.KnowledgeDocument.from_path(report, source_root=tmp_path)

    assert first.filename == second.filename
    assert first.filename == "nerd-agency--docs--nerd_inventory--nerd-method-brain.md"
    assert first.content_sha256 != second.content_sha256


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

    assert len(docs) == 1
    assert any("nerd-method-brain" in filename for filename in filenames)
    assert not any("workspace-map" in filename for filename in filenames)


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


def test_knowledge_file_plan_creates_missing_docs_by_filename(tmp_path):
    seed = load_module("agency_openwebui_seed_knowledge_file_plan", SEED_PATH)
    doc_a = tmp_path / "a.md"
    doc_b = tmp_path / "b.md"
    doc_a.write_text("alpha", encoding="utf-8")
    doc_b.write_text("beta", encoding="utf-8")
    docs = [
        seed.KnowledgeDocument.from_path(doc_a, source_root=tmp_path),
        seed.KnowledgeDocument.from_path(doc_b, source_root=tmp_path),
    ]

    plan = seed.plan_knowledge_file_changes(
        [
            {
                "id": "file-a",
                "filename": docs[0].filename,
                "meta": {"data": {"content_sha256": docs[0].content_sha256}},
            }
        ],
        docs,
    )

    actions = {(change.action, change.key): change for change in plan}

    assert actions[("keep", docs[0].filename)].object_id == "file-a"
    assert actions[("create", docs[1].filename)].object_id is None


def test_knowledge_file_plan_keeps_attached_doc_with_matching_digest(tmp_path):
    seed = load_module("agency_openwebui_seed_knowledge_file_plan_keep", SEED_PATH)
    doc_path = tmp_path / "report.md"
    doc_path.write_text("current report", encoding="utf-8")
    doc = seed.KnowledgeDocument.from_path(doc_path, source_root=tmp_path)

    plan = seed.plan_knowledge_file_changes(
        [
            {
                "id": "file-id",
                "filename": doc.filename,
                "meta": {"data": {"content_sha256": doc.content_sha256}},
            }
        ],
        [doc],
    )

    assert len(plan) == 1
    assert plan[0].kind == "knowledge_file"
    assert plan[0].action == "keep"
    assert plan[0].key == doc.filename
    assert plan[0].object_id == "file-id"


def test_knowledge_file_plan_keeps_same_digest_under_old_filename(tmp_path):
    seed = load_module("agency_openwebui_seed_digest_alias", SEED_PATH)
    doc_path = tmp_path / "new-name.md"
    doc_path.write_text("same content", encoding="utf-8")
    doc = seed.KnowledgeDocument.from_path(doc_path, source_root=tmp_path)

    plan = seed.plan_knowledge_file_changes(
        [
            {
                "id": "file-id",
                "filename": "old-name.md",
                "meta": {"data": {"content_sha256": doc.content_sha256}},
            }
        ],
        [doc],
    )

    assert len(plan) == 1
    assert plan[0].kind == "knowledge_file"
    assert plan[0].action == "keep"
    assert plan[0].key == doc.filename
    assert plan[0].object_id == "file-id"


def test_knowledge_file_plan_updates_stale_filename_by_source_path(tmp_path):
    seed = load_module("agency_openwebui_seed_source_alias", SEED_PATH)
    doc_path = tmp_path / "stable-name.md"
    doc_path.write_text("fresh content", encoding="utf-8")
    doc = seed.KnowledgeDocument.from_path(doc_path, source_root=tmp_path)

    plan = seed.plan_knowledge_file_changes(
        [
            {
                "id": "stale-id",
                "filename": "old-hashed-name.md",
                "meta": {"data": {"source_path": str(doc.path)}},
            }
        ],
        [doc],
    )

    assert len(plan) == 1
    assert plan[0].kind == "knowledge_file"
    assert plan[0].action == "update"
    assert plan[0].key == doc.filename
    assert plan[0].object_id == "stale-id"


def test_knowledge_file_plan_updates_attached_doc_with_missing_or_old_digest(tmp_path):
    seed = load_module("agency_openwebui_seed_knowledge_file_plan_update", SEED_PATH)
    missing_digest_path = tmp_path / "missing.md"
    old_digest_path = tmp_path / "old.md"
    missing_digest_path.write_text("missing digest", encoding="utf-8")
    old_digest_path.write_text("new content", encoding="utf-8")
    docs = [
        seed.KnowledgeDocument.from_path(missing_digest_path, source_root=tmp_path),
        seed.KnowledgeDocument.from_path(old_digest_path, source_root=tmp_path),
    ]

    plan = seed.plan_knowledge_file_changes(
        [
            {"id": "missing-id", "filename": docs[0].filename},
            {
                "id": "old-id",
                "filename": docs[1].filename,
                "meta": {"data": {"content_sha256": "old-digest"}},
            },
        ],
        docs,
    )

    actions = {(change.action, change.key): change for change in plan}

    assert actions[("update", docs[0].filename)].object_id == "missing-id"
    assert actions[("update", docs[1].filename)].object_id == "old-id"


def test_file_digest_helper_reads_nested_openwebui_metadata():
    seed = load_module("agency_openwebui_seed_digest_helper", SEED_PATH)

    assert (
        seed.file_content_sha256(
            {"meta": {"data": {"content_sha256": "abc123"}}}
        )
        == "abc123"
    )
    assert (
        seed.file_content_sha256(
            {"metadata": {"content_sha256": "def456"}}
        )
        == "def456"
    )
    assert seed.file_content_sha256({"meta": {"data": {}}}) is None


def test_file_source_path_helper_reads_nested_openwebui_metadata():
    seed = load_module("agency_openwebui_seed_source_path_helper", SEED_PATH)

    assert (
        seed.file_source_path({"meta": {"data": {"source_path": "/tmp/a.md"}}})
        == "/tmp/a.md"
    )
    assert seed.file_source_path({"meta": {"data": {}}}) is None


def test_apply_knowledge_documents_updates_stale_attachment_and_keeps_current(
    tmp_path,
    monkeypatch,
):
    seed = load_module("agency_openwebui_seed_apply_docs", SEED_PATH)
    current_path = tmp_path / "current.md"
    stale_path = tmp_path / "stale.md"
    current_path.write_text("current", encoding="utf-8")
    stale_path.write_text("fresh", encoding="utf-8")
    docs = [
        seed.KnowledgeDocument.from_path(current_path, source_root=tmp_path),
        seed.KnowledgeDocument.from_path(stale_path, source_root=tmp_path),
    ]
    monkeypatch.setattr(seed, "mission_control_knowledge_documents", lambda: docs)

    class FakeClient:
        def __init__(self):
            self.added = []
            self.replaced = []

        def list_knowledge_files(self, knowledge_id):
            assert knowledge_id == "knowledge-id"
            return [
                {
                    "id": "current-id",
                    "filename": docs[0].filename,
                    "meta": {"data": {"content_sha256": docs[0].content_sha256}},
                },
                {
                    "id": "stale-id",
                    "filename": docs[1].filename,
                    "meta": {"data": {"content_sha256": "old"}},
                },
            ]

        def add_document_to_knowledge(self, knowledge_id, doc):
            self.added.append((knowledge_id, doc.filename))

        def replace_document_in_knowledge(self, knowledge_id, doc, file_id):
            self.replaced.append((knowledge_id, doc.filename, file_id))

    client = FakeClient()

    changes = seed.apply_knowledge_documents(client, "knowledge-id")

    actions = {(change.action, change.key) for change in changes}
    assert ("keep", docs[0].filename) in actions
    assert ("update", docs[1].filename) in actions
    assert client.added == []
    assert client.replaced == [("knowledge-id", docs[1].filename, "stale-id")]


def test_add_document_to_knowledge_reuses_only_matching_global_digest(tmp_path):
    seed = load_module("agency_openwebui_seed_add_doc", SEED_PATH)
    doc_path = tmp_path / "report.md"
    doc_path.write_text("current", encoding="utf-8")
    doc = seed.KnowledgeDocument.from_path(doc_path, source_root=tmp_path)

    class FakeClient(seed.OpenWebUISeedClient):
        def __init__(self):
            super().__init__("http://openwebui.test", "token")
            self.uploaded = []
            self.requests = []

        def _request(self, method, path, payload=None):
            self.requests.append((method, path, payload))
            if method == "GET":
                return [
                    {
                        "id": "old-id",
                        "filename": doc.filename,
                        "meta": {"data": {"content_sha256": "old"}},
                    },
                    {
                        "id": "matching-id",
                        "filename": doc.filename,
                        "meta": {"data": {"content_sha256": doc.content_sha256}},
                    },
                ]
            return {"ok": True}

        def upload_document(self, doc):
            self.uploaded.append(doc.filename)
            return "uploaded-id"

    client = FakeClient()

    file_id = client.add_document_to_knowledge("knowledge-id", doc)

    assert file_id == "matching-id"
    assert client.uploaded == []
    assert (
        "POST",
        "/api/v1/knowledge/knowledge-id/file/add",
        {"file_id": "matching-id"},
    ) in client.requests


def test_add_document_to_knowledge_treats_duplicate_content_as_existing(tmp_path):
    seed = load_module("agency_openwebui_seed_duplicate_doc", SEED_PATH)
    doc_path = tmp_path / "report.md"
    doc_path.write_text("current", encoding="utf-8")
    doc = seed.KnowledgeDocument.from_path(doc_path, source_root=tmp_path)

    class FakeClient(seed.OpenWebUISeedClient):
        def __init__(self):
            super().__init__("http://openwebui.test", "token")
            self.uploaded = []

        def _request(self, method, path, payload=None):
            if method == "GET":
                return []
            raise RuntimeError(
                "Open WebUI request failed: 400 http://openwebui.test: "
                '{"detail":"400: Duplicate content detected. '
                'Please provide unique content to proceed."}'
            )

        def upload_document(self, doc):
            self.uploaded.append(doc.filename)
            return "uploaded-id"

    client = FakeClient()

    file_id = client.add_document_to_knowledge("knowledge-id", doc)

    assert file_id == "uploaded-id"
    assert client.uploaded == [doc.filename]


def test_upload_document_includes_seed_metadata_and_digest(tmp_path, monkeypatch):
    seed = load_module("agency_openwebui_seed_upload_metadata", SEED_PATH)
    doc_path = tmp_path / "report.md"
    doc_path.write_text("current", encoding="utf-8")
    doc = seed.KnowledgeDocument.from_path(doc_path, source_root=tmp_path)
    captured = {}

    def fake_request_multipart_json(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return {"id": "uploaded-id"}

    monkeypatch.setattr(seed, "request_multipart_json", fake_request_multipart_json)

    file_id = seed.OpenWebUISeedClient(
        "http://openwebui.test",
        "token",
    ).upload_document(doc)

    metadata = json.loads(captured["fields"]["metadata"])
    assert file_id == "uploaded-id"
    assert metadata == {
        "nerd_agency_seed": True,
        "source_path": str(doc.path),
        "content_sha256": doc.content_sha256,
    }


def test_knowledge_requests_allow_large_inventory_embedding_timeout():
    seed = load_module("agency_openwebui_seed_timeout", SEED_PATH)

    assert seed.KNOWLEDGE_REQUEST_TIMEOUT_SECONDS >= 180
