from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.nerd.autonomous.bootstrap import generated_at
from scripts.nerd.autonomous.models import DEFAULT_CANONICAL_ROOT, write_json


def _skill(
    *,
    id: str,
    name: str,
    source: str,
    category: str,
    status: str,
    risk_level: str,
    tools_required: list[str],
    install_state: str,
    notes: str,
) -> dict[str, object]:
    return {
        "id": id,
        "name": name,
        "source": source,
        "category": category,
        "status": status,
        "risk_level": risk_level,
        "tools_required": sorted(tools_required),
        "install_state": install_state,
        "last_reviewed": "2026-05-25",
        "notes": notes,
    }


def build_skills_registry(
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
) -> dict[str, object]:
    canonical_root = Path(canonical_root)
    items = [
        _skill(
            id="skill-memory-curation",
            name="Memory Curation",
            source="nerd-method",
            category="knowledge",
            status="approved",
            risk_level="low",
            tools_required=["filesystem"],
            install_state="available",
            notes="Promotes inbox/task outputs into reviewed NERD OS knowledge.",
        ),
        _skill(
            id="skill-hermes-operations",
            name="Hermes Operations",
            source="hermes-agent",
            category="operations",
            status="approved",
            risk_level="medium",
            tools_required=["systemctl", "docker", "filesystem"],
            install_state="available",
            notes="Read-only and guarded Hermes runtime operation routines.",
        ),
        _skill(
            id="skill-repo-radar",
            name="GitHub Radar",
            source="git-inspired",
            category="research",
            status="custom",
            risk_level="low",
            tools_required=["git", "codegraph"],
            install_state="planned",
            notes="Repository discovery, triage, and trend intake for NERD OS tasks.",
        ),
    ]
    return {
        "generated_at": generated_at(),
        "canonical_root": str(canonical_root),
        "items": sorted(items, key=lambda item: str(item["id"])),
    }


def write_skills_registry(canonical_root: Path = DEFAULT_CANONICAL_ROOT) -> Path:
    output = Path(canonical_root) / "registry" / "skills-registry.json"
    return write_json(output, build_skills_registry(canonical_root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write NERD OS skills registry.")
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    args = parser.parse_args(argv)
    output = write_skills_registry(args.canonical_root)
    sys.stdout.write(str(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
