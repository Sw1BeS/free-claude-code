from __future__ import annotations

import argparse
import binascii
import html
import json
import math
import os
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

import httpx

from scripts.nerd.autonomous.intake import iso_now, record_stamp, write_brain_intake
from scripts.nerd.autonomous.models import (
    DEFAULT_CANONICAL_ROOT,
    to_pretty_json,
    write_json,
)
from scripts.nerd.brain.store import ingest_brain_record

DEFAULT_LITELLM_BASE_URL = "http://127.0.0.1:44000/v1"
DEFAULT_MODEL = "dev-coder-fast"
ENV_FILES = (
    Path("/root/.hermes/.env"),
    Path("/root/.hermes/hermes-agent/ops/hermes-evolution/env/core.env"),
)
SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")
LANDING_TERMS = (
    "landing",
    "landing page",
    "лендинг",
    "лендос",
    "site",
    "website",
    "сайт",
)


def _slugify(value: str, fallback: str = "agency-request") -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:72] or fallback


def _first_line(value: str, fallback: str = "Autonomous agency request") -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), fallback)


def _as_text(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _as_list(value: object, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        if items:
            return items[:10]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return fallback


def _detect_mode(request: str, mode: str) -> str:
    if mode != "auto":
        return mode
    lower = request.lower()
    if any(term in lower for term in LANDING_TERMS):
        return "landing_page"
    return "implementation"


def _load_env_value(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    for env_path in ENV_FILES:
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            if not line.startswith(f"{name}="):
                continue
            value = line.split("=", 1)[1].strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]
            return value
    return None


def _extract_json_object(value: str) -> dict[str, Any]:
    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model response does not contain a JSON object")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model response JSON is not an object")
    return parsed


def _fallback_spec(request: str, mode: str) -> dict[str, object]:
    title = _first_line(request)
    if mode == "landing_page":
        sections = [
            "Hero with a literal offer and primary action",
            "Audience pain and desired outcome",
            "Proof, process, and expected deliverables",
            "Pricing or next-step conversion block",
        ]
        design_direction = [
            "Full-bleed generated hero image with text over the image",
            "Restrained operational layout, compact sections, 8px card radius",
            "Warm neutral background, green system accents, coral conversion accents",
        ]
        implementation_steps = [
            "Create static responsive landing page package",
            "Generate a bitmap hero asset",
            "Write deployment manifest for Vercel/static hosting",
            "Record artifacts and memory writeback",
        ]
    else:
        sections = [
            "Problem statement",
            "Context and source data",
            "Implementation plan",
            "Verification and handoff",
        ]
        design_direction = [
            "Use the existing project patterns and registries",
            "Keep outputs auditable and bounded",
        ]
        implementation_steps = [
            "Classify request into inbox and task memory",
            "Create implementation brief",
            "Write artifact package",
            "Record run evidence",
        ]
    return {
        "title": title[:100],
        "audience": "Project operator and the autonomous agency runtime",
        "offer": title[:160],
        "sections": sections,
        "design_direction": design_direction,
        "acceptance_criteria": [
            "Request is captured in inbox/task memory",
            "Artifacts are written under the canonical delivery root",
            "A run record lists produced files and next action",
            "The package can be inspected without secrets",
        ],
        "implementation_steps": implementation_steps,
        "deployment_target": "static package; Vercel or subdomain when credentials are configured",
        "risks": [
            "External deployment requires configured credentials",
            "Live model generation can fall back to deterministic planning",
        ],
        "memory_notes": [
            "Promote reusable decisions into /root/nerd-method/memory/knowledge",
            "Keep run evidence under /root/nerd-method/memory/runs",
        ],
    }


def _normalize_spec(raw: dict[str, object], request: str, mode: str) -> dict[str, object]:
    fallback = _fallback_spec(request, mode)
    return {
        "title": _as_text(raw.get("title"), str(fallback["title"]))[:120],
        "audience": _as_text(raw.get("audience"), str(fallback["audience"])),
        "offer": _as_text(raw.get("offer"), str(fallback["offer"])),
        "sections": _as_list(raw.get("sections"), list(fallback["sections"])),
        "design_direction": _as_list(
            raw.get("design_direction"), list(fallback["design_direction"])
        ),
        "acceptance_criteria": _as_list(
            raw.get("acceptance_criteria"), list(fallback["acceptance_criteria"])
        ),
        "implementation_steps": _as_list(
            raw.get("implementation_steps"), list(fallback["implementation_steps"])
        ),
        "deployment_target": _as_text(
            raw.get("deployment_target"), str(fallback["deployment_target"])
        ),
        "risks": _as_list(raw.get("risks"), list(fallback["risks"])),
        "memory_notes": _as_list(raw.get("memory_notes"), list(fallback["memory_notes"])),
    }


def _generate_spec_with_model(
    request: str,
    *,
    mode: str,
    model: str,
    base_url: str,
    timeout_seconds: float,
) -> tuple[dict[str, object], dict[str, object]]:
    api_key = _load_env_value("HERMES_LITELLM_API_KEY")
    if not api_key:
        raise RuntimeError("HERMES_LITELLM_API_KEY is not configured")

    prompt = (
        "Return strict JSON only. Keys: title, audience, offer, sections, "
        "design_direction, acceptance_criteria, implementation_steps, "
        "deployment_target, risks, memory_notes. Build an autonomous agency "
        "delivery plan, not a chat answer. If the request is a landing page, "
        "include concrete design, build, verification, and deployment steps. "
        "Do not include secrets or shell commands that require hidden credentials."
    )
    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": f"Mode: {mode}\nRequest:\n{request}",
            },
        ],
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        response.raise_for_status()
    data = response.json()
    content = str(data["choices"][0]["message"]["content"])
    spec = _normalize_spec(_extract_json_object(content), request, mode)
    return spec, {
        "provider": "litellm",
        "model": model,
        "base_url": base_url,
        "status": "success",
    }


def build_delivery_spec(
    request: str,
    *,
    mode: str,
    model: str,
    base_url: str,
    timeout_seconds: float,
    offline: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    if offline:
        return _fallback_spec(request, mode), {
            "provider": "deterministic",
            "model": "offline",
            "status": "skipped",
        }
    try:
        return _generate_spec_with_model(
            request,
            mode=mode,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    except (httpx.HTTPError, KeyError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return _fallback_spec(request, mode), {
            "provider": "deterministic",
            "model": "fallback",
            "status": "fallback",
            "reason": f"{type(exc).__name__}: {exc}",
        }


def _markdown_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _render_prompt(request: str, spec: dict[str, object], mode: str) -> str:
    return "\n".join(
        [
            "# Agency Director Prompt",
            "",
            "You are the agency director for the NERD autonomous runtime.",
            "Turn the operator request into an artifact-backed delivery run.",
            "",
            "## Mode",
            "",
            mode,
            "",
            "## Operator Request",
            "",
            request.strip(),
            "",
            "## Delivery Contract",
            "",
            to_pretty_json(spec).strip(),
            "",
        ]
    )


def _render_brief(request: str, spec: dict[str, object], model_status: dict[str, object]) -> str:
    return "\n".join(
        [
            f"# Delivery Brief: {spec['title']}",
            "",
            f"- Generated: {iso_now()}",
            f"- Model route: {model_status.get('provider')} / {model_status.get('model')}",
            f"- Model status: {model_status.get('status')}",
            "",
            "## Request",
            "",
            request.strip(),
            "",
            "## Audience",
            "",
            str(spec["audience"]),
            "",
            "## Offer",
            "",
            str(spec["offer"]),
            "",
            "## Acceptance Criteria",
            "",
            _markdown_list(list(spec["acceptance_criteria"])),
            "",
        ]
    )


def _render_design(spec: dict[str, object]) -> str:
    return "\n".join(
        [
            f"# Design Direction: {spec['title']}",
            "",
            "## Sections",
            "",
            _markdown_list(list(spec["sections"])),
            "",
            "## Visual System",
            "",
            _markdown_list(list(spec["design_direction"])),
            "",
        ]
    )


def _render_plan(spec: dict[str, object]) -> str:
    return "\n".join(
        [
            f"# Implementation Plan: {spec['title']}",
            "",
            "## Steps",
            "",
            _markdown_list(list(spec["implementation_steps"])),
            "",
            "## Risks",
            "",
            _markdown_list(list(spec["risks"])),
            "",
        ]
    )


def _render_deployment(spec: dict[str, object], site_path: Path | None) -> str:
    site_note = str(site_path) if site_path else "No static site generated for this mode."
    return "\n".join(
        [
            f"# Deployment Handoff: {spec['title']}",
            "",
            f"- Target: {spec['deployment_target']}",
            f"- Static artifact: {site_note}",
            "",
            "## Default Path",
            "",
            "Deploy the static package with the configured Vercel, Netlify, or subdomain "
            "target when credentials are present. If no deployment target is configured, "
            "keep this package as the reviewed build artifact.",
            "",
        ]
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_generated_hero_png(path: Path, seed_text: str) -> None:
    width = 960
    height = 540
    seed = sum(ord(char) for char in seed_text) % 997
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            nx = x / width
            ny = y / height
            wave = int(18 * math.sin((nx * 8.0) + (seed / 31.0)))
            r = int(238 - 42 * ny + 18 * nx + wave)
            g = int(232 - 25 * nx + 32 * ny)
            b = int(214 + 22 * nx - 18 * ny)
            if (x - 720) ** 2 + (y - 150) ** 2 < 78_000:
                r, g, b = 48, 111, 94
            if (x - 250) ** 2 + (y - 400) ** 2 < 65_000:
                r, g, b = 217, 79, 61
            if 80 + (seed % 120) < x < 180 + (seed % 120) and 70 < y < 470:
                r = min(255, r + 12)
                g = max(0, g - 22)
                b = max(0, b - 28)
            row.extend((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
        rows.append(b"\x00" + bytes(row))
    raw = b"".join(rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _render_static_landing(spec: dict[str, object], site_dir: Path) -> Path:
    site_dir.mkdir(parents=True, exist_ok=True)
    hero_path = site_dir / "assets" / "hero.png"
    write_generated_hero_png(hero_path, str(spec["title"]))
    section_cards = "\n".join(
        f"<article><span>{index:02d}</span><p>{html.escape(section)}</p></article>"
        for index, section in enumerate(list(spec["sections"]), start=1)
    )
    criteria = "\n".join(
        f"<li>{html.escape(item)}</li>" for item in list(spec["acceptance_criteria"])[:5]
    )
    html_body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(str(spec["title"]))}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #13201e;
      --muted: #53615d;
      --paper: #f6f0e6;
      --line: #ded4c3;
      --green: #2f6f5e;
      --coral: #d94f3d;
      --gold: #efc456;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
    }}
    .hero {{
      min-height: 88vh;
      display: grid;
      align-items: end;
      position: relative;
      overflow: hidden;
      padding: 28px;
    }}
    .hero img {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, rgba(19,32,30,.92), rgba(19,32,30,.58) 52%, rgba(19,32,30,.08));
    }}
    .hero-content {{
      position: relative;
      z-index: 1;
      max-width: 760px;
      padding-bottom: 42px;
      color: #fffaf0;
    }}
    .eyebrow {{
      text-transform: uppercase;
      font-size: 13px;
      letter-spacing: 0;
      color: var(--gold);
      font-weight: 700;
    }}
    h1 {{
      font-size: clamp(42px, 7vw, 88px);
      line-height: .94;
      margin: 14px 0 18px;
      letter-spacing: 0;
      max-width: 820px;
    }}
    .lead {{
      max-width: 660px;
      font-size: 19px;
      line-height: 1.55;
      margin: 0 0 26px;
    }}
    .actions {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    a.button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 18px;
      border-radius: 8px;
      background: var(--coral);
      color: white;
      text-decoration: none;
      font-weight: 700;
    }}
    a.button.secondary {{
      background: rgba(255,255,255,.14);
      border: 1px solid rgba(255,255,255,.34);
    }}
    main {{
      padding: 46px 28px 72px;
    }}
    .wrap {{
      max-width: 1120px;
      margin: 0 auto;
    }}
    .section-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    article {{
      min-height: 144px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      background: rgba(255,255,255,.48);
    }}
    article span {{
      color: var(--green);
      font-weight: 800;
      font-size: 13px;
    }}
    article p {{
      margin: 20px 0 0;
      color: var(--ink);
      line-height: 1.45;
    }}
    .proof {{
      margin-top: 34px;
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(260px, .7fr);
      gap: 28px;
      align-items: start;
    }}
    h2 {{
      font-size: 31px;
      line-height: 1.1;
      margin: 0 0 16px;
      letter-spacing: 0;
    }}
    li {{
      margin: 10px 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .panel {{
      border-left: 4px solid var(--green);
      padding: 4px 0 4px 18px;
    }}
    @media (max-width: 720px) {{
      .hero {{
        min-height: 86vh;
        padding: 18px;
      }}
      .hero-content {{
        padding-bottom: 26px;
      }}
      .proof {{
        grid-template-columns: 1fr;
      }}
      main {{
        padding-inline: 18px;
      }}
    }}
  </style>
</head>
<body>
  <section class="hero">
    <img src="assets/hero.png" alt="">
    <div class="hero-content">
      <div class="eyebrow">Autonomous delivery package</div>
      <h1>{html.escape(str(spec["title"]))}</h1>
      <p class="lead">{html.escape(str(spec["offer"]))}</p>
      <div class="actions">
        <a class="button" href="#delivery">Start</a>
        <a class="button secondary" href="#proof">Review proof</a>
      </div>
    </div>
  </section>
  <main id="delivery">
    <div class="wrap">
      <div class="section-grid">
        {section_cards}
      </div>
      <section class="proof" id="proof">
        <div>
          <h2>Delivery Criteria</h2>
          <ul>{criteria}</ul>
        </div>
        <div class="panel">
          <h2>Target</h2>
          <p>{html.escape(str(spec["deployment_target"]))}</p>
        </div>
      </section>
    </div>
  </main>
</body>
</html>
"""
    index_path = site_dir / "index.html"
    index_path.write_text(html_body, encoding="utf-8")
    return index_path


def _write_text(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")
    return path


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def run_delivery(
    request: str,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    output_root: Path | None = None,
    source: str = "manual",
    mode: str = "auto",
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_LITELLM_BASE_URL,
    timeout_seconds: float = 90.0,
    offline: bool = True,
    dry_run: bool = False,
    no_intake: bool = False,
    build_static_site: bool = True,
) -> dict[str, object]:
    request = request.strip()
    if not request:
        raise ValueError("request text is required")
    canonical_root = Path(canonical_root)
    output_root = Path(output_root) if output_root else canonical_root / "artifacts" / "deliveries"
    resolved_mode = _detect_mode(request, mode)
    stamp = record_stamp()
    slug = _slugify(_first_line(request))
    delivery_dir = output_root / f"{stamp}-{slug}"

    spec, model_status = build_delivery_spec(
        request,
        mode=resolved_mode,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        offline=offline,
    )
    spec["mode"] = resolved_mode

    planned_paths = {
        "delivery_dir": str(delivery_dir),
        "prompt": str(delivery_dir / "agency-prompt.md"),
        "brief": str(delivery_dir / "01-brief.md"),
        "design": str(delivery_dir / "02-design.md"),
        "implementation_plan": str(delivery_dir / "03-implementation-plan.md"),
        "deployment": str(delivery_dir / "04-deployment.md"),
        "run": str(delivery_dir / "run.json"),
    }
    if resolved_mode == "landing_page" and build_static_site:
        planned_paths["site"] = str(delivery_dir / "site" / "index.html")

    if dry_run:
        return {
            "status": "dry_run",
            "mode": resolved_mode,
            "model": model_status,
            "spec": spec,
            "paths": planned_paths,
        }

    intake = None
    if not no_intake:
        intake = write_brain_intake(
            request,
            canonical_root=canonical_root,
            source=source,
        )

    site_path = None
    if resolved_mode == "landing_page" and build_static_site:
        site_path = _render_static_landing(spec, delivery_dir / "site")

    artifact_paths = [
        _write_text(delivery_dir / "00-request.md", request),
        _write_text(delivery_dir / "agency-prompt.md", _render_prompt(request, spec, resolved_mode)),
        _write_text(delivery_dir / "01-brief.md", _render_brief(request, spec, model_status)),
        _write_text(delivery_dir / "02-design.md", _render_design(spec)),
        _write_text(delivery_dir / "03-implementation-plan.md", _render_plan(spec)),
        _write_text(delivery_dir / "04-deployment.md", _render_deployment(spec, site_path)),
    ]
    if site_path:
        artifact_paths.append(site_path)
        artifact_paths.append(site_path.parent / "assets" / "hero.png")

    task_id = None
    if isinstance(intake, dict) and isinstance(intake.get("task"), dict):
        task_id = str(intake["task"].get("id") or "")
    run_id = f"agency_delivery_{stamp}_{slug}"
    run_record: dict[str, object] = {
        "id": run_id,
        "kind": "agency_delivery",
        "status": "success",
        "created_at": iso_now(),
        "request": request,
        "mode": resolved_mode,
        "source": source,
        "task_id": task_id,
        "model": model_status,
        "title": spec["title"],
        "artifact_paths": [str(path) for path in artifact_paths],
        "site_path": str(site_path) if site_path else None,
        "next_action": "review_or_deploy",
    }
    run_path = write_json(delivery_dir / "run.json", run_record)
    artifact_paths.append(run_path)
    run_record["artifact_paths"] = [str(path) for path in artifact_paths]
    write_json(run_path, run_record)
    _append_jsonl(canonical_root / "memory" / "runs" / "agency-deliveries.jsonl", run_record)

    brain_record = ingest_brain_record(
        text="\n".join(
            [
                str(spec["title"]),
                request,
                "Artifacts:",
                *[str(path) for path in artifact_paths],
            ]
        ),
        source="agency_delivery",
        title=str(spec["title"]),
        summary=f"Agency delivery package for {spec['title']}",
        canonical_root=canonical_root,
        kind="delivery_run",
        privacy="project",
        risk="medium",
        task_id=task_id,
        candidate_id=run_id,
        artifact_path=str(run_path),
        markdown_path=str(delivery_dir / "01-brief.md"),
        metadata={"mode": resolved_mode, "model": model_status},
    )

    return {
        "status": "success",
        "mode": resolved_mode,
        "run_id": run_id,
        "title": spec["title"],
        "paths": {**planned_paths, "run": str(run_path)},
        "artifact_paths": [str(path) for path in artifact_paths],
        "model": model_status,
        "intake": {
            "inbox_path": str(intake["paths"]["inbox"]) if intake else None,
            "task_path": str(intake["paths"]["task"]) if intake else None,
        },
        "brain_store": brain_record,
    }


def _read_request(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    positional = " ".join(args.request).strip()
    if positional:
        return positional
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an autonomous agency delivery lane.")
    parser.add_argument("request", nargs="*", help="Operator request text.")
    parser.add_argument("--text")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--canonical-root", type=Path, default=DEFAULT_CANONICAL_ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--source", default="manual")
    parser.add_argument(
        "--mode",
        choices=("auto", "landing_page", "implementation"),
        default="auto",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_LITELLM_BASE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.set_defaults(offline=True)
    parser.add_argument("--offline", dest="offline", action="store_true")
    parser.add_argument("--live-model", dest="offline", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-intake", action="store_true")
    parser.add_argument("--no-static-site", action="store_true")
    args = parser.parse_args(argv)

    result = run_delivery(
        _read_request(args),
        canonical_root=args.canonical_root,
        output_root=args.output_root,
        source=args.source,
        mode=args.mode,
        model=args.model,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        offline=args.offline,
        dry_run=args.dry_run,
        no_intake=args.no_intake,
        build_static_site=not args.no_static_site,
    )
    sys.stdout.write(to_pretty_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
