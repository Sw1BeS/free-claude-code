from __future__ import annotations

import json
import subprocess


def _git(repo, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def test_github_radar_registry_reads_repo_state_without_network(tmp_path):
    from scripts.nerd.autonomous.github_radar import build_github_radar_registry

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "nerd/action-console")
    _git(repo, "config", "user.email", "nerd@example.test")
    _git(repo, "config", "user.name", "NERD Test")
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    _git(
        repo,
        "remote",
        "add",
        "origin",
        "https://github.com/Sw1BeS/free-claude-code.git",
    )
    _git(
        repo,
        "remote",
        "add",
        "upstream",
        "https://github.com/Alishahryar1/free-claude-code.git",
    )
    _git(repo, "remote", "set-url", "--push", "upstream", "DISABLED")
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    registry = build_github_radar_registry(
        canonical_root=tmp_path / "nerd-method",
        repo_path=repo,
        gitinspired_root=tmp_path / "missing-gitinspired",
    )

    items = {str(item["id"]): item for item in registry["items"]}  # type: ignore[index]
    repo_item = items["github-radar-staging-repo"]
    assert repo_item["status"] == "dirty"
    assert repo_item["metadata"]["branch"] == "nerd/action-console"
    assert repo_item["metadata"]["dirty_count"] == 1
    assert repo_item["metadata"]["canonical_repo"] == "Sw1BeS/free-claude-code"
    assert repo_item["metadata"]["upstream_push_protected"] is True
    assert repo_item["risk"] == "medium"


def test_write_github_radar_registry_sorts_items_and_writes_json(tmp_path):
    from scripts.nerd.autonomous.github_radar import write_github_radar_registry

    canonical_root = tmp_path / "nerd-method"
    output = write_github_radar_registry(
        canonical_root=canonical_root,
        repo_path=tmp_path / "missing-repo",
        gitinspired_root=tmp_path / "missing-gitinspired",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    item_ids = [item["id"] for item in payload["items"]]
    assert output == canonical_root / "registry" / "github-radar.json"
    assert item_ids == sorted(item_ids)
    assert "github-radar-staging-repo" in item_ids
