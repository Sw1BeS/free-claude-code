import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN_PATH = ROOT / "scripts" / "nerd" / "inventory" / "brain.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_brain_report_contains_canonical_sources_and_sync_targets(tmp_path):
    brain = load_module("inventory_brain_sources", BRAIN_PATH)
    workspace_root = tmp_path / "workspace"
    staging_dir = tmp_path / "staging"
    agency_stack_dir = tmp_path / "agency-stack"
    nerd_method_dir = tmp_path / "nerd-method"
    obsidian_vault_dir = tmp_path / "obsidian-vault"
    (staging_dir / "scripts" / "nerd" / "agency").mkdir(parents=True)
    (staging_dir / "scripts" / "nerd" / "agency" / "openwebui_seed.py").write_text(
        "# seed\n", encoding="utf-8"
    )
    (staging_dir / "scripts" / "nerd").mkdir(parents=True, exist_ok=True)
    (staging_dir / "scripts" / "nerd" / "generate_inventory.py").write_text(
        "# generate\n", encoding="utf-8"
    )
    (agency_stack_dir / "scripts").mkdir(parents=True)
    (agency_stack_dir / "scripts" / "seed-openwebui.sh").write_text(
        "#!/usr/bin/env bash\n", encoding="utf-8"
    )
    (nerd_method_dir / ".git").mkdir(parents=True)
    obsidian_vault_dir.mkdir(parents=True)
    (obsidian_vault_dir / "one.md").write_text("# One\n", encoding="utf-8")
    (obsidian_vault_dir / "two.md").write_text("# Two\n", encoding="utf-8")

    report = brain.build_brain_report(
        workspace_root,
        agency_stack_dir,
        staging_dir,
        nerd_method_dir,
        obsidian_vault_dir,
    )
    by_id = {item.id: item for item in report.items}

    assert {
        "brain-canonical-repo",
        "brain-runtime-stack",
        "brain-nerd-method",
        "brain-openwebui-knowledge",
        "brain-obsidian-vault",
        "brain-gitnexus",
        "brain-n8n",
        "brain-langfuse",
        "brain-sync-openwebui-seed",
        "brain-sync-inventory",
        "brain-sync-stack-seed",
    } == set(by_id)
    assert by_id["brain-canonical-repo"].status == "present"
    assert by_id["brain-runtime-stack"].domain == "brain-runtime"
    assert by_id["brain-nerd-method"].recommended_action == "normalize"
    assert by_id["brain-gitnexus"].status == "active"
    assert by_id["brain-n8n"].status == "active"
    assert by_id["brain-langfuse"].status == "active"
    assert by_id["brain-gitnexus"].source_url == (
        "https://agency.umanoff-analytics.space/nerd-os/"
    )
    assert by_id["brain-n8n"].source_url == (
        "https://automations.umanoff-analytics.space"
    )
    assert by_id["brain-langfuse"].source_url == "https://obs.umanoff-analytics.space"
    assert by_id["brain-sync-openwebui-seed"].status == "present"
    assert by_id["brain-sync-stack-seed"].domain == "brain-sync"
    assert report.warnings == []


def test_brain_report_investigates_missing_paths_and_warns_on_brain_gaps(tmp_path):
    brain = load_module("inventory_brain_warnings", BRAIN_PATH)
    workspace_root = tmp_path / "workspace"
    staging_dir = tmp_path / "staging"
    agency_stack_dir = tmp_path / "missing-stack"
    nerd_method_dir = tmp_path / "nerd-method"
    obsidian_vault_dir = tmp_path / "obsidian-vault"
    nerd_method_dir.mkdir()
    obsidian_vault_dir.mkdir()
    (obsidian_vault_dir / "only.md").write_text("# Only\n", encoding="utf-8")

    report = brain.build_brain_report(
        workspace_root,
        agency_stack_dir,
        staging_dir,
        nerd_method_dir,
        obsidian_vault_dir,
    )
    by_id = {item.id: item for item in report.items}
    notes = "\n".join(item.notes or "" for item in report.items)

    assert by_id["brain-canonical-repo"].status == "investigate"
    assert by_id["brain-runtime-stack"].status == "investigate"
    assert by_id["brain-sync-inventory"].status == "investigate"
    assert any(
        "fewer than two Markdown notes" in warning for warning in report.warnings
    )
    assert any("not a git repository" in warning for warning in report.warnings)
    assert "sk-" not in notes
    assert "password" not in notes.lower()
    assert "api_key" not in notes.lower()


def test_brain_report_public_service_links_do_not_expose_local_ips(tmp_path):
    brain = load_module("inventory_brain_domain_routes", BRAIN_PATH)

    report = brain.build_brain_report(
        tmp_path / "workspace",
        tmp_path / "agency-stack",
        tmp_path / "staging",
        tmp_path / "nerd-method",
        tmp_path / "obsidian-vault",
    )
    text = "\n".join(
        " ".join([item.source_url or "", item.notes or "", *item.evidence])
        for item in report.items
    )

    assert "https://agency.umanoff-analytics.space" in text
    assert "http://127.0.0.1" not in text
    assert "http://172.20.0.1" not in text
    assert "localhost" not in text
