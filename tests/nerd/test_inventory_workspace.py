import importlib.util
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

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

    assert workspace.classify_path(Path("/root/archive")) == (
        "archive",
        "archived",
        "medium",
    )
    assert workspace.classify_path(Path("/root/free-claude-code")) == (
        "repo",
        "legacy",
        "medium",
    )
    assert workspace.classify_path(Path("/root/nerd-claude-free-staging")) == (
        "repo",
        "staged",
        "low",
    )
    assert workspace.classify_path(Path("/root/.fcc")) == ("config", "active", "medium")


def test_scan_workspace_detects_repo_and_dir(tmp_path):
    workspace = load_workspace()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init"], cwd=repo, check=True, capture_output=True, text=True
    )
    regular = tmp_path / "regular"
    regular.mkdir()

    report = workspace.scan_workspace(tmp_path)
    ids = {item.id for item in report.items}

    assert "repo" in ids
    assert "regular" in ids
    assert report.generated_at.endswith("Z")
