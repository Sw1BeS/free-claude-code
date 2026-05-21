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
