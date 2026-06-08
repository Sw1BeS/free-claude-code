from __future__ import annotations

import argparse
import json
import re
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
from scripts.nerd.brain.store import (
    brain_candidate_exists,
    ingest_intake_artifact,
    mark_candidate_promoted,
)

GITHUB_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+")
URL_RE = re.compile(r"https?://[^\s]+")
SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")

HIGH_RISK_TERMS = {
    "betting",
    "credential",
    "dark ai",
    "dark-ai",
    "darkweb",
    "dark web",
    "exploit",
    "farming",
    "hack",
    "hacking",
    "offensive",
    "stealth",
    "uncensored",
}


def record_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")


def iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_text(raw: str | dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if isinstance(raw, dict):
        if isinstance(raw.get("raw_text"), str):
            return raw["raw_text"].strip(), raw
        return json.dumps(raw, ensure_ascii=False, sort_keys=True), raw
    text = raw.strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return text, parsed
        except json.JSONDecodeError:
            pass
    return text, {}


def _contains_any(value: str, terms: set[str] | tuple[str, ...]) -> bool:
    lower = value.lower()
    return any(term in lower for term in terms)


def classify_raw_input(raw_text: str) -> dict[str, Any]:
    lower = raw_text.lower()
    tags: set[str] = set()
    risk = "low"
    detected_type = "task"
    department = "ops"

    if GITHUB_RE.search(raw_text):
        detected_type = "repo"
        tags.update({"github", "repo"})
        department = "research"
    elif URL_RE.search(raw_text):
        detected_type = "link"
        tags.update({"link", "web"})
        department = "research"
    if _contains_any(lower, {"rss", "research", "notebooklm", "crawl4ai"}):
        if department == "ops":
            tags.add("research")
        department = "research"
    if _contains_any(lower, {"shopify", "wordpress", "woocommerce", "cms"}):
        tags.add("cms-commerce")
        department = "cms-commerce"
    if _contains_any(lower, {"dataset", "export", "analytics", "saved items"}):
        tags.add("data")
        if department == "ops":
            department = "data-studio"
    if (
        _contains_any(lower, {"chrome extension", "code", "repo", "site", "website"})
        and department == "ops"
    ):
        tags.add("engineering")
        department = "engineering"
    if _contains_any(lower, {"course", "digital product", "moneygen", "template"}):
        tags.add("product-growth")
        department = "product-growth"
    if _contains_any(lower, {"obsidian", "prompt", "skill", "memory"}):
        tags.add("memory")
        department = "memory"
    if _contains_any(lower, HIGH_RISK_TERMS):
        tags.update({"high-risk", "lab"})
        risk = "high"
        department = "lab"

    if not tags:
        tags.add(department)

    return {
        "detected_type": detected_type,
        "department": department,
        "risk": risk,
        "tags": sorted(tags),
    }


def create_inbox_item(
    raw: str | dict[str, Any],
    *,
    source: str = "manual",
    source_url: str | None = None,
    privacy: str = "project",
) -> InboxItem:
    raw_text, parsed = _normalize_text(raw)
    classification = classify_raw_input(raw_text)
    detected_type = str(parsed.get("detected_type", classification["detected_type"]))
    tags = list(classification["tags"])
    if detected_type == "file":
        tags.extend(["file", "memory"])
    return InboxItem(
        id=f"inbox_{record_stamp()}",
        created_at=iso_now(),
        source=str(parsed.get("source", source)),
        source_url=str(parsed["source_url"])
        if parsed.get("source_url")
        else source_url,
        raw_text=raw_text,
        raw_path=str(parsed["raw_path"]) if parsed.get("raw_path") else None,
        detected_type=detected_type,
        project=str(parsed.get("project", "NERD-METHOD")),
        client=str(parsed["client"]) if parsed.get("client") else None,
        tags=tags,
        risk=classification["risk"],  # type: ignore[arg-type]
        privacy=str(parsed.get("privacy", privacy)),  # type: ignore[arg-type]
        status="classified",
    )


def _title_for(item: InboxItem, department: str) -> str:
    if item.detected_type == "repo":
        match = GITHUB_RE.search(item.raw_text)
        repo = (
            match.group(0).removeprefix("https://github.com/")
            if match
            else "repository"
        )
        return f"Analyze submitted GitHub repository: {repo}"
    if department == "cms-commerce":
        return "Prepare CMS/commerce task from inbox item"
    if department == "lab":
        return "Review high-risk lab request"
    if department == "data-studio":
        return "Classify data intake request"
    if department == "product-growth":
        return "Evaluate product/growth opportunity"
    if department == "memory":
        return "Promote memory or skill candidate"
    if department == "engineering":
        return "Prepare engineering implementation task"
    return "Classify and route inbox item"


def create_task_from_inbox(item: InboxItem) -> Task:
    classification = classify_raw_input(item.raw_text)
    department = classification["department"]
    if item.detected_type == "file":
        department = "memory"
    if item.risk == "high":
        department = "lab"

    routes = {
        "research": ("repo_researcher", "research_deep", "L1"),
        "cms-commerce": ("cms_commerce_builder", "coding_deep", "L1"),
        "data-studio": ("data_analyst", "data_extract", "L1"),
        "engineering": ("engineering_operator", "coding_deep", "L1"),
        "product-growth": ("growth_strategist", "research_deep", "L1"),
        "memory": ("memory_curator", "private_local", "L1"),
        "lab": ("lab_researcher", "lab_research", "L4"),
        "ops": ("ops_operator", "ops_fast", "L1"),
    }
    role, model_profile, autonomy_level = routes[department]
    required_approval = item.risk == "high" or department == "lab"
    status = "approval_required" if required_approval else "queued"

    return Task(
        id=f"task_{record_stamp()}",
        inbox_id=item.id,
        title=_title_for(item, department),
        department=department,
        risk=item.risk,
        autonomy_level=autonomy_level,  # type: ignore[arg-type]
        assigned_agent_role=role,
        model_profile=model_profile,
        required_approval=required_approval,
        status=status,
        tags=item.tags,
    )


def write_manual_inbox_item(
    raw: str | dict[str, Any],
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    source: str = "manual",
    source_url: str | None = None,
) -> dict[str, Path]:
    canonical_root = Path(canonical_root)
    item = create_inbox_item(raw, source=source, source_url=source_url)
    task = create_task_from_inbox(item)
    inbox_path = canonical_root / "memory" / "inbox" / f"{item.id}.json"
    task_path = canonical_root / "memory" / "tasks" / f"{task.id}.json"
    write_json(inbox_path, item.to_dict())
    write_json(task_path, task.to_dict())
    return {"inbox_path": inbox_path, "task_path": task_path}


def _slugify(value: str, fallback: str) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:80] or fallback


def _file_excerpt(path: Path, *, limit: int = 5000) -> str:
    if not path.is_file():
        raise ValueError(f"file does not exist: {path}")
    return path.read_text(encoding="utf-8", errors="replace")[:limit].strip()


def _candidate_summary(item: InboxItem, task: Task) -> str:
    first_line = next(
        (line.strip() for line in item.raw_text.splitlines() if line.strip()), ""
    )
    if first_line:
        return first_line[:240]
    return task.title


def _candidate_markdown(item: InboxItem, task: Task, summary: str) -> str:
    provenance = item.raw_path or item.source_url or item.source
    return "\n".join(
        [
            f"# Memory Candidate: {task.title}",
            "",
            f"- Inbox: {item.id}",
            f"- Task: {task.id}",
            f"- Source: {item.source}",
            f"- Provenance: {provenance}",
            f"- Risk: {item.risk}",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Raw",
            "",
            item.raw_text.strip(),
            "",
        ]
    )


def create_memory_candidate(
    item: InboxItem,
    task: Task,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> tuple[MemoryArtifact, Path]:
    summary = _candidate_summary(item, task)
    artifact_id = f"memory_candidate_{record_stamp()}"
    candidate_path = (
        Path(canonical_root)
        / "memory"
        / "brain"
        / "candidates"
        / f"{artifact_id}-{_slugify(summary, 'candidate')}.md"
    )
    provenance = [item.source]
    if item.source_url:
        provenance.append(item.source_url)
    if item.raw_path:
        provenance.append(item.raw_path)
    artifact = MemoryArtifact(
        id=artifact_id,
        task_id=task.id,
        run_id=None,
        artifact_type="memory_candidate",
        path=str(candidate_path),
        summary=summary,
        provenance=provenance,
        promotion_status="candidate",
    )
    return artifact, candidate_path


def _brain_intake_raw(
    text: str | None,
    *,
    file_path: Path | None,
    source: str,
    source_url: str | None,
) -> dict[str, Any]:
    body = (text or "").strip()
    raw_path: str | None = None
    detected_type: str | None = None
    if file_path is not None:
        file_path = Path(file_path)
        excerpt = _file_excerpt(file_path)
        body = "\n\n".join(part for part in (body, excerpt) if part)
        raw_path = str(file_path)
        detected_type = "file"
    if source_url and not body:
        body = source_url
    if not body:
        raise ValueError("text, source_url, or file_path is required")
    payload = {
        "source": source,
        "source_url": source_url,
        "raw_path": raw_path,
        "raw_text": body,
    }
    if detected_type is not None:
        payload["detected_type"] = detected_type
    return payload


def write_brain_intake(
    text: str | None = None,
    *,
    file_path: Path | None = None,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    source: str = "manual",
    source_url: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    canonical_root = Path(canonical_root)
    raw = _brain_intake_raw(
        text, file_path=file_path, source=source, source_url=source_url
    )
    item = create_inbox_item(raw, source=source, source_url=source_url)
    task = create_task_from_inbox(item)
    artifact, candidate_markdown_path = create_memory_candidate(
        item,
        task,
        canonical_root=canonical_root,
    )
    inbox_path = canonical_root / "memory" / "inbox" / f"{item.id}.json"
    task_path = canonical_root / "memory" / "tasks" / f"{task.id}.json"
    candidate_path = canonical_root / "memory" / "artifacts" / f"{artifact.id}.json"

    if not dry_run:
        write_json(inbox_path, item.to_dict())
        write_json(task_path, task.to_dict())
        candidate_markdown_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_markdown_path.write_text(
            _candidate_markdown(item, task, artifact.summary),
            encoding="utf-8",
        )
        write_json(candidate_path, artifact.to_dict())
        brain_store = ingest_intake_artifact(
            item,
            task,
            artifact,
            canonical_root=canonical_root,
            candidate_markdown_path=candidate_markdown_path,
        )
    else:
        brain_store = None

    return {
        "dry_run": dry_run,
        "inbox": item.to_dict(),
        "task": task.to_dict(),
        "candidate": artifact.to_dict(),
        "paths": {
            "inbox": inbox_path,
            "task": task_path,
            "candidate": candidate_path,
            "candidate_markdown": candidate_markdown_path,
        },
        "brain_store": brain_store,
    }


def _candidate_record_path(candidate_id: str, canonical_root: Path) -> Path | None:
    for path in sorted((canonical_root / "memory" / "artifacts").glob("*.json")):
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("id") == candidate_id:
            return path
    return None


def promote_memory_candidate(
    candidate_id: str,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    reviewer: str = "operator",
) -> dict[str, Any]:
    canonical_root = Path(canonical_root)
    candidate_path = _candidate_record_path(candidate_id, canonical_root)
    if candidate_path is None:
        raise ValueError(f"unknown memory candidate: {candidate_id}")
    artifact = read_json(candidate_path, {})
    if not isinstance(artifact, dict):
        raise ValueError(f"invalid memory candidate: {candidate_id}")
    if artifact.get("promotion_status") != "candidate":
        raise ValueError(f"memory candidate is not promotable: {candidate_id}")
    if not brain_candidate_exists(candidate_id, canonical_root):
        raise ValueError(f"unknown memory candidate in brain store: {candidate_id}")
    markdown_path = Path(str(artifact.get("path") or ""))
    if not markdown_path.is_file():
        raise ValueError(f"candidate markdown is missing: {markdown_path}")

    knowledge_path = canonical_root / "memory" / "knowledge" / f"{candidate_id}.md"
    knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    approved_at = iso_now()
    knowledge_path.write_text(
        markdown_path.read_text(encoding="utf-8")
        + f"\n## Promotion\n\nApproved by {reviewer} at {approved_at}.\n",
        encoding="utf-8",
    )

    artifact["promotion_status"] = "approved"
    artifact["approved_by"] = reviewer
    artifact["approved_at"] = approved_at
    artifact["path"] = str(knowledge_path)
    write_json(candidate_path, artifact)
    brain_store = mark_candidate_promoted(
        candidate_id,
        canonical_root=canonical_root,
        reviewer=reviewer,
        knowledge_path=knowledge_path,
        approved_at=approved_at,
    )
    return {
        "artifact": artifact,
        "candidate_path": candidate_path,
        "knowledge_path": knowledge_path,
        "brain_store": brain_store,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a safe Autonomous Core inbox item."
    )
    parser.add_argument("text", nargs="*", help="Manual inbox text.")
    parser.add_argument("--text", dest="text_option")
    parser.add_argument("--file", dest="file_path", type=Path)
    parser.add_argument("--source", default="manual")
    parser.add_argument("--source-url")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--promote-candidate")
    parser.add_argument("--reviewer", default="operator")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    args = parser.parse_args(argv)

    if args.promote_candidate:
        result = promote_memory_candidate(
            args.promote_candidate,
            canonical_root=args.canonical_root,
            reviewer=args.reviewer,
        )
        sys.stdout.write(str(result["knowledge_path"]) + "\n")
        return 0

    raw_text = args.text_option or " ".join(args.text).strip()
    if not raw_text:
        raw_text = sys.stdin.read().strip()

    result = write_brain_intake(
        raw_text,
        file_path=args.file_path,
        canonical_root=args.canonical_root,
        source=args.source,
        source_url=args.source_url,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        serializable = {
            key: {name: str(path) for name, path in value.items()}
            if key == "paths"
            else value
            for key, value in result.items()
        }
        sys.stdout.write(to_pretty_json(serializable))
    else:
        sys.stdout.write(str(result["paths"]["task"]) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
