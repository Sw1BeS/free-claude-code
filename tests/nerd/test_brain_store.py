from __future__ import annotations

import json
import sqlite3


def test_brain_intake_writes_db_backed_candidate_and_registry(tmp_path):
    from scripts.nerd.autonomous.intake import write_brain_intake
    from scripts.nerd.brain.store import build_brain_store_snapshot, brain_db_path

    canonical_root = tmp_path / "nerd-method"
    result = write_brain_intake(
        text="Remember this architecture decision. api_key=super-secret",
        canonical_root=canonical_root,
        source="operator",
    )

    db_path = brain_db_path(canonical_root)
    assert db_path.is_file()
    assert result["brain_store"]["db_path"] == str(db_path)
    assert result["brain_store"]["candidate_id"] == result["candidate"]["id"]

    snapshot = build_brain_store_snapshot(canonical_root)
    assert snapshot["status"] == "present"
    assert snapshot["source_count"] == 1
    assert snapshot["episode_count"] == 1
    assert snapshot["candidate_count"] == 1
    assert snapshot["recent_candidates"][0]["id"] == result["candidate"]["id"]

    registry = json.loads((canonical_root / "registry" / "brain-store.json").read_text(encoding="utf-8"))
    assert registry["candidate_count"] == 1

    with sqlite3.connect(db_path) as connection:
        body = connection.execute("SELECT body FROM episodes").fetchone()[0]
    assert "super-secret" not in body
    assert "api_key=[redacted]" in body


def test_promote_memory_candidate_updates_brain_store(tmp_path):
    from scripts.nerd.autonomous.intake import promote_memory_candidate, write_brain_intake
    from scripts.nerd.brain.store import build_brain_store_snapshot

    canonical_root = tmp_path / "nerd-method"
    intake = write_brain_intake(
        text="Promote this durable knowledge.",
        canonical_root=canonical_root,
        source="manual",
    )

    promote_memory_candidate(
        intake["candidate"]["id"],
        canonical_root=canonical_root,
        reviewer="operator",
    )

    snapshot = build_brain_store_snapshot(canonical_root)
    assert snapshot["approved_count"] == 1
    assert snapshot["recent_candidates"][0]["promotion_status"] == "approved"


def test_promote_memory_candidate_rejects_artifact_without_db_candidate(tmp_path):
    import pytest

    from scripts.nerd.autonomous.intake import promote_memory_candidate, write_brain_intake
    from scripts.nerd.brain.store import brain_db_path

    canonical_root = tmp_path / "nerd-method"
    intake = write_brain_intake(
        text="Legacy artifact exists but DB row is missing.",
        canonical_root=canonical_root,
        source="manual",
    )
    candidate_id = intake["candidate"]["id"]
    candidate_path = intake["paths"]["candidate"]
    knowledge_path = canonical_root / "memory" / "knowledge" / f"{candidate_id}.md"
    with sqlite3.connect(brain_db_path(canonical_root)) as connection:
        connection.execute("DELETE FROM memory_candidates WHERE id = ?", (candidate_id,))

    with pytest.raises(ValueError, match="unknown memory candidate in brain store"):
        promote_memory_candidate(
            candidate_id,
            canonical_root=canonical_root,
            reviewer="operator",
        )

    artifact = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert artifact["promotion_status"] == "candidate"
    assert "approved_at" not in artifact
    assert not knowledge_path.exists()


def test_mark_candidate_promoted_does_not_audit_missing_db_candidate(tmp_path):
    import pytest

    from scripts.nerd.brain.store import brain_db_path, ensure_brain_store, mark_candidate_promoted

    canonical_root = tmp_path / "nerd-method"
    ensure_brain_store(canonical_root)

    with pytest.raises(ValueError, match="unknown memory candidate in brain store"):
        mark_candidate_promoted(
            "missing-candidate",
            canonical_root=canonical_root,
            reviewer="operator",
            knowledge_path=canonical_root / "memory" / "knowledge" / "missing.md",
            approved_at="2026-05-26T00:00:00Z",
        )

    with sqlite3.connect(brain_db_path(canonical_root)) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert audit_count == 0


def test_sync_memory_records_imports_existing_json_records(tmp_path):
    from scripts.nerd.autonomous.intake import write_brain_intake
    from scripts.nerd.brain.store import build_brain_store_snapshot, sync_memory_records

    canonical_root = tmp_path / "nerd-method"
    write_brain_intake(
        text="Sync existing JSON memory.",
        canonical_root=canonical_root,
        source="telegram",
    )

    synced = sync_memory_records(canonical_root)
    snapshot = build_brain_store_snapshot(canonical_root)

    assert synced["ingested"] == 1
    assert snapshot["episode_count"] == 1
    assert snapshot["candidate_count"] == 1


def test_brain_graph_snapshot_reports_missing_store_without_creating_db(tmp_path):
    from scripts.nerd.brain.store import brain_db_path, build_brain_graph_snapshot

    canonical_root = tmp_path / "nerd-method"
    graph = build_brain_graph_snapshot(canonical_root)

    assert graph["status"] == "missing"
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["harness"]["db_path"] == str(brain_db_path(canonical_root))
    assert graph["harness"]["candidate_count"] == 0
    assert graph["harness"]["mirror_registry_path"] == str(
        canonical_root / "registry" / "brain-store.json"
    )
    assert not brain_db_path(canonical_root).exists()


def test_brain_graph_snapshot_uses_db_rows_and_approved_knowledge_nodes(tmp_path):
    from scripts.nerd.autonomous.intake import promote_memory_candidate, write_brain_intake
    from scripts.nerd.brain.store import brain_db_path, build_brain_graph_snapshot

    canonical_root = tmp_path / "nerd-method"
    intake = write_brain_intake(
        text="Graphable knowledge about the brain graph API.",
        canonical_root=canonical_root,
        source="operator",
    )
    promote_memory_candidate(
        intake["candidate"]["id"],
        canonical_root=canonical_root,
        reviewer="operator",
    )

    graph = build_brain_graph_snapshot(canonical_root)
    nodes = {node["id"]: node for node in graph["nodes"]}
    edge_relations = {edge["relation"] for edge in graph["edges"]}

    assert graph["status"] == "present"
    assert nodes["brain-store-db"]["type"] == "store"
    assert nodes["source_operator"]["type"] == "source"
    assert nodes[intake["brain_store"]["episode_id"]]["type"] == "episode"
    assert nodes[intake["candidate"]["id"]]["type"] == "candidate"
    assert nodes[f"knowledge_{intake['candidate']['id']}"]["type"] == "knowledge"
    assert nodes["brain-store-db"]["provenance"] == str(brain_db_path(canonical_root))
    assert nodes["source_operator"]["provenance"] == "source_operator"
    assert not isinstance(nodes[intake["candidate"]["id"]]["provenance"], dict)
    assert graph["harness"]["approved_count"] == 1
    assert {"has_source", "captured", "yielded", "promoted"} <= edge_relations


def test_search_brain_store_uses_fts_and_handles_invalid_query(tmp_path):
    from scripts.nerd.autonomous.intake import write_brain_intake
    from scripts.nerd.brain.store import search_brain_store

    canonical_root = tmp_path / "nerd-method"
    intake = write_brain_intake(
        text="Recall lens should find durable sqlite FTS memory records.",
        canonical_root=canonical_root,
        source="operator",
    )

    payload = search_brain_store("durable", canonical_root)

    assert payload["status"] == "ok"
    assert payload["fts_status"] == "enabled"
    assert payload["results"][0]["candidate_id"] == intake["candidate"]["id"]
    assert payload["results"][0]["source_id"] == "source_operator"
    assert "excerpt" in payload["results"][0]

    invalid = search_brain_store('"unterminated', canonical_root)
    assert invalid["status"] == "invalid_query"
    assert invalid["results"] == []


def test_search_brain_store_missing_or_empty_query_is_non_throwing(tmp_path):
    from scripts.nerd.brain.store import search_brain_store

    missing = search_brain_store("brain", tmp_path / "missing")
    empty = search_brain_store("", tmp_path / "missing")

    assert missing["status"] == "missing"
    assert missing["results"] == []
    assert empty["status"] == "missing"
    assert empty["results"] == []


def test_brain_context_pack_returns_agent_ready_markdown(tmp_path):
    from scripts.nerd.autonomous.intake import write_brain_intake
    from scripts.nerd.brain.store import build_brain_context_pack

    canonical_root = tmp_path / "nerd-method"
    intake = write_brain_intake(
        text="Durable context pack memory with token=super-secret should be redacted.",
        canonical_root=canonical_root,
        source="operator",
    )

    pack = build_brain_context_pack("Durable", canonical_root, limit=4)

    assert pack["status"] == "present"
    assert pack["recall_status"] == "ok"
    assert pack["fts_status"] == "enabled"
    assert pack["recall"][0]["candidate_id"] == intake["candidate"]["id"]
    assert "NERD OS Second Brain Context Pack" in pack["markdown"]
    assert intake["candidate"]["id"] in pack["markdown"]
    assert "token=[redacted]" in pack["markdown"]
    assert "super-secret" not in pack["markdown"]
    assert "raw" not in pack["graph_nodes"][0]


def test_brain_context_pack_missing_store_is_non_throwing(tmp_path):
    from scripts.nerd.brain.store import brain_db_path, build_brain_context_pack

    canonical_root = tmp_path / "nerd-method"
    pack = build_brain_context_pack("", canonical_root)

    assert pack["status"] == "missing"
    assert pack["recall_status"] == "missing"
    assert pack["recall"] == []
    assert pack["db_path"] == str(brain_db_path(canonical_root))
    assert "No recall records available." in pack["markdown"]
    assert not brain_db_path(canonical_root).exists()


def test_brain_candidate_detail_joins_candidate_episode_source_and_audit(tmp_path):
    from scripts.nerd.autonomous.intake import write_brain_intake
    from scripts.nerd.brain.store import brain_candidate_detail

    canonical_root = tmp_path / "nerd-method"
    intake = write_brain_intake(
        text="Candidate detail should expose source and audit provenance.",
        canonical_root=canonical_root,
        source="operator",
    )
    candidate_id = intake["candidate"]["id"]

    detail = brain_candidate_detail(candidate_id, canonical_root)

    assert detail["id"] == candidate_id
    assert detail["candidate"]["id"] == candidate_id
    assert detail["episode"]["id"] == intake["brain_store"]["episode_id"]
    assert detail["source"]["id"] == "source_operator"
    assert detail["audit_log"][0]["event_type"] == "memory_candidate_ingested"


def test_brain_candidate_detail_rejects_empty_or_unknown_id(tmp_path):
    import pytest

    from scripts.nerd.brain.store import brain_candidate_detail, ensure_brain_store

    canonical_root = tmp_path / "nerd-method"
    ensure_brain_store(canonical_root)

    with pytest.raises(ValueError, match="candidate_id is required"):
        brain_candidate_detail("", canonical_root)
    with pytest.raises(ValueError, match="unknown memory candidate"):
        brain_candidate_detail("missing", canonical_root)
