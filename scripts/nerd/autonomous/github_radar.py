from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json

DEFAULT_REPO_PATH = Path("/root/nerd-claude-free-staging")
DEFAULT_GITINSPIRED_ROOT = Path("/root/nerd-method/tools/git-inspired")


def _git_output(repo_path: Path, *args: str) -> str:
    if not repo_path.is_dir():
        return ""
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _remote_repo_name(url: str) -> str:
    cleaned = url.strip().removesuffix(".git")
    if not cleaned or cleaned in {"DISABLED", "no_push"}:
        return ""
    prefix = "https://github.com/"
    if cleaned.startswith(prefix):
        return cleaned.removeprefix(prefix)
    ssh_prefix = "git@github.com:"
    if cleaned.startswith(ssh_prefix):
        return cleaned.removeprefix(ssh_prefix)
    return ""


def _dirty_count(repo_path: Path) -> int:
    status = _git_output(repo_path, "status", "--porcelain")
    return len([line for line in status.splitlines() if line.strip()])


def _unpushed_count(repo_path: Path) -> int:
    unpushed = _git_output(repo_path, "rev-list", "--count", "@{u}..HEAD")
    return int(unpushed) if unpushed.isdigit() else 0


def _repo_item(repo_path: Path) -> dict[str, object]:
    branch = _git_output(repo_path, "branch", "--show-current")
    origin_fetch_url = _git_output(repo_path, "remote", "get-url", "origin")
    origin_push_url = _git_output(repo_path, "remote", "get-url", "--push", "origin")
    upstream_fetch_url = _git_output(repo_path, "remote", "get-url", "upstream")
    upstream_push_url = _git_output(
        repo_path, "remote", "get-url", "--push", "upstream"
    )
    dirty_count = _dirty_count(repo_path)
    exists = repo_path.is_dir()
    upstream_push_protected = upstream_push_url in {"", "DISABLED", "no_push"}
    status = "dirty" if dirty_count else "clean"
    if not exists:
        status = "missing"
    return {
        "id": "github-radar-staging-repo",
        "name": "NERD Claude Staging Repo",
        "kind": "git_repo",
        "status": status,
        "risk": "medium" if dirty_count else "low",
        "path": str(repo_path),
        "metadata": {
            "branch": branch,
            "dirty_count": dirty_count,
            "unpushed_commits": _unpushed_count(repo_path),
            "canonical_repo": _remote_repo_name(origin_push_url or origin_fetch_url),
            "origin_fetch_url": origin_fetch_url,
            "origin_push_url": origin_push_url,
            "upstream_fetch_url": upstream_fetch_url,
            "upstream_push_url": upstream_push_url,
            "upstream_push_protected": upstream_push_protected,
            "last_commit": _git_output(repo_path, "rev-parse", "--short", "HEAD"),
        },
        "notes": "Local staging repo state. Registry generation does not fetch, pull, or push.",
    }


def _gitinspired_item(gitinspired_root: Path) -> dict[str, object]:
    repo_count = 0
    if gitinspired_root.is_dir():
        repo_count = sum(1 for path in gitinspired_root.iterdir() if path.is_dir())
    return {
        "id": "github-radar-gitinspired-cache",
        "name": "GitInspired Source Cache",
        "kind": "source_cache",
        "status": "present" if gitinspired_root.is_dir() else "missing",
        "risk": "low",
        "path": str(gitinspired_root),
        "metadata": {"repo_count": repo_count},
        "notes": "Local source cache for repo radar and future trend intake.",
    }


def build_github_radar_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    repo_path: Path = DEFAULT_REPO_PATH,
    gitinspired_root: Path = DEFAULT_GITINSPIRED_ROOT,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    items = [_repo_item(Path(repo_path)), _gitinspired_item(Path(gitinspired_root))]
    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_github_radar_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    repo_path: Path = DEFAULT_REPO_PATH,
    gitinspired_root: Path = DEFAULT_GITINSPIRED_ROOT,
) -> Path:
    output = Path(canonical_root) / "registry" / "github-radar.json"
    return write_json(
        output,
        build_github_radar_registry(
            canonical_root=canonical_root,
            repo_path=repo_path,
            gitinspired_root=gitinspired_root,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write NERD OS GitHub Radar registry.")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--repo-path", type=Path, default=DEFAULT_REPO_PATH)
    parser.add_argument(
        "--gitinspired-root", type=Path, default=DEFAULT_GITINSPIRED_ROOT
    )
    args = parser.parse_args(argv)
    output = write_github_radar_registry(
        canonical_root=args.canonical_root,
        repo_path=args.repo_path,
        gitinspired_root=args.gitinspired_root,
    )
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
