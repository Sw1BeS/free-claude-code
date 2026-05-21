# NERD Workspace Inventory & Codemap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only inventory and codemap layer for `[NERD-CLAUDE]-free` that documents the current `/root` workspace, installed skills, GitInspired coverage, and ClaudeCore extension points.

**Architecture:** Add a stdlib-only inventory package under `scripts/nerd/inventory/` plus a CLI entry script that writes deterministic JSON and Markdown reports to `docs/nerd_inventory/`. The scanner reads local filesystem and git metadata only; it must not install, move, delete, start, stop, or reconfigure anything. Tests use temporary directories and fake git repos/skills so the generator can be verified without touching real global stores.

**Tech Stack:** Python 3.14, stdlib dataclasses/pathlib/subprocess/json, uv, pytest, ruff, ty, Bash runtime checks.

---

## File Structure

Create these implementation files:

- `scripts/nerd/inventory/__init__.py`
  - Package marker and public exports.
- `scripts/nerd/inventory/models.py`
  - Shared dataclasses, enums-as-literals, slug helper, deterministic JSON helper.
- `scripts/nerd/inventory/git_utils.py`
  - Read-only git metadata helper around `git -C`.
- `scripts/nerd/inventory/workspace.py`
  - Top-level workspace scanner for `/root`.
- `scripts/nerd/inventory/skills.py`
  - `SKILL.md` frontmatter parser and domain classifier.
- `scripts/nerd/inventory/gitinspired.py`
  - Static GitInspired input list and local evidence classifier.
- `scripts/nerd/inventory/codemap.py`
  - ClaudeCore component map and upstream ahead/behind summary.
- `scripts/nerd/inventory/render.py`
  - Markdown rendering helpers for all reports.
- `scripts/nerd/generate_inventory.py`
  - CLI entrypoint that orchestrates scanners and writes reports.

Create these tests:

- `tests/nerd/test_inventory_models.py`
- `tests/nerd/test_inventory_git_utils.py`
- `tests/nerd/test_inventory_skills.py`
- `tests/nerd/test_inventory_gitinspired.py`
- `tests/nerd/test_inventory_workspace.py`
- `tests/nerd/test_inventory_codemap.py`
- `tests/nerd/test_generate_inventory.py`

Generated report outputs:

- `docs/nerd_inventory/workspace-map.json`
- `docs/nerd_inventory/workspace-map.md`
- `docs/nerd_inventory/skills-inventory.json`
- `docs/nerd_inventory/skills-inventory.md`
- `docs/nerd_inventory/gitinspired-catalog.json`
- `docs/nerd_inventory/gitinspired-catalog.md`
- `docs/nerd_inventory/claudecore-codemap.md`
- `docs/nerd_inventory/next-phase-backlog.md`

Do not edit legacy application code in `/root/free-claude-code`.

---

## Task 1: Inventory Data Model

**Files:**
- Create: `scripts/nerd/inventory/__init__.py`
- Create: `scripts/nerd/inventory/models.py`
- Create: `tests/nerd/test_inventory_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/nerd/test_inventory_models.py`:

```python
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = ROOT / "scripts" / "nerd" / "inventory" / "models.py"


def load_models():
    spec = importlib.util.spec_from_file_location("inventory_models", MODELS_PATH)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load models from {MODELS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_slugify_is_stable_and_ascii_safe():
    models = load_models()

    assert models.slugify("[NERD-CLAUDE]-free / WordPress MCP") == (
        "nerd-claude-free-wordpress-mcp"
    )
    assert models.slugify("  9router++local  ") == "9router-local"


def test_inventory_item_serializes_with_sorted_keys():
    models = load_models()
    item = models.InventoryItem(
        id="wordpress",
        name="WordPress",
        kind="skill",
        status="present",
        domain="wordpress",
        risk="low",
        path="/tmp/wordpress",
        evidence=["/tmp/wordpress/SKILL.md"],
        recommended_action="normalize",
    )

    payload = item.to_dict()
    rendered = models.to_pretty_json({"items": [payload]})

    assert payload["id"] == "wordpress"
    assert payload["evidence"] == ["/tmp/wordpress/SKILL.md"]
    assert rendered.endswith("\n")
    assert rendered.index('"domain"') < rendered.index('"evidence"')


def test_inventory_report_sorts_items_by_id():
    models = load_models()
    report = models.InventoryReport(
        generated_at="2026-05-21T00:00:00Z",
        items=[
            models.InventoryItem(id="z", name="Z", kind="dir", status="present"),
            models.InventoryItem(id="a", name="A", kind="dir", status="present"),
        ],
        warnings=["warn"],
    )

    data = report.to_dict()

    assert [item["id"] for item in data["items"]] == ["a", "z"]
    assert data["warnings"] == ["warn"]
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/nerd/test_inventory_models.py -q
```

Expected: FAIL with `FileNotFoundError` or import failure for `scripts/nerd/inventory/models.py`.

- [ ] **Step 3: Implement package marker**

Create `scripts/nerd/inventory/__init__.py`:

```python
"""Read-only inventory tooling for [NERD-CLAUDE]-free."""
```

- [ ] **Step 4: Implement the data model**

Create `scripts/nerd/inventory/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Literal

Kind = Literal["repo", "dir", "skill", "service", "config", "doc", "archive", "candidate"]
Status = Literal[
    "active",
    "staged",
    "legacy",
    "present",
    "missing",
    "investigate",
    "skip_candidate",
    "archived",
]
Risk = Literal["low", "medium", "high", "unknown"]
Action = Literal[
    "keep",
    "index",
    "normalize",
    "install_later",
    "review_later",
    "skip",
    "archive_later",
]


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", cleaned)


@dataclass(frozen=True)
class InventoryItem:
    id: str
    name: str
    kind: Kind
    status: Status
    domain: str = "general"
    risk: Risk = "unknown"
    path: str | None = None
    source_url: str | None = None
    evidence: list[str] = field(default_factory=list)
    recommended_action: Action = "review_later"
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "domain": self.domain,
            "risk": self.risk,
            "recommended_action": self.recommended_action,
            "evidence": sorted(self.evidence),
        }
        if self.path is not None:
            data["path"] = self.path
        if self.source_url is not None:
            data["source_url"] = self.source_url
        if self.notes is not None:
            data["notes"] = self.notes
        return data


@dataclass(frozen=True)
class InventoryReport:
    generated_at: str
    items: list[InventoryItem]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "items": [item.to_dict() for item in sorted(self.items, key=lambda item: item.id)],
            "warnings": sorted(self.warnings),
        }


def to_pretty_json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
uv run pytest tests/nerd/test_inventory_models.py -q
uv run ruff check scripts/nerd/inventory/models.py tests/nerd/test_inventory_models.py
uv run ty check scripts/nerd/inventory/models.py tests/nerd/test_inventory_models.py
```

Expected: all pass.

Commit:

```bash
git add scripts/nerd/inventory/__init__.py scripts/nerd/inventory/models.py tests/nerd/test_inventory_models.py
git commit -m "feat: add nerd inventory data model"
```

---

## Task 2: Read-Only Git Metadata

**Files:**
- Create: `scripts/nerd/inventory/git_utils.py`
- Create: `tests/nerd/test_inventory_git_utils.py`

- [ ] **Step 1: Write failing git utility tests**

Create `tests/nerd/test_inventory_git_utils.py`:

```python
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
GIT_UTILS_PATH = ROOT / "scripts" / "nerd" / "inventory" / "git_utils.py"


def load_git_utils():
    spec = importlib.util.spec_from_file_location("inventory_git_utils", GIT_UTILS_PATH)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load git_utils from {GIT_UTILS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "README.md").write_text("# repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True, text=True)


def test_read_git_metadata_for_repo(tmp_path):
    git_utils = load_git_utils()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/repo.git"], cwd=repo, check=True)

    metadata = git_utils.read_git_metadata(repo)

    assert metadata.is_repo is True
    assert metadata.branch in {"main", "master"}
    assert metadata.commit
    assert metadata.dirty is False
    assert metadata.remotes == {"origin": "https://example.com/repo.git"}


def test_read_git_metadata_for_non_repo(tmp_path):
    git_utils = load_git_utils()

    metadata = git_utils.read_git_metadata(tmp_path)

    assert metadata.is_repo is False
    assert metadata.branch is None
    assert metadata.commit is None
    assert metadata.remotes == {}


def test_ahead_behind_returns_counts(tmp_path):
    git_utils = load_git_utils()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    counts = git_utils.ahead_behind(repo, "HEAD", "HEAD")

    assert counts == {"ahead": 0, "behind": 0}
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/nerd/test_inventory_git_utils.py -q
```

Expected: FAIL with missing `git_utils.py`.

- [ ] **Step 3: Implement git utilities**

Create `scripts/nerd/inventory/git_utils.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class GitMetadata:
    is_repo: bool
    branch: str | None = None
    commit: str | None = None
    dirty: bool = False
    remotes: dict[str, str] = field(default_factory=dict)
    warning: str | None = None


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def read_git_metadata(path: Path) -> GitMetadata:
    inside = _git(path, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return GitMetadata(is_repo=False)

    branch_result = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    commit_result = _git(path, "rev-parse", "--short", "HEAD")
    status_result = _git(path, "status", "--porcelain")
    remote_result = _git(path, "remote", "-v")

    remotes: dict[str, str] = {}
    for line in remote_result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "(fetch)":
            remotes[parts[0]] = parts[1]

    warning = None
    for result in (branch_result, commit_result, status_result, remote_result):
        if result.returncode != 0:
            warning = result.stderr.strip() or "git metadata command failed"
            break

    return GitMetadata(
        is_repo=True,
        branch=branch_result.stdout.strip() or None,
        commit=commit_result.stdout.strip() or None,
        dirty=bool(status_result.stdout.strip()),
        remotes=dict(sorted(remotes.items())),
        warning=warning,
    )


def ahead_behind(path: Path, left: str, right: str) -> dict[str, int]:
    result = _git(path, "rev-list", "--left-right", "--count", f"{left}...{right}")
    if result.returncode != 0:
        return {"ahead": 0, "behind": 0}
    parts = result.stdout.split()
    if len(parts) != 2:
        return {"ahead": 0, "behind": 0}
    return {"ahead": int(parts[0]), "behind": int(parts[1])}
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run pytest tests/nerd/test_inventory_git_utils.py -q
uv run ruff check scripts/nerd/inventory/git_utils.py tests/nerd/test_inventory_git_utils.py
uv run ty check scripts/nerd/inventory/git_utils.py tests/nerd/test_inventory_git_utils.py
```

Expected: all pass.

Commit:

```bash
git add scripts/nerd/inventory/git_utils.py tests/nerd/test_inventory_git_utils.py
git commit -m "feat: add read-only git inventory metadata"
```

---

## Task 3: Skills Inventory Scanner

**Files:**
- Create: `scripts/nerd/inventory/skills.py`
- Create: `tests/nerd/test_inventory_skills.py`

- [ ] **Step 1: Write failing skills tests**

Create `tests/nerd/test_inventory_skills.py`:

```python
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SKILLS_PATH = ROOT / "scripts" / "nerd" / "inventory" / "skills.py"


def load_skills():
    spec = importlib.util.spec_from_file_location("inventory_skills", SKILLS_PATH)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load skills from {SKILLS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_skill_frontmatter_extracts_fields(tmp_path):
    skills = load_skills()
    skill_file = tmp_path / "wordpress" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text(
        "\n".join(
            [
                "---",
                "name: wordpress",
                'description: "WordPress development workflow"',
                "risk: safe",
                "source: community",
                "---",
                "# WordPress",
            ]
        )
        + "\n"
    )

    parsed = skills.parse_skill_file(skill_file)

    assert parsed["name"] == "wordpress"
    assert parsed["description"] == "WordPress development workflow"
    assert parsed["risk"] == "safe"
    assert parsed["source"] == "community"


def test_classify_domain_recognizes_requested_domains():
    skills = load_skills()

    assert skills.classify_domain("wordpress-theme-development", "") == "wordpress"
    assert skills.classify_domain("shopify-automation", "") == "shopify"
    assert skills.classify_domain("n8n-workflow-patterns", "") == "n8n"
    assert skills.classify_domain("chrome-extension-developer", "") == "chrome"
    assert skills.classify_domain("gitnexus-cli", "") == "gitnexus"


def test_scan_skill_roots_returns_inventory_items(tmp_path):
    skills = load_skills()
    skill_file = tmp_path / "skills" / "shopify-automation" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: shopify-automation\ndescription: Shopify operations\n---\n"
    )

    items = skills.scan_skill_roots([tmp_path / "skills"])

    assert len(items) == 1
    assert items[0].id == "skill-shopify-automation"
    assert items[0].domain == "shopify"
    assert items[0].status == "present"
    assert items[0].recommended_action == "normalize"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/nerd/test_inventory_skills.py -q
```

Expected: FAIL with missing `skills.py`.

- [ ] **Step 3: Implement skills scanner**

Create `scripts/nerd/inventory/skills.py`:

```python
from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.models import InventoryItem, slugify
else:
    from .models import InventoryItem, slugify

KNOWN_SKILL_ROOTS = (
    Path("/root/.agents/plugins/skills"),
    Path("/root/.agents/skills"),
    Path("/root/.claude/skills"),
    Path("/root/.claude/skills/skills"),
    Path("/root/.codex/skills"),
    Path("/root/.hermes/skills"),
)

DOMAIN_KEYWORDS = {
    "wordpress": ("wordpress", "woocommerce"),
    "shopify": ("shopify",),
    "n8n": ("n8n",),
    "github": ("github", "git-pr", "pull-request"),
    "gitnexus": ("gitnexus",),
    "design": ("design", "ui-ux", "frontend", "stitch"),
    "security": ("security", "hacking", "pentest", "xss", "sast"),
    "data": ("data", "analytics", "database", "vector"),
    "obsidian": ("obsidian",),
    "telegram": ("telegram",),
    "scraping": ("crawl", "scrape", "firecrawl", "apify"),
    "chrome": ("chrome-extension", "chrome"),
    "mcp": ("mcp",),
    "agents": ("agent", "orchestration"),
    "finance": ("trading", "betting", "money", "monte-carlo"),
}


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_skill_file(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return {"name": path.parent.name}

    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = _strip_quotes(value)

    data.setdefault("name", path.parent.name)
    return data


def classify_domain(name: str, description: str) -> str:
    haystack = f"{name} {description}".lower()
    for domain, needles in DOMAIN_KEYWORDS.items():
        if any(needle in haystack for needle in needles):
            return domain
    return "general"


def scan_skill_roots(roots: list[Path] | tuple[Path, ...] = KNOWN_SKILL_ROOTS) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for root in roots:
        if not root.exists():
            continue
        for skill_file in sorted(root.rglob("SKILL.md")):
            parsed = parse_skill_file(skill_file)
            name = parsed.get("name", skill_file.parent.name)
            description = parsed.get("description", "")
            risk = "low" if parsed.get("risk") in {"safe", "low"} else "unknown"
            domain = classify_domain(name, description)
            items.append(
                InventoryItem(
                    id=f"skill-{slugify(name)}",
                    name=name,
                    kind="skill",
                    status="present",
                    domain=domain,
                    risk=risk,
                    path=str(skill_file.parent),
                    evidence=[str(skill_file)],
                    recommended_action="normalize",
                    notes=description or None,
                )
            )
    return items
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run pytest tests/nerd/test_inventory_skills.py -q
uv run ruff check scripts/nerd/inventory/skills.py tests/nerd/test_inventory_skills.py
uv run ty check scripts/nerd/inventory/skills.py tests/nerd/test_inventory_skills.py
```

Expected: all pass.

Commit:

```bash
git add scripts/nerd/inventory/skills.py tests/nerd/test_inventory_skills.py
git commit -m "feat: add nerd skills inventory scanner"
```

---

## Task 4: Workspace Scanner

**Files:**
- Create: `scripts/nerd/inventory/workspace.py`
- Create: `tests/nerd/test_inventory_workspace.py`

- [ ] **Step 1: Write failing workspace tests**

Create `tests/nerd/test_inventory_workspace.py`:

```python
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_PATH = ROOT / "scripts" / "nerd" / "inventory" / "workspace.py"


def load_workspace():
    spec = importlib.util.spec_from_file_location("inventory_workspace", WORKSPACE_PATH)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load workspace from {WORKSPACE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_classify_path_kind():
    workspace = load_workspace()

    assert workspace.classify_path(Path("/root/archive")) == ("archive", "archived", "medium")
    assert workspace.classify_path(Path("/root/free-claude-code")) == ("repo", "legacy", "medium")
    assert workspace.classify_path(Path("/root/nerd-claude-free-staging")) == ("repo", "staged", "low")
    assert workspace.classify_path(Path("/root/.fcc")) == ("config", "active", "medium")


def test_scan_workspace_detects_repo_and_dir(tmp_path):
    workspace = load_workspace()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    regular = tmp_path / "regular"
    regular.mkdir()

    report = workspace.scan_workspace(tmp_path)
    ids = {item.id for item in report.items}

    assert "repo" in ids
    assert "regular" in ids
    assert report.generated_at.endswith("Z")
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/nerd/test_inventory_workspace.py -q
```

Expected: FAIL with missing `workspace.py`.

- [ ] **Step 3: Implement workspace scanner**

Create `scripts/nerd/inventory/workspace.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import cast

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.git_utils import read_git_metadata
    from scripts.nerd.inventory.models import (
        InventoryItem,
        InventoryReport,
        Kind,
        Risk,
        Status,
        slugify,
    )
else:
    from .git_utils import read_git_metadata
    from .models import InventoryItem, InventoryReport, Kind, Risk, Status, slugify

SKIP_NAMES = {
    ".cache",
    ".npm",
    ".venv",
    "node_modules",
    "__pycache__",
}


def generated_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_path(path: Path) -> tuple[str, str, str]:
    name = path.name
    if name == "archive" or "archive" in name:
        return "archive", "archived", "medium"
    if name == "free-claude-code":
        return "repo", "legacy", "medium"
    if name == "nerd-claude-free-staging":
        return "repo", "staged", "low"
    if name.startswith(".") and name in {".fcc", ".claude", ".codex", ".hermes", ".gitnexus"}:
        return "config", "active", "medium"
    if (path / ".git").exists():
        return "repo", "present", "medium"
    return "dir", "present", "unknown"


def _safe_size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.name in SKIP_NAMES:
            continue
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def scan_workspace(root: Path = Path("/root")) -> InventoryReport:
    items: list[InventoryItem] = []
    warnings: list[str] = []
    for child in sorted(root.iterdir(), key=lambda value: value.name):
        if child.name in SKIP_NAMES:
            continue
        try:
            kind, status, risk = classify_path(child)
            git = read_git_metadata(child)
            evidence = [str(child)]
            notes_parts = [f"size_bytes={_safe_size_bytes(child)}"]
            if git.is_repo:
                kind = "repo"
                if git.branch:
                    notes_parts.append(f"branch={git.branch}")
                if git.commit:
                    notes_parts.append(f"commit={git.commit}")
                notes_parts.append(f"dirty={str(git.dirty).lower()}")
                for remote_name, remote_url in git.remotes.items():
                    notes_parts.append(f"remote:{remote_name}={remote_url}")
                if git.warning:
                    warnings.append(f"{child}: {git.warning}")

            items.append(
                InventoryItem(
                    id=slugify(child.name),
                    name=child.name,
                    kind=cast(Kind, kind),
                    status=cast(Status, status),
                    domain="workspace",
                    risk=cast(Risk, risk),
                    path=str(child),
                    evidence=evidence,
                    recommended_action="review_later",
                    notes="; ".join(notes_parts),
                )
            )
        except OSError as exc:
            warnings.append(f"{child}: {exc}")

    return InventoryReport(generated_at=generated_at(), items=items, warnings=warnings)
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run pytest tests/nerd/test_inventory_workspace.py -q
uv run ruff check scripts/nerd/inventory/workspace.py tests/nerd/test_inventory_workspace.py
uv run ty check scripts/nerd/inventory/workspace.py tests/nerd/test_inventory_workspace.py
```

Expected: all pass.

Commit:

```bash
git add scripts/nerd/inventory/workspace.py tests/nerd/test_inventory_workspace.py
git commit -m "feat: add nerd workspace scanner"
```

---

## Task 5: GitInspired Catalog

**Files:**
- Create: `scripts/nerd/inventory/gitinspired.py`
- Create: `tests/nerd/test_inventory_gitinspired.py`

- [ ] **Step 1: Write failing GitInspired tests**

Create `tests/nerd/test_inventory_gitinspired.py`:

```python
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
GITINSPIRED_PATH = ROOT / "scripts" / "nerd" / "inventory" / "gitinspired.py"


def load_gitinspired():
    spec = importlib.util.spec_from_file_location("inventory_gitinspired", GITINSPIRED_PATH)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load gitinspired from {GITINSPIRED_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_catalog_contains_requested_repositories():
    gitinspired = load_gitinspired()
    urls = {entry.source_url for entry in gitinspired.GITINSPIRED_REPOS}

    assert "https://github.com/decolua/9router" in urls
    assert "https://github.com/unclecode/crawl4ai" in urls
    assert "https://github.com/TauricResearch/TradingAgents" in urls
    assert "https://github.com/safishamsi/graphify" in urls


def test_classify_candidate_from_skill_evidence(tmp_path):
    gitinspired = load_gitinspired()
    skill_root = tmp_path / ".agents" / "plugins" / "skills" / "notebooklm"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("---\nname: notebooklm\n---\n")

    item = gitinspired.classify_candidate(
        gitinspired.GitInspiredRepo(
            name="notebooklm-skill",
            source_url="https://github.com/PleasePrompto/notebooklm-skill",
            domain="google",
            aliases=("notebooklm",),
        ),
        search_roots=[tmp_path],
    )

    assert item.status == "present"
    assert item.recommended_action == "normalize"
    assert item.domain == "google"


def test_build_catalog_marks_missing_when_no_evidence(tmp_path):
    gitinspired = load_gitinspired()

    report = gitinspired.build_gitinspired_catalog(
        repos=[
            gitinspired.GitInspiredRepo(
                name="missing-tool",
                source_url="https://github.com/example/missing-tool",
                domain="general",
                aliases=("missing-tool",),
            )
        ],
        search_roots=[tmp_path],
    )

    assert report.items[0].status == "missing"
    assert report.items[0].recommended_action == "install_later"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/nerd/test_inventory_gitinspired.py -q
```

Expected: FAIL with missing `gitinspired.py`.

- [ ] **Step 3: Implement GitInspired catalog**

Create `scripts/nerd/inventory/gitinspired.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import cast

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.models import (
        Action,
        InventoryItem,
        InventoryReport,
        Status,
        slugify,
    )
    from scripts.nerd.inventory.workspace import generated_at
else:
    from .models import Action, InventoryItem, InventoryReport, Status, slugify
    from .workspace import generated_at


@dataclass(frozen=True)
class GitInspiredRepo:
    name: str
    source_url: str
    domain: str
    aliases: tuple[str, ...]
    notes: str = ""


GITINSPIRED_REPOS = (
    GitInspiredRepo("awesome-claude-skills", "https://github.com/travisvn/awesome-claude-skills", "skills", ("awesome-claude-skills", "claude-skills")),
    GitInspiredRepo("OpenMythos", "https://github.com/kyegomez/OpenMythos", "agents", ("openmythos",)),
    GitInspiredRepo("awesome-design-systems", "https://github.com/alexpate/awesome-design-systems", "design", ("awesome-design-systems", "design-systems")),
    GitInspiredRepo("Awesome-Hacking", "https://github.com/Hack-with-Github/Awesome-Hacking", "security", ("awesome-hacking", "hacking")),
    GitInspiredRepo("awesome-openclaw-skills", "https://github.com/VoltAgent/awesome-openclaw-skills", "skills", ("awesome-openclaw-skills", "openclaw")),
    GitInspiredRepo("open-design", "https://github.com/nexu-io/open-design", "design", ("open-design",)),
    GitInspiredRepo("ECC", "https://github.com/affaan-m/ECC", "claude", ("ecc", "everything-claude-code")),
    GitInspiredRepo("awesome-copilot", "https://github.com/github/awesome-copilot", "github", ("awesome-copilot", "copilot")),
    GitInspiredRepo("OpenJarvis", "https://github.com/open-jarvis/OpenJarvis", "agents", ("openjarvis", "jarvis")),
    GitInspiredRepo("9router", "https://github.com/decolua/9router", "routing", ("9router",)),
    GitInspiredRepo("notebooklm-skill", "https://github.com/PleasePrompto/notebooklm-skill", "google", ("notebooklm", "notebooklm-skill")),
    GitInspiredRepo("openui", "https://github.com/thesysdev/openui", "ui", ("openui", "open-ui")),
    GitInspiredRepo("GitNexus", "https://github.com/abhigyanpatwari/GitNexus", "gitnexus", ("gitnexus",)),
    GitInspiredRepo("agency-agents", "https://github.com/msitarzewski/agency-agents", "agents", ("agency-agents",)),
    GitInspiredRepo("dify", "https://github.com/langgenius/dify", "agents", ("dify",)),
    GitInspiredRepo("hackingtool", "https://github.com/Z4nzu/hackingtool", "security", ("hackingtool",)),
    GitInspiredRepo("ui-ux-pro-max-skill", "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill", "design", ("ui-ux-pro-max", "ui-ux")),
    GitInspiredRepo("mattpocock-skills", "https://github.com/mattpocock/skills", "skills", ("mattpocock",)),
    GitInspiredRepo("composio-awesome-claude-skills", "https://github.com/ComposioHQ/awesome-claude-skills", "skills", ("composio", "awesome-claude-skills")),
    GitInspiredRepo("crawl4ai", "https://github.com/unclecode/crawl4ai", "scraping", ("crawl4ai", "crawl")),
    GitInspiredRepo("spec-kit", "https://github.com/github/spec-kit", "github", ("spec-kit",)),
    GitInspiredRepo("successor-agent", "https://github.com/lyc-aon/successor-agent", "agents", ("successor-agent",)),
    GitInspiredRepo("MiroFish", "https://github.com/666ghj/MiroFish", "agents", ("mirofish",)),
    GitInspiredRepo("TradingAgents", "https://github.com/TauricResearch/TradingAgents", "finance", ("tradingagents", "trading-agents")),
    GitInspiredRepo("n8n-workflows", "https://github.com/Zie619/n8n-workflows", "n8n", ("n8n-workflows", "n8n")),
    GitInspiredRepo("graphify", "https://github.com/safishamsi/graphify", "knowledge", ("graphify",)),
)


def _find_evidence(aliases: tuple[str, ...], search_roots: list[Path]) -> list[str]:
    evidence: list[str] = []
    lowered_aliases = tuple(alias.lower() for alias in aliases)
    for root in search_roots:
        if not root.exists():
            continue
        for child in root.rglob("*"):
            if len(evidence) >= 8:
                return sorted(evidence)
            name = child.name.lower()
            if any(alias in name for alias in lowered_aliases):
                evidence.append(str(child))
    return sorted(evidence)


def classify_candidate(repo: GitInspiredRepo, search_roots: list[Path]) -> InventoryItem:
    evidence = _find_evidence(repo.aliases, search_roots)
    if evidence:
        status = "present"
        action = "normalize"
        notes = "Local evidence found; review before installing anything new."
    else:
        status = "missing"
        action = "install_later"
        notes = "No strong local evidence found in configured search roots."

    return InventoryItem(
        id=f"gitinspired-{slugify(repo.name)}",
        name=repo.name,
        kind="candidate",
        status=cast(Status, status),
        domain=repo.domain,
        risk="unknown",
        source_url=repo.source_url,
        evidence=evidence,
        recommended_action=cast(Action, action),
        notes=repo.notes or notes,
    )


def build_gitinspired_catalog(
    repos: tuple[GitInspiredRepo, ...] | list[GitInspiredRepo] = GITINSPIRED_REPOS,
    search_roots: list[Path] | None = None,
) -> InventoryReport:
    roots = search_roots or [
        Path("/root"),
        Path("/root/.agents/plugins/skills"),
        Path("/root/.claude/skills"),
        Path("/root/.hermes/skills"),
    ]
    return InventoryReport(
        generated_at=generated_at(),
        items=[classify_candidate(repo, roots) for repo in repos],
    )
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run pytest tests/nerd/test_inventory_gitinspired.py -q
uv run ruff check scripts/nerd/inventory/gitinspired.py tests/nerd/test_inventory_gitinspired.py
uv run ty check scripts/nerd/inventory/gitinspired.py tests/nerd/test_inventory_gitinspired.py
```

Expected: all pass.

Commit:

```bash
git add scripts/nerd/inventory/gitinspired.py tests/nerd/test_inventory_gitinspired.py
git commit -m "feat: add gitinspired inventory catalog"
```

---

## Task 6: ClaudeCore Codemap

**Files:**
- Create: `scripts/nerd/inventory/codemap.py`
- Create: `tests/nerd/test_inventory_codemap.py`

- [ ] **Step 1: Write failing codemap tests**

Create `tests/nerd/test_inventory_codemap.py`:

```python
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
CODEMAP_PATH = ROOT / "scripts" / "nerd" / "inventory" / "codemap.py"


def load_codemap():
    spec = importlib.util.spec_from_file_location("inventory_codemap", CODEMAP_PATH)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load codemap from {CODEMAP_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_static_component_map_contains_nerd_extension_points():
    codemap = load_codemap()

    components = codemap.static_claudecore_components()
    names = {component["path"] for component in components}

    assert "api" in names
    assert "cli" in names
    assert "providers" in names
    assert "scripts/nerd" in names


def test_build_codemap_report_marks_missing_paths(tmp_path):
    codemap = load_codemap()
    (tmp_path / "api").mkdir()

    report = codemap.build_claudecore_codemap(staging_dir=tmp_path, legacy_dir=tmp_path / "legacy")

    api = next(item for item in report.items if item.id == "codemap-api")
    cli = next(item for item in report.items if item.id == "codemap-cli")

    assert api.status == "present"
    assert cli.status == "missing"
    assert report.generated_at.endswith("Z")
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/nerd/test_inventory_codemap.py -q
```

Expected: FAIL with missing `codemap.py`.

- [ ] **Step 3: Implement codemap builder**

Create `scripts/nerd/inventory/codemap.py`:

```python
from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.git_utils import ahead_behind
    from scripts.nerd.inventory.models import InventoryItem, InventoryReport, slugify
    from scripts.nerd.inventory.workspace import generated_at
else:
    from .git_utils import ahead_behind
    from .models import InventoryItem, InventoryReport, slugify
    from .workspace import generated_at


def static_claudecore_components() -> list[dict[str, str]]:
    return [
        {"path": "api", "domain": "api", "notes": "FastAPI routes, admin UI, request handling, runtime lifecycle."},
        {"path": "cli", "domain": "cli", "notes": "fcc-server, fcc-claude, process/session handling."},
        {"path": "config", "domain": "config", "notes": "Settings, provider config, constants, logging."},
        {"path": "providers", "domain": "providers", "notes": "Kimi, NVIDIA NIM, Wafer, OpenRouter, DeepSeek, Fireworks, Z.ai, OpenCode, local providers."},
        {"path": "messaging", "domain": "messaging", "notes": "Discord/Telegram command and session layer."},
        {"path": "core", "domain": "core", "notes": "Anthropic request/stream conversion and shared primitives."},
        {"path": "scripts/nerd", "domain": "nerd", "notes": "NERD wrappers, migration utilities, inventory tooling."},
        {"path": "docs", "domain": "docs", "notes": "Runbooks, specs, plans, generated inventory reports."},
    ]


def _branch_notes(staging_dir: Path, legacy_dir: Path) -> str:
    staged = ahead_behind(staging_dir, "HEAD", "upstream/main")
    legacy = ahead_behind(legacy_dir, "HEAD", "origin/main")
    return (
        f"staged_ahead={staged['ahead']}; staged_behind={staged['behind']}; "
        f"legacy_ahead={legacy['ahead']}; legacy_behind={legacy['behind']}"
    )


def build_claudecore_codemap(
    staging_dir: Path = Path("/root/nerd-claude-free-staging"),
    legacy_dir: Path = Path("/root/free-claude-code"),
) -> InventoryReport:
    items: list[InventoryItem] = []
    for component in static_claudecore_components():
        rel_path = component["path"]
        full_path = staging_dir / rel_path
        items.append(
            InventoryItem(
                id=f"codemap-{slugify(rel_path)}",
                name=rel_path,
                kind="dir",
                status="present" if full_path.exists() else "missing",
                domain=component["domain"],
                risk="low",
                path=str(full_path),
                evidence=[str(full_path)] if full_path.exists() else [],
                recommended_action="keep" if full_path.exists() else "review_later",
                notes=component["notes"],
            )
        )

    items.append(
        InventoryItem(
            id="codemap-upstream-status",
            name="ClaudeCore upstream status",
            kind="repo",
            status="staged",
            domain="upstream",
            risk="medium",
            path=str(staging_dir),
            evidence=[str(staging_dir), str(legacy_dir)],
            recommended_action="review_later",
            notes=_branch_notes(staging_dir, legacy_dir),
        )
    )
    return InventoryReport(generated_at=generated_at(), items=items)
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run pytest tests/nerd/test_inventory_codemap.py -q
uv run ruff check scripts/nerd/inventory/codemap.py tests/nerd/test_inventory_codemap.py
uv run ty check scripts/nerd/inventory/codemap.py tests/nerd/test_inventory_codemap.py
```

Expected: all pass.

Commit:

```bash
git add scripts/nerd/inventory/codemap.py tests/nerd/test_inventory_codemap.py
git commit -m "feat: add claudecore inventory codemap"
```

---

## Task 7: Markdown Rendering And Report Writer

**Files:**
- Create: `scripts/nerd/inventory/render.py`
- Create: `tests/nerd/test_generate_inventory.py`

- [ ] **Step 1: Write failing render tests**

Create `tests/nerd/test_generate_inventory.py`:

```python
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
RENDER_PATH = ROOT / "scripts" / "nerd" / "inventory" / "render.py"
MODELS_PATH = ROOT / "scripts" / "nerd" / "inventory" / "models.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_render_markdown_table_redacts_secret_like_notes():
    render = load_module("inventory_render", RENDER_PATH)
    models = load_module("inventory_models_for_render", MODELS_PATH)
    report = models.InventoryReport(
        generated_at="2026-05-21T00:00:00Z",
        items=[
            models.InventoryItem(
                id="secret",
                name="Secret",
                kind="config",
                status="present",
                notes="api_key=sk-live-super-secret-do-not-log",
            )
        ],
    )

    markdown = render.render_report_markdown("Secrets", report)

    assert "sk-live-super-secret-do-not-log" not in markdown
    assert "[REDACTED]" in markdown
    assert "| ID | Name | Kind | Status | Domain | Risk | Action |" in markdown


def test_write_report_pair_creates_json_and_markdown(tmp_path):
    render = load_module("inventory_render", RENDER_PATH)
    models = load_module("inventory_models_for_writer", MODELS_PATH)
    report = models.InventoryReport(
        generated_at="2026-05-21T00:00:00Z",
        items=[models.InventoryItem(id="a", name="A", kind="dir", status="present")],
    )

    render.write_report_pair(tmp_path, "workspace-map", "Workspace Map", report)

    assert (tmp_path / "workspace-map.json").is_file()
    assert (tmp_path / "workspace-map.md").is_file()
    assert '"items"' in (tmp_path / "workspace-map.json").read_text()
    assert "# Workspace Map" in (tmp_path / "workspace-map.md").read_text()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/nerd/test_generate_inventory.py -q
```

Expected: FAIL with missing `render.py`.

- [ ] **Step 3: Implement renderer**

Create `scripts/nerd/inventory/render.py`:

```python
from __future__ import annotations

from pathlib import Path
import re
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from scripts.nerd.inventory.models import InventoryReport, to_pretty_json
else:
    from .models import InventoryReport, to_pretty_json

SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|nvapi-[A-Za-z0-9_-]{12,}|wfr_[A-Za-z0-9_-]{12,})"
)


def redact(value: str | None) -> str:
    if not value:
        return ""
    return SECRET_PATTERN.sub("[REDACTED]", value)


def render_report_markdown(title: str, report: InventoryReport) -> str:
    lines = [
        f"# {title}",
        "",
        f"Generated: `{report.generated_at}`",
        "",
        "| ID | Name | Kind | Status | Domain | Risk | Action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(report.items, key=lambda entry: entry.id):
        lines.append(
            " | ".join(
                [
                    f"| `{item.id}`",
                    redact(item.name),
                    item.kind,
                    item.status,
                    item.domain,
                    item.risk,
                    f"{item.recommended_action} |",
                ]
            )
        )
        if item.path or item.source_url or item.notes or item.evidence:
            detail = "; ".join(
                part
                for part in [
                    f"path={item.path}" if item.path else "",
                    f"source={item.source_url}" if item.source_url else "",
                    f"notes={redact(item.notes)}" if item.notes else "",
                    f"evidence={', '.join(item.evidence[:5])}" if item.evidence else "",
                ]
                if part
            )
            lines.append(f"|  | {redact(detail)} |  |  |  |  |  |")
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {redact(warning)}" for warning in report.warnings)
    return "\n".join(lines) + "\n"


def write_report_pair(output_dir: Path, stem: str, title: str, report: InventoryReport) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{stem}.json").write_text(
        to_pretty_json(report.to_dict()),
        encoding="utf-8",
    )
    (output_dir / f"{stem}.md").write_text(
        render_report_markdown(title, report),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
uv run pytest tests/nerd/test_generate_inventory.py -q
uv run ruff check scripts/nerd/inventory/render.py tests/nerd/test_generate_inventory.py
uv run ty check scripts/nerd/inventory/render.py tests/nerd/test_generate_inventory.py
```

Expected: all pass.

Commit:

```bash
git add scripts/nerd/inventory/render.py tests/nerd/test_generate_inventory.py
git commit -m "feat: add nerd inventory report rendering"
```

---

## Task 8: CLI Orchestrator And Generated Reports

**Files:**
- Create: `scripts/nerd/generate_inventory.py`
- Modify: `tests/nerd/test_generate_inventory.py`
- Generate: `docs/nerd_inventory/*.json`
- Generate: `docs/nerd_inventory/*.md`

- [ ] **Step 1: Extend tests for CLI generation**

Append this test to `tests/nerd/test_generate_inventory.py`:

```python
def test_generate_inventory_main_writes_expected_reports(tmp_path):
    generator_path = ROOT / "scripts" / "nerd" / "generate_inventory.py"
    generator = load_module("generate_inventory", generator_path)

    exit_code = generator.main(
        [
            "--workspace-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "reports"),
            "--skip-real-skills",
            "--skip-real-gitinspired-search",
        ]
    )

    assert exit_code == 0
    expected = {
        "workspace-map.json",
        "workspace-map.md",
        "skills-inventory.json",
        "skills-inventory.md",
        "gitinspired-catalog.json",
        "gitinspired-catalog.md",
        "claudecore-codemap.md",
        "next-phase-backlog.md",
    }
    assert expected.issubset({path.name for path in (tmp_path / "reports").iterdir()})
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest tests/nerd/test_generate_inventory.py::test_generate_inventory_main_writes_expected_reports -q
```

Expected: FAIL with missing `generate_inventory.py`.

- [ ] **Step 3: Implement CLI orchestrator**

Create `scripts/nerd/generate_inventory.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.nerd.inventory.codemap import build_claudecore_codemap
    from scripts.nerd.inventory.gitinspired import build_gitinspired_catalog
    from scripts.nerd.inventory.models import InventoryReport
    from scripts.nerd.inventory.render import render_report_markdown, write_report_pair
    from scripts.nerd.inventory.skills import KNOWN_SKILL_ROOTS, scan_skill_roots
    from scripts.nerd.inventory.workspace import generated_at, scan_workspace
else:
    from .inventory.codemap import build_claudecore_codemap
    from .inventory.gitinspired import build_gitinspired_catalog
    from .inventory.models import InventoryReport
    from .inventory.render import render_report_markdown, write_report_pair
    from .inventory.skills import KNOWN_SKILL_ROOTS, scan_skill_roots
    from .inventory.workspace import generated_at, scan_workspace


def write_backlog(output_dir: Path) -> None:
    lines = [
        "# Next Phase Backlog",
        "",
        "1. Rebase or merge NERD staged patch stack onto latest `upstream/main`.",
        "2. Normalize installed WordPress, Shopify, n8n, NotebookLM, Obsidian, GitHub, data, and security skills into an activation manifest.",
        "3. Design the WordPress/CMS workbench layer.",
        "4. Design the Shopify commerce layer.",
        "5. Design the n8n/MCP connector library.",
        "6. Design Mac companion install, sync, and task routing.",
        "7. Design data ingestion and automatic triage.",
        "8. Design commercialization and prompt/product library.",
        "",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "next-phase-backlog.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate NERD workspace inventory reports.")
    parser.add_argument("--workspace-root", type=Path, default=Path("/root"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/nerd_inventory"))
    parser.add_argument("--staging-dir", type=Path, default=Path("/root/nerd-claude-free-staging"))
    parser.add_argument("--legacy-dir", type=Path, default=Path("/root/free-claude-code"))
    parser.add_argument("--skip-real-skills", action="store_true")
    parser.add_argument("--skip-real-gitinspired-search", action="store_true")
    args = parser.parse_args(argv)

    workspace_report = scan_workspace(args.workspace_root)
    skill_roots = [] if args.skip_real_skills else list(KNOWN_SKILL_ROOTS)
    skills_report = InventoryReport(
        generated_at=generated_at(),
        items=scan_skill_roots(skill_roots),
    )
    gitinspired_roots = [args.workspace_root]
    if args.skip_real_gitinspired_search:
        gitinspired_roots = [args.workspace_root / "__empty__"]
    gitinspired_report = build_gitinspired_catalog(search_roots=gitinspired_roots)
    codemap_report = build_claudecore_codemap(args.staging_dir, args.legacy_dir)

    write_report_pair(args.output_dir, "workspace-map", "Workspace Map", workspace_report)
    write_report_pair(args.output_dir, "skills-inventory", "Skills Inventory", skills_report)
    write_report_pair(args.output_dir, "gitinspired-catalog", "GitInspired Catalog", gitinspired_report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "claudecore-codemap.md").write_text(
        render_report_markdown("ClaudeCore Codemap", codemap_report),
        encoding="utf-8",
    )
    write_backlog(args.output_dir)
    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and generate real reports**

Run:

```bash
uv run pytest tests/nerd/test_generate_inventory.py -q
uv run python scripts/nerd/generate_inventory.py
```

Expected:

- tests pass;
- command prints `docs/nerd_inventory`;
- all eight report files exist.

- [ ] **Step 5: Verify generated reports are secret-safe**

Run:

```bash
if rg -n 'sk-[A-Za-z0-9_-]{20,}|nvapi-[A-Za-z0-9_-]{20,}|wfr_[A-Za-z0-9_-]{20,}' docs/nerd_inventory; then
  printf 'Secret-like value found in generated inventory\n' >&2
  exit 1
fi
```

Expected: no output and exit `0`.

- [ ] **Step 6: Run lint/type checks and commit**

Run:

```bash
uv run ruff check scripts/nerd/inventory scripts/nerd/generate_inventory.py tests/nerd
uv run ty check scripts/nerd/inventory scripts/nerd/generate_inventory.py tests/nerd
```

Expected: all pass.

Commit:

```bash
git add scripts/nerd/generate_inventory.py tests/nerd/test_generate_inventory.py docs/nerd_inventory
git commit -m "feat: generate nerd workspace inventory reports"
```

---

## Task 9: Full Verification

**Files:**
- No new files.
- Verify all files created in Tasks 1-8.

- [ ] **Step 1: Run project sync**

Run:

```bash
uv sync
```

Expected: exits `0`.

- [ ] **Step 2: Run full lint**

Run:

```bash
uv run ruff check
```

Expected: `All checks passed!`

- [ ] **Step 3: Run full type check**

Run:

```bash
uv run ty check
```

Expected: `All checks passed!`

- [ ] **Step 4: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 5: Verify service health was not disturbed**

Run:

```bash
free-claude status
curl -fsS http://127.0.0.1:18082/health
curl -fsS http://127.0.0.1:8082/health
```

Expected:

- `free-claude status` reports `staged_health=healthy` and `legacy_8082_health=healthy`;
- both curl commands print `{"status":"healthy"}`.

- [ ] **Step 6: Verify branch and report outputs**

Run:

```bash
git status --short --branch
find docs/nerd_inventory -maxdepth 1 -type f | sort
```

Expected:

- git status shows only `## nerd/safe-upgrade`;
- output contains all eight inventory files.

- [ ] **Step 7: Commit any final report refresh**

If `uv run python scripts/nerd/generate_inventory.py` changed generated docs after verification, commit them:

```bash
git add docs/nerd_inventory
git commit -m "docs: refresh nerd inventory reports"
```

If no files changed, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage:
  - Workspace source of truth: Tasks 1, 2, 4, 8.
  - ClaudeCore codemap: Task 6.
  - Skills inventory: Task 3.
  - GitInspired classification: Task 5.
  - JSON and Markdown outputs: Tasks 7, 8.
  - Secret-safe behavior: Tasks 7, 8, 9.
  - Runtime health unchanged: Task 9.
- Scope:
  - No cleanup, installs, UI changes, service reconfiguration, or port promotion.
- Type consistency:
  - `InventoryItem`, `InventoryReport`, `GitMetadata`, and `GitInspiredRepo` are introduced before use.
  - All task paths match the file structure section.
