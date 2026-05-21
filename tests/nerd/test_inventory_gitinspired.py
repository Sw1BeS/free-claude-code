import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITINSPIRED_PATH = ROOT / "scripts" / "nerd" / "inventory" / "gitinspired.py"


def load_gitinspired():
    spec = importlib.util.spec_from_file_location(
        "inventory_gitinspired", GITINSPIRED_PATH
    )
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
