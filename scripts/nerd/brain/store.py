from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.nerd.autonomous.models import (
    DEFAULT_CANONICAL_ROOT,
    InboxItem,
    MemoryArtifact,
    Task,
    read_json,
    to_pretty_json,
    write_json,
)

SCHEMA_VERSION = 1
DEFAULT_DB_RELATIVE_PATH = Path("brain") / "brain.sqlite"
SECRET_PATTERNS = (
    re.compile(r"\b(token|api[_-]?key|secret|password)=([^\s&]+)", re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{12,})\b"),
    re.compile(r"\b(ghp_[A-Za-z0-9_]{20,})\b"),
)


def record_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")


def iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def brain_db_path(canonical_root: Path = DEFAULT_CANONICAL_ROOT) -> Path:
    return Path(canonical_root) / DEFAULT_DB_RELATIVE_PATH


def redact_brain_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            redacted = pattern.sub(r"\1=[redacted]", redacted)
        else:
            redacted = pattern.sub("[redacted-secret]", redacted)
    return redacted


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _safe_read_json(path: Path, default: object) -> object:
    try:
        return read_json(path, default)
    except (json.JSONDecodeError, OSError):
        return default


def _safe_record_array(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _source_id(source: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", source.strip().lower()).strip("_")
    return f"source_{normalized or 'unknown'}"


def _content_hash(*parts: object) -> str:
    body = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def ensure_brain_store(canonical_root: Path = DEFAULT_CANONICAL_ROOT) -> Path:
    db_path = brain_db_path(canonical_root)
    with _connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sources (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              kind TEXT NOT NULL,
              status TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS episodes (
              id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL REFERENCES sources(id),
              kind TEXT NOT NULL,
              body TEXT NOT NULL,
              content_hash TEXT NOT NULL UNIQUE,
              privacy TEXT NOT NULL,
              risk TEXT NOT NULL,
              created_at TEXT NOT NULL,
              source_url TEXT,
              raw_path TEXT,
              metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_candidates (
              id TEXT PRIMARY KEY,
              episode_id TEXT NOT NULL REFERENCES episodes(id),
              task_id TEXT,
              title TEXT NOT NULL,
              summary TEXT NOT NULL,
              status TEXT NOT NULL,
              promotion_status TEXT NOT NULL,
              risk TEXT NOT NULL,
              privacy TEXT NOT NULL,
              created_at TEXT NOT NULL,
              artifact_path TEXT,
              markdown_path TEXT,
              metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
              id TEXT PRIMARY KEY,
              event_type TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            ("canonical_root", str(Path(canonical_root))),
        )
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS brain_fts
                USING fts5(candidate_id UNINDEXED, title, summary, body)
                """
            )
        except sqlite3.OperationalError:
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                ("fts_status", "unavailable"),
            )
        else:
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                ("fts_status", "enabled"),
            )
    return db_path


def ingest_brain_record(
    *,
    text: str,
    source: str,
    title: str,
    summary: str,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    kind: str = "memory_candidate",
    source_url: str | None = None,
    raw_path: str | None = None,
    privacy: str = "project",
    risk: str = "unknown",
    task_id: str | None = None,
    candidate_id: str | None = None,
    artifact_path: str | None = None,
    markdown_path: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    db_path = ensure_brain_store(canonical_root)
    now = iso_now()
    source_id = _source_id(source)
    body = redact_brain_text(text.strip())
    digest = _content_hash(source_id, body, source_url, raw_path)
    episode_id = f"episode_{digest[:18]}"
    candidate_id = candidate_id or f"memory_candidate_{record_stamp()}"
    metadata = metadata or {}

    with _connect(db_path) as connection:
        candidate_exists = (
            connection.execute(
                "SELECT 1 FROM memory_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            is not None
        )
        connection.execute(
            """
            INSERT INTO sources(id, name, kind, status, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              kind=excluded.kind,
              status=excluded.status,
              metadata_json=excluded.metadata_json,
              updated_at=excluded.updated_at
            """,
            (
                source_id,
                source,
                "operator" if source in {"manual", "operator", "web"} else "integration",
                "active",
                _json_dumps({"latest_source_url": source_url, "latest_raw_path": raw_path}),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO episodes(
              id, source_id, kind, body, content_hash, privacy, risk,
              created_at, source_url, raw_path, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode_id,
                source_id,
                kind,
                body,
                digest,
                privacy,
                risk,
                now,
                source_url,
                raw_path,
                _json_dumps(metadata),
            ),
        )
        connection.execute(
            """
            INSERT INTO memory_candidates(
              id, episode_id, task_id, title, summary, status, promotion_status,
              risk, privacy, created_at, artifact_path, markdown_path, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              episode_id=excluded.episode_id,
              task_id=excluded.task_id,
              title=excluded.title,
              summary=excluded.summary,
              status=excluded.status,
              promotion_status=excluded.promotion_status,
              risk=excluded.risk,
              privacy=excluded.privacy,
              artifact_path=excluded.artifact_path,
              markdown_path=excluded.markdown_path,
              metadata_json=excluded.metadata_json
            """,
            (
                candidate_id,
                episode_id,
                task_id,
                title,
                redact_brain_text(summary),
                "active",
                "candidate",
                risk,
                privacy,
                now,
                artifact_path,
                markdown_path,
                _json_dumps(metadata),
            ),
        )
        try:
            if candidate_exists:
                connection.execute("DELETE FROM brain_fts WHERE candidate_id = ?", (candidate_id,))
            connection.execute(
                "INSERT INTO brain_fts(candidate_id, title, summary, body) VALUES (?, ?, ?, ?)",
                (candidate_id, title, redact_brain_text(summary), body),
            )
        except sqlite3.OperationalError:
            pass
        if not candidate_exists:
            connection.execute(
                "INSERT INTO audit_log(id, event_type, subject_id, created_at, payload_json) VALUES (?, ?, ?, ?, ?)",
                (
                    f"audit_{record_stamp()}",
                    "memory_candidate_ingested",
                    candidate_id,
                    now,
                    _json_dumps({"episode_id": episode_id, "source_id": source_id}),
                ),
            )

    registry_path = write_brain_store_registry(canonical_root)
    return {
        "db_path": str(db_path),
        "registry_path": str(registry_path),
        "source_id": source_id,
        "episode_id": episode_id,
        "candidate_id": candidate_id,
        "content_hash": digest,
    }


def ingest_intake_artifact(
    item: InboxItem,
    task: Task,
    artifact: MemoryArtifact,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    candidate_markdown_path: Path | None = None,
) -> dict[str, object]:
    return ingest_brain_record(
        text=item.raw_text,
        source=item.source,
        title=task.title,
        summary=artifact.summary,
        canonical_root=canonical_root,
        kind=item.detected_type,
        source_url=item.source_url,
        raw_path=item.raw_path,
        privacy=item.privacy,
        risk=item.risk,
        task_id=task.id,
        candidate_id=artifact.id,
        artifact_path=artifact.path,
        markdown_path=str(candidate_markdown_path) if candidate_markdown_path else None,
        metadata={
            "inbox_id": item.id,
            "tags": item.tags,
            "department": task.department,
            "assigned_agent_role": task.assigned_agent_role,
            "model_profile": task.model_profile,
        },
    )


def mark_candidate_promoted(
    candidate_id: str,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    reviewer: str,
    knowledge_path: Path,
    approved_at: str,
) -> dict[str, object]:
    db_path = ensure_brain_store(canonical_root)
    with _connect(db_path) as connection:
        result = connection.execute(
            """
            UPDATE memory_candidates
            SET promotion_status = ?, status = ?, markdown_path = ?
            WHERE id = ?
            """,
            ("approved", "active", str(knowledge_path), candidate_id),
        )
        if result.rowcount != 1:
            raise ValueError(f"unknown memory candidate in brain store: {candidate_id}")
        connection.execute(
            "INSERT INTO audit_log(id, event_type, subject_id, created_at, payload_json) VALUES (?, ?, ?, ?, ?)",
            (
                f"audit_{record_stamp()}",
                "memory_candidate_promoted",
                candidate_id,
                approved_at,
                _json_dumps({"reviewer": reviewer, "knowledge_path": str(knowledge_path)}),
            ),
        )
    registry_path = write_brain_store_registry(canonical_root)
    return {"db_path": str(db_path), "registry_path": str(registry_path)}


def brain_candidate_exists(
    candidate_id: str,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> bool:
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id:
        return False
    db_path = brain_db_path(canonical_root)
    if not db_path.is_file():
        return False
    ensure_brain_store(canonical_root)
    with _connect(db_path) as connection:
        return (
            connection.execute(
                "SELECT 1 FROM memory_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            is not None
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    payload = dict(row)
    for key in ("metadata_json",):
        if key in payload:
            try:
                payload[key.removesuffix("_json")] = json.loads(str(payload.pop(key)))
            except json.JSONDecodeError:
                payload[key.removesuffix("_json")] = {}
    return payload


def _metadata_value(connection: sqlite3.Connection, key: str, default: str = "") -> str:
    row = connection.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return str(row[0] or default)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _scalar(connection: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> int:
    row = connection.execute(sql, params).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def _brain_store_harness(
    canonical_root: Path,
    db_path: Path,
    *,
    status: str,
    connection: sqlite3.Connection | None = None,
) -> dict[str, object]:
    registry_path = Path(canonical_root) / "registry" / "brain-store.json"
    if connection is None:
        return {
            "status": status,
            "db_path": str(db_path),
            "fts_status": "missing",
            "source_count": 0,
            "episode_count": 0,
            "candidate_count": 0,
            "approved_count": 0,
            "audit_count": 0,
            "last_episode_at": None,
            "mirror_registry_path": str(registry_path),
        }
    last_episode = connection.execute(
        "SELECT created_at FROM episodes ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    return {
        "status": status,
        "db_path": str(db_path),
        "fts_status": _metadata_value(connection, "fts_status", "unknown"),
        "source_count": _scalar(connection, "SELECT COUNT(*) FROM sources"),
        "episode_count": _scalar(connection, "SELECT COUNT(*) FROM episodes"),
        "candidate_count": _scalar(connection, "SELECT COUNT(*) FROM memory_candidates"),
        "approved_count": _scalar(
            connection,
            "SELECT COUNT(*) FROM memory_candidates WHERE promotion_status = ?",
            ("approved",),
        ),
        "audit_count": _scalar(connection, "SELECT COUNT(*) FROM audit_log"),
        "last_episode_at": str(last_episode[0]) if last_episode else None,
        "mirror_registry_path": str(registry_path),
    }


def _node(
    node_id: str,
    label: str,
    kind: str,
    *,
    status: str = "present",
    risk: str = "unknown",
    detail: str | None = None,
    metric: object | None = None,
    raw: dict[str, object] | None = None,
    x: int | None = None,
    y: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": node_id,
        "label": label,
        "name": label,
        "kind": kind,
        "type": kind,
        "status": status,
        "risk": risk,
    }
    if detail:
        payload["detail"] = detail
    if metric is not None:
        payload["metric"] = metric
    if raw:
        payload["raw"] = raw
        provenance = (
            raw.get("path")
            or raw.get("db_path")
            or raw.get("source_name")
            or raw.get("source_id")
            or raw.get("id")
        )
        if provenance:
            payload["provenance"] = str(provenance)
    if x is not None:
        payload["x"] = x
    if y is not None:
        payload["y"] = y
    return payload


def build_brain_graph_snapshot(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    *,
    limit: int = 12,
) -> dict[str, object]:
    db_path = brain_db_path(canonical_root)
    if not db_path.is_file():
        return {
            "status": "missing",
            "nodes": [],
            "edges": [],
            "harness": _brain_store_harness(canonical_root, db_path, status="missing"),
        }

    ensure_brain_store(canonical_root)
    limit = max(1, min(int(limit), 100))
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(payload: dict[str, object]) -> None:
        node_id = str(payload.get("id") or "")
        if node_id and node_id not in seen_nodes:
            seen_nodes.add(node_id)
            nodes.append(payload)

    def add_edge(source: str, target: str, relation: str, status: str = "present") -> None:
        edge_key = (source, target, relation)
        if source in seen_nodes and target in seen_nodes and edge_key not in seen_edges:
            seen_edges.add(edge_key)
            edges.append(
                {
                    "id": f"{source}:{relation}:{target}",
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "status": status,
                }
            )

    with _connect(db_path) as connection:
        harness = _brain_store_harness(canonical_root, db_path, status="present", connection=connection)
        add_node(
            _node(
                "brain-store-db",
                "NERD Brain Store",
                "store",
                status="present",
                risk="medium",
                detail=str(db_path),
                metric=harness["candidate_count"],
                raw={"db_path": str(db_path), "schema_version": SCHEMA_VERSION},
                x=0,
                y=0,
            )
        )
        source_rows = [
            _row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, name, kind, status, created_at, updated_at, metadata_json
                FROM sources
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
        episode_rows = [
            _row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, source_id, kind, body, privacy, risk, created_at,
                       source_url, raw_path, metadata_json
                FROM episodes
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
        candidate_rows = [
            _row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, episode_id, task_id, title, summary, status,
                       promotion_status, risk, privacy, created_at,
                       artifact_path, markdown_path, metadata_json
                FROM memory_candidates
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]

        for index, source in enumerate(source_rows):
            source_id = str(source["id"])
            add_node(
                _node(
                    source_id,
                    str(source.get("name") or source_id),
                    "source",
                    status=str(source.get("status") or "active"),
                    detail=str(source.get("kind") or "source"),
                    raw=source,
                    x=160,
                    y=index * 90,
                )
            )
            add_edge("brain-store-db", source_id, "has_source")

        for index, episode in enumerate(episode_rows):
            episode_id = str(episode["id"])
            body = str(episode.get("body") or "")
            detail = body.replace("\n", " ")[:180]
            add_node(
                _node(
                    episode_id,
                    str(episode.get("kind") or "episode"),
                    "episode",
                    status="captured",
                    risk=str(episode.get("risk") or "unknown"),
                    detail=detail,
                    raw=episode,
                    x=360,
                    y=index * 90,
                )
            )
            source_id = str(episode.get("source_id") or "")
            add_edge(source_id, episode_id, "captured")

        for index, candidate in enumerate(candidate_rows):
            candidate_id = str(candidate["id"])
            status = str(candidate.get("promotion_status") or candidate.get("status") or "candidate")
            add_node(
                _node(
                    candidate_id,
                    str(candidate.get("title") or candidate_id),
                    "candidate",
                    status=status,
                    risk=str(candidate.get("risk") or "unknown"),
                    detail=str(candidate.get("summary") or ""),
                    raw=candidate,
                    x=600,
                    y=index * 90,
                )
            )
            add_edge(str(candidate.get("episode_id") or ""), candidate_id, "yielded", status)
            if status == "approved" and candidate.get("markdown_path"):
                knowledge_id = f"knowledge_{candidate_id}"
                add_node(
                    _node(
                        knowledge_id,
                        str(candidate.get("title") or candidate_id),
                        "knowledge",
                        status="approved",
                        risk=str(candidate.get("risk") or "unknown"),
                        detail=str(candidate.get("markdown_path") or ""),
                        raw={
                            "candidate_id": candidate_id,
                            "path": str(candidate.get("markdown_path") or ""),
                        },
                        x=840,
                        y=index * 90,
                    )
                )
                add_edge(candidate_id, knowledge_id, "promoted", "approved")

    return {"status": "present", "nodes": nodes, "edges": edges, "harness": harness}


def search_brain_store(
    query: str,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    *,
    limit: int = 8,
) -> dict[str, object]:
    db_path = brain_db_path(canonical_root)
    query = str(query or "").strip()
    if not db_path.is_file():
        return {
            "query": query,
            "status": "missing",
            "fts_status": "missing",
            "results": [],
        }
    if not query:
        return {
            "query": query,
            "status": "empty_query",
            "fts_status": "unknown",
            "results": [],
        }

    ensure_brain_store(canonical_root)
    limit = max(1, min(int(limit), 50))
    with _connect(db_path) as connection:
        fts_status = _metadata_value(connection, "fts_status", "unknown")
        if fts_status != "enabled" or not _table_exists(connection, "brain_fts"):
            return {
                "query": query,
                "status": "fts_unavailable",
                "fts_status": fts_status,
                "results": [],
            }
        try:
            rows = connection.execute(
                """
                SELECT
                  mc.id AS candidate_id,
                  mc.title AS title,
                  mc.summary AS summary,
                  snippet(brain_fts, 3, '', '', '...', 18) AS snippet,
                  s.id AS source_id,
                  s.name AS source_name,
                  mc.risk AS risk,
                  mc.privacy AS privacy,
                  mc.created_at AS created_at,
                  mc.task_id AS task_id,
                  bm25(brain_fts) AS score,
                  rank AS rank
                FROM brain_fts
                JOIN memory_candidates mc ON mc.id = brain_fts.candidate_id
                JOIN episodes e ON e.id = mc.episode_id
                JOIN sources s ON s.id = e.source_id
                WHERE brain_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return {
                "query": query,
                "status": "invalid_query",
                "fts_status": fts_status,
                "results": [],
            }
    results = []
    for row in rows:
        payload = dict(row)
        payload["id"] = payload["candidate_id"]
        payload["name"] = payload["title"]
        payload["excerpt"] = payload.get("snippet") or payload.get("summary") or ""
        results.append(payload)
    return {
        "query": query,
        "status": "ok",
        "fts_status": fts_status,
        "results": results,
    }


def _compact_brain_text(value: object, *, limit: int = 320) -> str:
    compact = " ".join(redact_brain_text(str(value or "")).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _context_candidate(record: dict[str, object]) -> dict[str, object]:
    candidate_id = str(record.get("candidate_id") or record.get("id") or "")
    title = str(record.get("title") or record.get("name") or candidate_id or "Memory candidate")
    summary = _compact_brain_text(
        record.get("snippet") or record.get("summary") or record.get("description") or title,
        limit=420,
    )
    return {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "title": _compact_brain_text(title, limit=140),
        "summary": summary,
        "source_id": str(record.get("source_id") or ""),
        "source_name": str(record.get("source_name") or ""),
        "status": str(record.get("promotion_status") or record.get("status") or "candidate"),
        "risk": str(record.get("risk") or "unknown"),
        "privacy": str(record.get("privacy") or "project"),
        "created_at": str(record.get("created_at") or ""),
        "task_id": str(record.get("task_id") or ""),
    }


def _context_source(record: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(record.get("id") or ""),
        "name": _compact_brain_text(record.get("name") or record.get("id"), limit=120),
        "kind": str(record.get("kind") or "source"),
        "status": str(record.get("status") or "unknown"),
        "updated_at": str(record.get("updated_at") or ""),
    }


def _context_node(record: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(record.get("id") or ""),
        "label": _compact_brain_text(record.get("label") or record.get("name"), limit=120),
        "kind": str(record.get("kind") or record.get("type") or "node"),
        "status": str(record.get("status") or "unknown"),
        "risk": str(record.get("risk") or "unknown"),
        "detail": _compact_brain_text(record.get("detail") or record.get("summary"), limit=220),
        "provenance": _compact_brain_text(record.get("provenance"), limit=180),
    }


def _brain_context_markdown(pack: dict[str, object]) -> str:
    harness = pack.get("harness") if isinstance(pack.get("harness"), dict) else {}
    recall = pack.get("recall") if isinstance(pack.get("recall"), list) else []
    graph_nodes = pack.get("graph_nodes") if isinstance(pack.get("graph_nodes"), list) else []
    sources = pack.get("sources") if isinstance(pack.get("sources"), list) else []
    lines = [
        "# NERD OS Second Brain Context Pack",
        "",
        f"Generated: {pack.get('generated_at')}",
        f"Status: {pack.get('status')}",
        f"Query: {pack.get('query') or 'recent'}",
        f"DB: {pack.get('db_path')}",
        "",
        "## Harness",
        f"- FTS: {harness.get('fts_status', 'unknown')}",
        f"- Sources: {harness.get('source_count', 0)}",
        f"- Episodes: {harness.get('episode_count', 0)}",
        f"- Candidates: {harness.get('candidate_count', 0)}",
        f"- Approved: {harness.get('approved_count', 0)}",
        "",
        "## Recall",
    ]
    if recall:
        for index, item in enumerate(recall, start=1):
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    f"{index}. {item.get('title')}",
                    f"   - id: {item.get('candidate_id') or item.get('id')}",
                    f"   - source: {item.get('source_name') or item.get('source_id') or 'unknown'}",
                    f"   - risk/privacy: {item.get('risk')} / {item.get('privacy')}",
                    f"   - summary: {item.get('summary')}",
                ]
            )
    else:
        lines.append("- No recall records available.")
    lines.extend(["", "## Active Graph Nodes"])
    if graph_nodes:
        for item in graph_nodes:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- [{item.get('kind')}:{item.get('status')}] {item.get('label')} ({item.get('id')})"
            )
    else:
        lines.append("- No graph nodes available.")
    lines.extend(["", "## Sources"])
    if sources:
        for item in sources:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('name')} ({item.get('id')}, {item.get('status')})")
    else:
        lines.append("- No sources available.")
    lines.extend(
        [
            "",
            "## Agent Use",
            "- Treat this as shared durable memory for the current task.",
            "- Prefer candidate ids and source ids when citing or updating memory.",
            "- Promote only reviewed candidates into canonical knowledge.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_brain_context_pack(
    query: str = "",
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    *,
    limit: int = 8,
) -> dict[str, object]:
    limit = max(1, min(int(limit), 20))
    query = str(query or "").strip()
    store = build_brain_store_snapshot(canonical_root, recent_limit=limit)
    graph = build_brain_graph_snapshot(canonical_root, limit=limit)
    harness = graph.get("harness", {})
    if query:
        recall_payload = search_brain_store(query, canonical_root, limit=limit)
        recall_records = _safe_record_array(recall_payload.get("results", []))
        recall_status = str(recall_payload.get("status") or "unknown")
        fts_status = str(recall_payload.get("fts_status") or harness.get("fts_status") or "unknown")
    else:
        recall_records = _safe_record_array(store.get("recent_candidates", []))
        recall_status = "recent" if store.get("status") == "present" else str(store.get("status") or "missing")
        fts_status = str(harness.get("fts_status") or "unknown")
    pack: dict[str, object] = {
        "id": "nerd-os-second-brain-context-pack",
        "generated_at": iso_now(),
        "status": str(store.get("status") or graph.get("status") or "missing"),
        "query": query,
        "recall_status": recall_status,
        "fts_status": fts_status,
        "db_path": str(store.get("db_path") or brain_db_path(canonical_root)),
        "harness": harness,
        "recall": [_context_candidate(record) for record in recall_records[:limit]],
        "graph_nodes": [
            _context_node(record)
            for record in _safe_record_array(graph.get("nodes", []))[:limit]
        ],
        "sources": [
            _context_source(record)
            for record in _safe_record_array(store.get("sources", []))[:limit]
        ],
    }
    pack["markdown"] = _brain_context_markdown(pack)
    return pack


def brain_candidate_detail(
    candidate_id: str,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    candidate_id = str(candidate_id or "").strip()
    if not candidate_id:
        raise ValueError("candidate_id is required")
    db_path = brain_db_path(canonical_root)
    if not db_path.is_file():
        raise ValueError(f"unknown memory candidate: {candidate_id}")
    ensure_brain_store(canonical_root)
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
              mc.id AS id,
              mc.episode_id AS episode_id,
              mc.task_id AS task_id,
              mc.title AS title,
              mc.summary AS summary,
              mc.status AS status,
              mc.promotion_status AS promotion_status,
              mc.risk AS risk,
              mc.privacy AS privacy,
              mc.created_at AS created_at,
              mc.artifact_path AS artifact_path,
              mc.markdown_path AS markdown_path,
              mc.metadata_json AS metadata_json,
              e.id AS episode_id_joined,
              e.source_id AS source_id,
              e.kind AS episode_kind,
              e.body AS body,
              e.content_hash AS content_hash,
              e.privacy AS episode_privacy,
              e.risk AS episode_risk,
              e.created_at AS episode_created_at,
              e.source_url AS source_url,
              e.raw_path AS raw_path,
              e.metadata_json AS episode_metadata_json,
              s.id AS source_id_joined,
              s.name AS source_name,
              s.kind AS source_kind,
              s.status AS source_status,
              s.created_at AS source_created_at,
              s.updated_at AS source_updated_at,
              s.metadata_json AS source_metadata_json
            FROM memory_candidates mc
            JOIN episodes e ON e.id = mc.episode_id
            JOIN sources s ON s.id = e.source_id
            WHERE mc.id = ?
            """,
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown memory candidate: {candidate_id}")
        raw = dict(row)
        candidate = {
            key: raw[key]
            for key in (
                "id",
                "episode_id",
                "task_id",
                "title",
                "summary",
                "status",
                "promotion_status",
                "risk",
                "privacy",
                "created_at",
                "artifact_path",
                "markdown_path",
            )
        }
        episode = {
            "id": raw["episode_id_joined"],
            "source_id": raw["source_id"],
            "kind": raw["episode_kind"],
            "body": raw["body"],
            "content_hash": raw["content_hash"],
            "privacy": raw["episode_privacy"],
            "risk": raw["episode_risk"],
            "created_at": raw["episode_created_at"],
            "source_url": raw["source_url"],
            "raw_path": raw["raw_path"],
        }
        source = {
            "id": raw["source_id_joined"],
            "name": raw["source_name"],
            "kind": raw["source_kind"],
            "status": raw["source_status"],
            "created_at": raw["source_created_at"],
            "updated_at": raw["source_updated_at"],
        }
        for target, key in (
            (candidate, "metadata_json"),
            (episode, "episode_metadata_json"),
            (source, "source_metadata_json"),
        ):
            try:
                target["metadata"] = json.loads(str(raw.get(key) or "{}"))
            except json.JSONDecodeError:
                target["metadata"] = {}
        audit_log = [
            _row_to_dict(audit_row)
            for audit_row in connection.execute(
                """
                SELECT id, event_type, subject_id, created_at, payload_json AS metadata_json
                FROM audit_log
                WHERE subject_id = ?
                ORDER BY created_at DESC
                """,
                (candidate_id,),
            ).fetchall()
        ]
    return {
        "id": candidate_id,
        "candidate": candidate,
        "episode": episode,
        "source": source,
        "audit_log": audit_log,
    }


def build_brain_store_snapshot(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    *,
    ensure: bool = False,
    recent_limit: int = 8,
) -> dict[str, object]:
    db_path = brain_db_path(canonical_root)
    if ensure:
        ensure_brain_store(canonical_root)
    if not db_path.is_file():
        return {
            "id": "brain-store-db",
            "name": "NERD Brain Store",
            "status": "missing",
            "risk": "medium",
            "db_path": str(db_path),
            "source_count": 0,
            "episode_count": 0,
            "candidate_count": 0,
            "approved_count": 0,
            "recent_candidates": [],
            "sources": [],
        }
    ensure_brain_store(canonical_root)

    with _connect(db_path) as connection:
        candidates = [
            _row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, task_id, title AS name, summary, promotion_status,
                       promotion_status AS status, risk, privacy, created_at,
                       artifact_path, markdown_path, metadata_json
                FROM memory_candidates
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (recent_limit,),
            ).fetchall()
        ]
        sources = [
            _row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, name, kind, status, created_at, updated_at, metadata_json
                FROM sources
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (recent_limit,),
            ).fetchall()
        ]
        last_episode = connection.execute(
            "SELECT created_at FROM episodes ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        snapshot = {
            "id": "brain-store-db",
            "name": "NERD Brain Store",
            "status": "present",
            "risk": "medium",
            "db_path": str(db_path),
            "schema_version": SCHEMA_VERSION,
            "source_count": _scalar(connection, "SELECT COUNT(*) FROM sources"),
            "episode_count": _scalar(connection, "SELECT COUNT(*) FROM episodes"),
            "candidate_count": _scalar(connection, "SELECT COUNT(*) FROM memory_candidates"),
            "approved_count": _scalar(
                connection,
                "SELECT COUNT(*) FROM memory_candidates WHERE promotion_status = ?",
                ("approved",),
            ),
            "audit_count": _scalar(connection, "SELECT COUNT(*) FROM audit_log"),
            "last_episode_at": str(last_episode[0]) if last_episode else None,
            "recent_candidates": candidates,
            "sources": sources,
        }
    return snapshot


def write_brain_store_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> Path:
    snapshot = build_brain_store_snapshot(canonical_root, ensure=True)
    output = Path(canonical_root) / "registry" / "brain-store.json"
    return write_json(output, snapshot)


def _cleanup_legacy_sync_duplicates(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        DELETE FROM memory_candidates
        WHERE artifact_path IS NULL
          AND id GLOB 'memory_candidate_[0-9]*'
          AND metadata_json LIKE '%"sync_source": "memory_json"%'
        """
    )
    connection.execute(
        """
        DELETE FROM audit_log
        WHERE event_type = 'memory_candidate_ingested'
          AND subject_id NOT IN (SELECT id FROM memory_candidates)
        """
    )


def sync_memory_records(canonical_root: Path = DEFAULT_CANONICAL_ROOT) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    db_path = ensure_brain_store(canonical_root)
    with _connect(db_path) as connection:
        _cleanup_legacy_sync_duplicates(connection)
    inbox_records = _safe_record_array(_records_from_dir(canonical_root / "memory" / "inbox"))
    task_records = {
        str(record.get("inbox_id") or ""): record
        for record in _safe_record_array(_records_from_dir(canonical_root / "memory" / "tasks"))
    }
    artifact_records = _safe_record_array(_records_from_dir(canonical_root / "memory" / "artifacts"))
    artifacts_by_task = {
        str(record.get("task_id") or ""): record
        for record in artifact_records
        if str(record.get("artifact_type") or "") == "memory_candidate"
    }
    ingested = 0
    for inbox in inbox_records:
        raw_text = str(inbox.get("raw_text") or "").strip()
        if not raw_text:
            continue
        task = task_records.get(str(inbox.get("id") or ""), {})
        artifact = artifacts_by_task.get(str(task.get("id") or ""), {})
        title = str(task.get("title") or "Imported memory candidate")
        summary = str(artifact.get("summary") or raw_text.splitlines()[0][:240] or title)
        candidate_id = str(artifact.get("id") or "") or (
            f"memory_candidate_sync_{_content_hash(inbox.get('id'), raw_text)[:18]}"
        )
        ingest_brain_record(
            text=raw_text,
            source=str(inbox.get("source") or "memory-sync"),
            title=title,
            summary=summary,
            canonical_root=canonical_root,
            kind=str(inbox.get("detected_type") or "memory_sync"),
            source_url=str(inbox.get("source_url") or "") or None,
            raw_path=str(inbox.get("raw_path") or "") or None,
            privacy=str(inbox.get("privacy") or "project"),
            risk=str(inbox.get("risk") or task.get("risk") or "unknown"),
            task_id=str(task.get("id") or "") or None,
            candidate_id=candidate_id,
            artifact_path=str(artifact.get("path") or "") or None,
            markdown_path=str(artifact.get("path") or "") or None,
            metadata={
                "inbox_id": inbox.get("id"),
                "tags": inbox.get("tags", []),
                "department": task.get("department"),
                "sync_source": "memory_json",
            },
        )
        ingested += 1
    registry_path = write_brain_store_registry(canonical_root)
    snapshot = build_brain_store_snapshot(canonical_root)
    return {
        "ingested": ingested,
        "registry_path": str(registry_path),
        "snapshot": snapshot,
    }


def _records_from_dir(path: Path) -> list[object]:
    if not path.is_dir():
        return []
    records = []
    for record_path in sorted(path.glob("*.json")):
        payload = _safe_read_json(record_path, {})
        if isinstance(payload, dict):
            records.append(payload)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the NERD OS brain store.")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("sync-memory")
    sub.add_parser("snapshot")
    args = parser.parse_args(argv)

    if args.command == "init":
        db_path = ensure_brain_store(args.canonical_root)
        registry_path = write_brain_store_registry(args.canonical_root)
        sys.stdout.write(to_pretty_json({"db_path": str(db_path), "registry_path": str(registry_path)}))
        return 0
    if args.command == "sync-memory":
        sys.stdout.write(to_pretty_json(sync_memory_records(args.canonical_root)))
        return 0
    if args.command == "snapshot":
        sys.stdout.write(to_pretty_json(build_brain_store_snapshot(args.canonical_root)))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
