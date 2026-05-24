#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib import error, request
from urllib.parse import quote

Action = Literal["create", "update", "keep"]
SeedKind = Literal["prompt", "memory", "knowledge", "knowledge_file"]

BASE_URL = "http://127.0.0.1:38080"
STACK_DIR = Path("/root/nerd-agency-stack")
STAGING_DIR = Path("/root/nerd-claude-free-staging")
NERD_METHOD_DIR = Path("/root/nerd-method")
ADMIN_CREDENTIALS = STACK_DIR / "admin-credentials.txt"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
KNOWLEDGE_REQUEST_TIMEOUT_SECONDS = 240


class OpenWebUIObject(TypedDict, total=False):
    id: str
    command: str
    name: str
    content: str
    tags: list[str]
    description: str
    filename: str
    meta: dict[str, object]
    metadata: dict[str, object]
    data: dict[str, object]


@dataclass(frozen=True)
class PromptSeed:
    command: str
    name: str
    content: str
    tags: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return {
            "command": self.command,
            "name": self.name,
            "content": self.content,
            "data": {},
            "meta": {"nerd_agency_seed": True},
            "tags": list(self.tags),
            "access_grants": [],
            "commit_message": "NERD Agency Mission Control seed",
            "is_production": True,
        }


@dataclass(frozen=True)
class MemorySeed:
    marker: str
    content: str

    def payload(self) -> dict[str, object]:
        return {"content": self.content}


@dataclass(frozen=True)
class KnowledgeSeed:
    name: str
    description: str

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "access_grants": [],
        }


@dataclass(frozen=True)
class KnowledgeDocument:
    path: Path
    filename: str
    content_type: str
    content_sha256: str

    @classmethod
    def from_path(cls, path: Path, *, source_root: Path) -> KnowledgeDocument:
        rel_path = _relative_path(path, source_root)
        stem = _slug_path(rel_path.with_suffix(""))
        suffix = path.suffix or ".txt"
        return cls(
            path=path,
            filename=f"nerd-agency--{stem}{suffix}",
            content_type=_content_type(path),
            content_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )


@dataclass(frozen=True)
class SeedChange:
    kind: SeedKind
    action: Action
    key: str
    payload: dict[str, object]
    object_id: str | None = None


def mission_control_prompts() -> list[PromptSeed]:
    shared_tags = ("nerd-agency", "mission-control", "v1")
    return [
        PromptSeed(
            command="mission_control",
            name="NERD Agency Mission Control",
            tags=shared_tags,
            content=(
                "Use NERD Agency Mission Control as the operating shell for "
                "[NERD-CLAUDE]-free. Public entry is "
                "https://agency.umanoff-analytics.space. Workspace hostnames "
                "agents, automations, memory, obs, and cms all route to the "
                "same Open WebUI shell. Backends stay loopback-only: n8n "
                "127.0.0.1:5678, Langfuse 127.0.0.1:3300, LiteLLM "
                "127.0.0.1:44000, Ollama 127.0.0.1:11434, GitNexus "
                "127.0.0.1:4173, and free-claude staged admin "
                "127.0.0.1:18082/admin. Prefer allowlisted V1 workflows, "
                "inventory reports, and trace links before raw backend access."
            ),
        ),
        PromptSeed(
            command="automation_ops",
            name="NERD Automation Ops",
            tags=(*shared_tags, "automation", "n8n"),
            content=(
                "Operate the V1 automation layer through n8n allowlisted "
                "workflows only. Low and medium-risk workflows may run in "
                "full-auto when NERD_AGENCY_AUTOMATION_ENABLED is enabled. "
                "Destructive, credentialed, money, betting, social scraping, "
                "personality-clone, and active security actions remain outside "
                "V1 automation."
            ),
        ),
        PromptSeed(
            command="cms_commerce",
            name="NERD CMS Commerce",
            tags=(*shared_tags, "cms", "shopify", "wordpress"),
            content=(
                "Use the CMS Commerce workspace for WordPress, WooCommerce, "
                "Shopify, SEO, analytics, migrations, theme work, app/plugin "
                "planning, and client delivery packaging. Candidate installers "
                "must stay as planned workflow actions until project "
                "credentials and scopes are explicitly configured."
            ),
        ),
        PromptSeed(
            command="knowledge_vault",
            name="NERD Knowledge Vault",
            tags=(*shared_tags, "memory", "knowledge"),
            content=(
                "Treat the knowledge vault as the unified memory surface. "
                "The canonical source is versioned NERD reports plus runtime "
                "sync targets, not scattered chat memory. Reference Open "
                "WebUI knowledge, Obsidian, NotebookLM, prompt library, "
                "client/project context, n8n execution notes, Langfuse "
                "traces, and GitNexus analysis through this workspace."
            ),
        ),
        PromptSeed(
            command="observability",
            name="NERD Observability",
            tags=(*shared_tags, "observability", "langfuse", "grafana"),
            content=(
                "Use observability for status checks, trace lookup, Grafana, "
                "Loki/Prometheus, Uptime Kuma, n8n execution evidence, "
                "provider smoke tests, and regression notes. Public UI access "
                "should point back to Mission Control; raw observability "
                "services remain internal."
            ),
        ),
    ]


def mission_control_memories() -> list[MemorySeed]:
    return [
        MemorySeed(
            marker="[NERD-AGENCY memory:system]",
            content=(
                "[NERD-AGENCY memory:system]\n"
                "NERD Agency Mission Control is the public Open WebUI shell "
                "for [NERD-CLAUDE]-free at https://agency.umanoff-analytics.space. "
                "agents, automations, memory, obs, and cms subdomains route to "
                "the same shell. Open WebUI knowledge, NERD inventory, manifest, "
                "service directory, and operating policies are the system memory."
            ),
        ),
        MemorySeed(
            marker="[NERD-AGENCY memory:automation]",
            content=(
                "[NERD-AGENCY memory:automation]\n"
                "n8n is the V1 full-auto execution layer. Only allowlisted "
                "low/medium-risk workflows may run automatically. The global "
                "kill switch is NERD_AGENCY_AUTOMATION_ENABLED, with per-tool "
                "auto_mode gates in nerd-agency.manifest.yaml."
            ),
        ),
        MemorySeed(
            marker="[NERD-AGENCY memory:knowledge]",
            content=(
                "[NERD-AGENCY memory:knowledge]\n"
                "The canonical source is versioned NERD reports plus runtime "
                "sync targets, not scattered chat memory. Unified memory "
                "includes Open WebUI knowledge, Obsidian, NotebookLM, prompt "
                "library, reusable skills, activation packs, project docs, "
                "GitHub/GitNexus notes, Langfuse traces, Grafana links, and "
                "n8n execution history."
            ),
        ),
        MemorySeed(
            marker="[NERD-AGENCY memory:safety]",
            content=(
                "[NERD-AGENCY memory:safety]\n"
                "V1 excludes destructive automation, active offensive security, "
                "money/betting actions, personality-clone agents, and social "
                "scraping at scale. CMS installers and credentialed connectors "
                "stay as candidate actions until explicit scopes are configured."
            ),
        ),
    ]


def mission_control_knowledge_base() -> KnowledgeSeed:
    return KnowledgeSeed(
        name="NERD Agency Mission Control",
        description=(
            "Canonical NERD Agency operating knowledge for the NERD-METHOD "
            "shared brain: stack README, manifest, domain map, Mission "
            "Control architecture notes, inventory reports, GitNexus, "
            "Obsidian, NotebookLM, n8n, CMS candidates, skill catalog, and "
            "backlog."
        ),
    )


def mission_control_knowledge_documents(
    stack_dir: Path = STACK_DIR,
    staging_dir: Path = STAGING_DIR,
    nerd_method_dir: Path = NERD_METHOD_DIR,
) -> list[KnowledgeDocument]:
    sources = [
        (stack_dir, Path("README.md")),
        (stack_dir, Path("nerd-agency.manifest.yaml")),
        (stack_dir, Path("nerd-agency.domains.yaml")),
        (stack_dir, Path("nerd-os.actions.yaml")),
        (stack_dir, Path("nerd-os.ui.yaml")),
        (stack_dir, Path("nerd-os.openapi.json")),
        (staging_dir, Path("docs/nerd_agency_mission_control.md")),
        (staging_dir, Path("docs/nerd_method_product_essence.md")),
        (staging_dir, Path("docs/nerd_os_ui_ux.md")),
        (staging_dir, Path("docs/nerd_inventory/mission-control-stack.md")),
        (staging_dir, Path("docs/nerd_inventory/cms-candidates.md")),
        (staging_dir, Path("docs/nerd_inventory/skills-inventory.md")),
        (staging_dir, Path("docs/nerd_inventory/gitinspired-catalog.md")),
        (staging_dir, Path("docs/nerd_inventory/nerd-method-brain.md")),
        (staging_dir, Path("docs/nerd_inventory/next-phase-backlog.md")),
    ]
    if stack_dir == STACK_DIR and staging_dir == STAGING_DIR:
        sources.extend(
            [
                (nerd_method_dir.parent, Path("nerd-method/README.md")),
                (nerd_method_dir.parent, Path("nerd-method/memory/README.md")),
                (
                    nerd_method_dir.parent,
                    Path(
                        "nerd-method/memory/knowledge/"
                        "nerd-method-operating-model.md"
                    ),
                ),
            ]
        )
    documents = []
    for root, relative in sources:
        path = root / relative
        if path.is_file():
            documents.append(KnowledgeDocument.from_path(path, source_root=root))
    return documents


def plan_prompt_upserts(
    existing_prompts: Sequence[OpenWebUIObject],
    desired_prompts: Sequence[PromptSeed],
) -> list[SeedChange]:
    existing_by_command = {
        prompt.get("command", ""): prompt for prompt in existing_prompts
    }
    changes: list[SeedChange] = []
    for prompt in desired_prompts:
        existing = existing_by_command.get(prompt.command)
        payload = prompt.payload()
        if existing is None:
            changes.append(
                SeedChange(
                    kind="prompt",
                    action="create",
                    key=prompt.command,
                    payload=payload,
                )
            )
            continue

        if _prompt_needs_update(existing, prompt):
            changes.append(
                SeedChange(
                    kind="prompt",
                    action="update",
                    key=prompt.command,
                    payload=payload,
                    object_id=existing.get("id"),
                )
            )
        else:
            changes.append(
                SeedChange(
                    kind="prompt",
                    action="keep",
                    key=prompt.command,
                    payload=payload,
                    object_id=existing.get("id"),
                )
            )
    return changes


def plan_memory_upserts(
    existing_memories: Sequence[OpenWebUIObject],
    desired_memories: Sequence[MemorySeed],
) -> list[SeedChange]:
    existing_by_marker = {
        memory.marker: _find_memory_by_marker(existing_memories, memory.marker)
        for memory in desired_memories
    }
    changes: list[SeedChange] = []
    for memory in desired_memories:
        existing = existing_by_marker[memory.marker]
        payload = memory.payload()
        if existing is None:
            changes.append(
                SeedChange(
                    kind="memory",
                    action="create",
                    key=memory.marker,
                    payload=payload,
                )
            )
            continue

        if existing.get("content") != memory.content:
            changes.append(
                SeedChange(
                    kind="memory",
                    action="update",
                    key=memory.marker,
                    payload=payload,
                    object_id=existing.get("id"),
                )
            )
        else:
            changes.append(
                SeedChange(
                    kind="memory",
                    action="keep",
                    key=memory.marker,
                    payload=payload,
                    object_id=existing.get("id"),
                )
            )
    return changes


def plan_knowledge_base_upsert(
    existing_knowledge: Sequence[OpenWebUIObject],
    desired: KnowledgeSeed,
) -> SeedChange:
    existing = next(
        (
            knowledge
            for knowledge in existing_knowledge
            if knowledge.get("name") == desired.name
        ),
        None,
    )
    payload = desired.payload()
    if existing is None:
        return SeedChange(
            kind="knowledge",
            action="create",
            key=desired.name,
            payload=payload,
        )
    if existing.get("description") != desired.description:
        return SeedChange(
            kind="knowledge",
            action="update",
            key=desired.name,
            payload=payload,
            object_id=existing.get("id"),
        )
    return SeedChange(
        kind="knowledge",
        action="keep",
        key=desired.name,
        payload=payload,
        object_id=existing.get("id"),
    )


def plan_knowledge_file_changes(
    existing_files: Sequence[OpenWebUIObject],
    desired_docs: Sequence[KnowledgeDocument],
) -> list[SeedChange]:
    existing_by_filename = {file.get("filename", ""): file for file in existing_files}
    existing_by_source_path = {
        source_path: file
        for file in existing_files
        if (source_path := file_source_path(file)) is not None
    }
    existing_by_digest = {
        digest: file
        for file in existing_files
        if (digest := file_content_sha256(file)) is not None
    }
    changes: list[SeedChange] = []
    for doc in desired_docs:
        payload: dict[str, object] = {
            "source_path": str(doc.path),
            "content_sha256": doc.content_sha256,
        }
        existing = existing_by_filename.get(doc.filename)
        if existing is None:
            digest_match = existing_by_digest.get(doc.content_sha256)
            if digest_match is not None:
                changes.append(
                    SeedChange(
                        kind="knowledge_file",
                        action="keep",
                        key=doc.filename,
                        payload=payload,
                        object_id=digest_match.get("id"),
                    )
                )
                continue
            source_match = existing_by_source_path.get(str(doc.path))
            if source_match is not None:
                changes.append(
                    SeedChange(
                        kind="knowledge_file",
                        action="update",
                        key=doc.filename,
                        payload=payload,
                        object_id=source_match.get("id"),
                    )
                )
                continue
            changes.append(
                SeedChange(
                    kind="knowledge_file",
                    action="create",
                    key=doc.filename,
                    payload=payload,
                )
            )
            continue

        if file_content_sha256(existing) == doc.content_sha256:
            changes.append(
                SeedChange(
                    kind="knowledge_file",
                    action="keep",
                    key=doc.filename,
                    payload=payload,
                    object_id=existing.get("id"),
                )
            )
        else:
            changes.append(
                SeedChange(
                    kind="knowledge_file",
                    action="update",
                    key=doc.filename,
                    payload=payload,
                    object_id=existing.get("id"),
                )
            )
    return changes


def render_seed_plan(changes: Sequence[SeedChange]) -> str:
    lines = [
        f"{change.action.upper()} {change.kind} {change.key}" for change in changes
    ]
    return "\n".join(lines) + ("\n" if lines else "")


class OpenWebUISeedClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def list_prompts(self) -> list[OpenWebUIObject]:
        data = self._request("GET", "/api/v1/prompts/")
        if not isinstance(data, list):
            raise RuntimeError("Open WebUI prompts endpoint returned non-list data")
        return data

    def list_memories(self) -> list[OpenWebUIObject]:
        data = self._request("GET", "/api/v1/memories/")
        if not isinstance(data, list):
            raise RuntimeError("Open WebUI memories endpoint returned non-list data")
        return data

    def list_knowledge_bases(self) -> list[OpenWebUIObject]:
        data = self._request("GET", "/api/v1/knowledge/")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise RuntimeError("Open WebUI knowledge endpoint returned invalid data")
        return data["items"]

    def list_knowledge_files(self, knowledge_id: str) -> list[OpenWebUIObject]:
        data = self._request("GET", f"/api/v1/knowledge/{knowledge_id}/files")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise RuntimeError(
                "Open WebUI knowledge files endpoint returned invalid data"
            )
        return data["items"]

    def find_file_by_filename(self, filename: str) -> OpenWebUIObject | None:
        path = f"/api/v1/files/search?filename={quote(filename)}&content=false"
        try:
            data = self._request("GET", path)
        except RuntimeError as exc:
            if "404" in str(exc):
                return None
            raise
        if not isinstance(data, list):
            return None
        return next((file for file in data if file.get("filename") == filename), None)

    def find_file_by_document_digest(
        self, doc: KnowledgeDocument
    ) -> OpenWebUIObject | None:
        path = f"/api/v1/files/search?filename={quote(doc.filename)}&content=false"
        try:
            data = self._request("GET", path)
        except RuntimeError as exc:
            if "404" in str(exc):
                return None
            raise
        if not isinstance(data, list):
            return None
        return next(
            (
                file
                for file in data
                if file.get("filename") == doc.filename
                and file_content_sha256(file) == doc.content_sha256
            ),
            None,
        )

    def apply_change(self, change: SeedChange) -> str | None:
        if change.action == "keep":
            return change.object_id
        if change.kind == "prompt":
            if change.action == "create":
                self._request("POST", "/api/v1/prompts/create", change.payload)
                return None
            if not change.object_id:
                raise ValueError(f"Missing Open WebUI prompt id for {change.key}")
            self._request(
                "POST",
                f"/api/v1/prompts/id/{change.object_id}/update",
                change.payload,
            )
            return change.object_id

        if change.kind == "memory":
            if change.action == "create":
                self._request("POST", "/api/v1/memories/add", change.payload)
                return None
            if not change.object_id:
                raise ValueError(f"Missing Open WebUI memory id for {change.key}")
            self._request(
                "POST",
                f"/api/v1/memories/{change.object_id}/update",
                change.payload,
            )
            return change.object_id

        if change.kind == "knowledge":
            if change.action == "create":
                data = self._request("POST", "/api/v1/knowledge/create", change.payload)
                if not isinstance(data, dict) or not isinstance(data.get("id"), str):
                    raise RuntimeError(
                        "Open WebUI knowledge create did not return an id"
                    )
                return data["id"]
            if not change.object_id:
                raise ValueError(f"Missing Open WebUI knowledge id for {change.key}")
            self._request(
                "POST",
                f"/api/v1/knowledge/{change.object_id}/update",
                change.payload,
            )
            return change.object_id

        return None

    def add_document_to_knowledge(
        self, knowledge_id: str, doc: KnowledgeDocument
    ) -> str:
        existing = self.find_file_by_document_digest(doc)
        file_id = existing.get("id") if existing else None
        if not file_id:
            file_id = self.upload_document(doc)
        try:
            self._request(
                "POST",
                f"/api/v1/knowledge/{knowledge_id}/file/add",
                {"file_id": file_id},
            )
        except RuntimeError as exc:
            if not is_duplicate_content_error(exc):
                raise
        return file_id

    def replace_document_in_knowledge(
        self, knowledge_id: str, doc: KnowledgeDocument, file_id: str
    ) -> str:
        self._request(
            "POST",
            f"/api/v1/knowledge/{knowledge_id}/file/remove?delete_file=true",
            {"file_id": file_id},
        )
        new_file_id = self.upload_document(doc)
        try:
            self._request(
                "POST",
                f"/api/v1/knowledge/{knowledge_id}/file/add",
                {"file_id": new_file_id},
            )
        except RuntimeError as exc:
            if not is_duplicate_content_error(exc):
                raise
        return new_file_id

    def upload_document(self, doc: KnowledgeDocument) -> str:
        data = request_multipart_json(
            f"{self.base_url}/api/v1/files/?process=true&process_in_background=false",
            token=self.token,
            file_field="file",
            file_path=doc.path,
            filename=doc.filename,
            content_type=doc.content_type,
            fields={
                "metadata": json.dumps(
                    {
                        "nerd_agency_seed": True,
                        "source_path": str(doc.path),
                        "content_sha256": doc.content_sha256,
                    }
                )
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise RuntimeError("Open WebUI file upload did not return an id")
        return data["id"]

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> Any:
        return request_json(
            method,
            f"{self.base_url}{path}",
            token=self.token,
            payload=payload,
            timeout_seconds=KNOWLEDGE_REQUEST_TIMEOUT_SECONDS,
        )


def apply_knowledge_documents(
    client: OpenWebUISeedClient,
    knowledge_id: str | None,
    *,
    dry_run: bool = False,
) -> list[SeedChange]:
    documents = mission_control_knowledge_documents()
    existing_files = client.list_knowledge_files(knowledge_id) if knowledge_id else []
    changes = plan_knowledge_file_changes(existing_files, documents)
    if not dry_run and knowledge_id:
        documents_by_filename = {doc.filename: doc for doc in documents}
        for change in changes:
            doc = documents_by_filename[change.key]
            if change.action == "create":
                client.add_document_to_knowledge(knowledge_id, doc)
            elif change.action == "update":
                if not change.object_id:
                    raise ValueError(
                        f"Missing Open WebUI knowledge file id for {change.key}"
                    )
                client.replace_document_in_knowledge(
                    knowledge_id,
                    doc,
                    change.object_id,
                )
    return changes


def request_multipart_json(
    url: str,
    *,
    token: str,
    file_field: str,
    file_path: Path,
    filename: str,
    content_type: str,
    fields: dict[str, str] | None = None,
) -> Any:
    boundary = "----nerd-agency-openwebui-seed"
    body = _multipart_body(
        boundary=boundary,
        file_field=file_field,
        file_path=file_path,
        filename=filename,
        content_type=content_type,
        fields=fields or {},
    )
    req = request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(
            f"Open WebUI upload failed: {exc.code} {url}: {detail}"
        ) from exc
    if not raw:
        return None
    return json.loads(raw)


def _multipart_body(
    *,
    boundary: str,
    file_field: str,
    file_path: Path,
    filename: str,
    content_type: str,
    fields: dict[str, str],
) -> bytes:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{filename}"\r\n'
            ).encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks)


def signin(base_url: str, email: str, password: str) -> str:
    data = request_json(
        "POST",
        f"{base_url.rstrip('/')}/api/v1/auths/signin",
        payload={"email": email, "password": password},
    )
    if not isinstance(data, dict) or not isinstance(data.get("token"), str):
        raise RuntimeError("Open WebUI signin did not return a token")
    return data["token"]


def request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict[str, object] | None = None,
    timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> Any:
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(
            f"Open WebUI request failed: {exc.code} {url}: {detail}"
        ) from exc
    if not raw:
        return None
    return json.loads(raw)


def is_duplicate_content_error(exc: RuntimeError) -> bool:
    return "Duplicate content detected" in str(exc)


def load_admin_credentials(path: Path = ADMIN_CREDENTIALS) -> tuple[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    email = values.get("email")
    password = values.get("password")
    if not email or not password:
        raise ValueError(f"{path} must contain email= and password=")
    return email, password


def build_seed_plan(client: OpenWebUISeedClient) -> list[SeedChange]:
    prompt_changes = plan_prompt_upserts(
        client.list_prompts(),
        mission_control_prompts(),
    )
    memory_changes = plan_memory_upserts(
        client.list_memories(),
        mission_control_memories(),
    )
    knowledge_change = plan_knowledge_base_upsert(
        client.list_knowledge_bases(),
        mission_control_knowledge_base(),
    )
    return [*prompt_changes, *memory_changes, knowledge_change]


def apply_seed(
    *,
    base_url: str = BASE_URL,
    credentials_path: Path = ADMIN_CREDENTIALS,
    dry_run: bool = False,
) -> list[SeedChange]:
    email, password = load_admin_credentials(credentials_path)
    token = signin(base_url, email, password)
    client = OpenWebUISeedClient(base_url, token)
    changes = build_seed_plan(client)
    knowledge_id = next(
        (change.object_id for change in changes if change.kind == "knowledge"),
        None,
    )
    if not dry_run:
        for change in changes:
            result = client.apply_change(change)
            if change.kind == "knowledge":
                knowledge_id = result or knowledge_id
    changes.extend(
        apply_knowledge_documents(
            client,
            knowledge_id,
            dry_run=dry_run,
        )
    )
    return changes


def _prompt_needs_update(existing: OpenWebUIObject, desired: PromptSeed) -> bool:
    return (
        existing.get("name") != desired.name
        or existing.get("content") != desired.content
        or tuple(existing.get("tags", [])) != desired.tags
    )


def _find_memory_by_marker(
    existing_memories: Sequence[OpenWebUIObject],
    marker: str,
) -> OpenWebUIObject | None:
    for memory in existing_memories:
        content = memory.get("content", "")
        if content.startswith(marker):
            return memory
    return None


def file_content_sha256(file: OpenWebUIObject) -> str | None:
    return _find_string_value(file, "content_sha256")


def file_source_path(file: OpenWebUIObject) -> str | None:
    return _find_string_value(file, "source_path")


def _find_string_value(value: object, key: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
        for nested in value.values():
            found = _find_string_value(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_string_value(nested, key)
            if found is not None:
                return found
    return None


def _relative_path(path: Path, source_root: Path) -> Path:
    try:
        return path.relative_to(source_root)
    except ValueError:
        return Path(path.name)


def _slug_path(path: Path) -> str:
    raw = "--".join(path.parts)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw)
    return slug.strip("-") or "document"


def _content_type(path: Path) -> str:
    if path.suffix == ".md":
        return "text/markdown"
    if path.suffix in {".yaml", ".yml"}:
        return "text/yaml"
    if path.suffix == ".json":
        return "application/json"
    return "text/plain"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed NERD Agency prompts and memories into Open WebUI."
    )
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--credentials", type=Path, default=ADMIN_CREDENTIALS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    changes = apply_seed(
        base_url=args.base_url,
        credentials_path=args.credentials,
        dry_run=args.dry_run,
    )
    print(render_seed_plan(changes), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
