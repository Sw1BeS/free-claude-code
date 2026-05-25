import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = ROOT / "scripts" / "nerd" / "inventory" / "models.py"


def load_models():
    spec = importlib.util.spec_from_file_location("inventory_models", MODELS_PATH)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load models from {MODELS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_slugify_is_stable_and_ascii_safe():
    models = load_models()

    assert models.slugify("[NERD-CLAUDE]-free / WordPress MCP") == (
        "nerd-claude-free-wordpress-mcp"
    )
    assert models.slugify("  9router++local  ") == "9router-local"


def test_inventory_item_serializes_with_sorted_keys():
    models = load_models()
    item = models.InventoryItem(
        id="wordpress",
        name="WordPress",
        kind="skill",
        status="present",
        domain="wordpress",
        risk="low",
        path="/tmp/wordpress",
        evidence=["/tmp/wordpress/SKILL.md"],
        recommended_action="normalize",
        classification="skillpack",
    )

    payload = item.to_dict()
    rendered = models.to_pretty_json({"items": [payload]})

    assert payload["classification"] == "skillpack"
    assert payload["id"] == "wordpress"
    assert payload["evidence"] == ["/tmp/wordpress/SKILL.md"]
    assert rendered.endswith("\n")
    assert rendered.index('"classification"') < rendered.index('"domain"')
    assert rendered.index('"domain"') < rendered.index('"evidence"')


def test_inventory_report_sorts_items_by_id():
    models = load_models()
    report = models.InventoryReport(
        generated_at="2026-05-21T00:00:00Z",
        items=[
            models.InventoryItem(id="z", name="Z", kind="dir", status="present"),
            models.InventoryItem(id="a", name="A", kind="dir", status="present"),
        ],
        warnings=["warn"],
    )

    data = report.to_dict()

    assert [item["id"] for item in data["items"]] == ["a", "z"]
    assert data["warnings"] == ["warn"]
