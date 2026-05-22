import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

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
                notes="api_key=sk-12345678901234567890123456789012",
            )
        ],
    )

    markdown = render.render_report_markdown("Secrets", report)

    assert "sk-12345678901234567890123456789012" not in markdown
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


def test_write_report_pair_redacts_json_values(tmp_path):
    render = load_module("inventory_render", RENDER_PATH)
    models = load_module("inventory_models_for_json_writer", MODELS_PATH)
    report = models.InventoryReport(
        generated_at="2026-05-21T00:00:00Z",
        items=[
            models.InventoryItem(
                id="secret",
                name="Secret",
                kind="config",
                status="present",
                notes="api_key=sk-12345678901234567890123456789012",
            )
        ],
    )

    render.write_report_pair(tmp_path, "workspace-map", "Workspace Map", report)
    json_text = (tmp_path / "workspace-map.json").read_text()

    assert "sk-12345678901234567890123456789012" not in json_text
    assert "[REDACTED]" in json_text


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
        "cms-candidates.json",
        "cms-candidates.md",
        "claudecore-codemap.md",
        "mission-control-stack.json",
        "mission-control-stack.md",
        "nerd-method-brain.json",
        "nerd-method-brain.md",
        "next-phase-backlog.md",
    }
    assert expected.issubset({path.name for path in (tmp_path / "reports").iterdir()})


def test_scan_skill_roots_deduplicates_overlapping_roots(tmp_path):
    skills_path = tmp_path / "skills" / "skills" / "demo"
    skills_path.mkdir(parents=True)
    (skills_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill for duplicate root coverage.\n---\n",
        encoding="utf-8",
    )
    skills = load_module(
        "inventory_skills_for_dedup",
        ROOT / "scripts" / "nerd" / "inventory" / "skills.py",
    )

    items = skills.scan_skill_roots(
        [tmp_path / "skills", tmp_path / "skills" / "skills"]
    )

    assert [item.name for item in items] == ["demo"]


def test_gitinspired_alias_matching_avoids_short_substring_false_positive(tmp_path):
    (tmp_path / "experimental_lambdify.py").write_text("", encoding="utf-8")
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    (cache_dir / "dify").write_text("", encoding="utf-8")
    (tmp_path / "dify").mkdir()
    gitinspired = load_module(
        "inventory_gitinspired_for_aliases",
        ROOT / "scripts" / "nerd" / "inventory" / "gitinspired.py",
    )

    evidence = gitinspired._find_evidence(("dify",), [tmp_path])

    assert evidence == [str(tmp_path / "dify")]
