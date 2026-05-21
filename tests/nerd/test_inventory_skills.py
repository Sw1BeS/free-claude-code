import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_PATH = ROOT / "scripts" / "nerd" / "inventory" / "skills.py"


def load_skills():
    spec = importlib.util.spec_from_file_location("inventory_skills", SKILLS_PATH)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load skills from {SKILLS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_skill_frontmatter_extracts_fields(tmp_path):
    skills = load_skills()
    skill_file = tmp_path / "wordpress" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text(
        "\n".join(
            [
                "---",
                "name: wordpress",
                'description: "WordPress development workflow"',
                "risk: safe",
                "source: community",
                "---",
                "# WordPress",
            ]
        )
        + "\n"
    )

    parsed = skills.parse_skill_file(skill_file)

    assert parsed["name"] == "wordpress"
    assert parsed["description"] == "WordPress development workflow"
    assert parsed["risk"] == "safe"
    assert parsed["source"] == "community"


def test_classify_domain_recognizes_requested_domains():
    skills = load_skills()

    assert skills.classify_domain("wordpress-theme-development", "") == "wordpress"
    assert skills.classify_domain("shopify-automation", "") == "shopify"
    assert skills.classify_domain("n8n-workflow-patterns", "") == "n8n"
    assert skills.classify_domain("chrome-extension-developer", "") == "chrome"
    assert skills.classify_domain("gitnexus-cli", "") == "gitnexus"


def test_scan_skill_roots_returns_inventory_items(tmp_path):
    skills = load_skills()
    skill_file = tmp_path / "skills" / "shopify-automation" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(
        "---\nname: shopify-automation\ndescription: Shopify operations\n---\n"
    )

    items = skills.scan_skill_roots([tmp_path / "skills"])

    assert len(items) == 1
    assert items[0].id == "skill-shopify-automation"
    assert items[0].domain == "shopify"
    assert items[0].status == "present"
    assert items[0].recommended_action == "normalize"
