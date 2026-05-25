from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "git-guard.sh"


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-b", "nerd/safe-upgrade")
    run_git(repo, "config", "user.email", "nerd@example.test")
    run_git(repo, "config", "user.name", "NERD Test")
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "init")
    run_git(
        repo,
        "remote",
        "add",
        "origin",
        "https://github.com/Sw1BeS/free-claude-code.git",
    )
    run_git(
        repo,
        "remote",
        "add",
        "upstream",
        "https://github.com/Alishahryar1/free-claude-code.git",
    )
    run_git(repo, "remote", "set-url", "--push", "upstream", "DISABLED")
    return repo


def run_guard(repo: Path, **env: str) -> subprocess.CompletedProcess[str]:
    guard_env = {**os.environ, **env}
    return subprocess.run(
        [str(SCRIPT)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env=guard_env,
    )


def test_git_guard_allows_clean_user_owned_origin(tmp_path):
    repo = init_repo(tmp_path)

    result = run_guard(repo, NERD_GIT_ALLOWED_OWNER="Sw1BeS")

    assert result.returncode == 0
    assert "branch=nerd/safe-upgrade" in result.stdout
    assert "origin_push=https://github.com/Sw1BeS/free-claude-code.git" in result.stdout
    assert "upstream_push=DISABLED" in result.stdout


def test_git_guard_refuses_dirty_tree_without_override(tmp_path):
    repo = init_repo(tmp_path)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    result = run_guard(repo, NERD_GIT_ALLOWED_OWNER="Sw1BeS")

    assert result.returncode == 1
    assert "dirty tree" in result.stderr.lower()


def test_git_guard_refuses_non_user_owned_push_remote(tmp_path):
    repo = init_repo(tmp_path)
    run_git(
        repo,
        "remote",
        "set-url",
        "--push",
        "origin",
        "https://github.com/Other/free-claude-code.git",
    )

    result = run_guard(repo, NERD_GIT_ALLOWED_OWNER="Sw1BeS")

    assert result.returncode == 1
    assert "not owned by Sw1BeS" in result.stderr
