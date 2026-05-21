from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


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
