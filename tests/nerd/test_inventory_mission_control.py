import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MISSION_PATH = ROOT / "scripts" / "nerd" / "inventory" / "mission_control.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or not isinstance(spec.loader, SourceFileLoader):
        raise AssertionError(f"Unable to load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mission_control_report_contains_public_subdomains_and_memory_layers(tmp_path):
    mission = load_module("inventory_mission_control_system_map", MISSION_PATH)

    report = mission.build_mission_control_report(tmp_path)
    ids = {item.id for item in report.items}

    assert {
        "public-domain-agency",
        "public-domain-memory",
        "public-domain-automations",
        "memory-layer-system",
        "memory-layer-projects",
        "memory-layer-clients",
        "memory-layer-prompts",
        "memory-layer-traces",
    }.issubset(ids)

    memory = next(item for item in report.items if item.id == "memory-layer-system")
    assert memory.domain == "unified-memory"
    assert "Open WebUI knowledge" in (memory.notes or "")


def test_mission_control_report_presents_domain_routes_not_local_ips(tmp_path):
    mission = load_module("inventory_mission_control_domain_routes", MISSION_PATH)

    report = mission.build_mission_control_report(tmp_path)
    text = "\n".join(
        " ".join(
            [
                item.path or "",
                item.source_url or "",
                item.notes or "",
                *item.evidence,
            ]
        )
        for item in report.items
    )

    assert "https://agency.umanoff-analytics.space" in text
    assert "https://automations.umanoff-analytics.space" in text
    assert "https://obs.umanoff-analytics.space" in text
    assert "http://127.0.0.1" not in text
    assert "http://172.20.0.1" not in text
    assert "localhost" not in text
