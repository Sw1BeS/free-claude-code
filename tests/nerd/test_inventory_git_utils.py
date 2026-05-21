import importlib.util
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

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
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_read_git_metadata_for_repo(tmp_path):
    git_utils = load_git_utils()
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/repo.git"],
        cwd=repo,
        check=True,
    )

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
