import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

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

    report = codemap.build_claudecore_codemap(
        staging_dir=tmp_path,
        legacy_dir=tmp_path / "legacy",
    )

    api = next(item for item in report.items if item.id == "codemap-api")
    cli = next(item for item in report.items if item.id == "codemap-cli")

    assert api.status == "present"
    assert cli.status == "missing"
    assert report.generated_at.endswith("Z")
