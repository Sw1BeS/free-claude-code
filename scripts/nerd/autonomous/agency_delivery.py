from __future__ import annotations

import argparse
import binascii
import hashlib
import html
import json
import math
import os
import re
import shlex
import shutil
import struct
import subprocess
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
BROWSER_ENV_NAMES = (
    "NERD_BROWSER_COMMAND",
    "NERD_BROWSER_BINARY",
    "CHROME_PATH",
)
BROWSER_COMMAND_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
)
BROWSER_FIXED_PATHS = (
    Path("/opt/google/chrome/chrome"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/google-chrome-stable"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
)
DEPLOYMENT_TARGETS_RELATIVE_PATH = Path("system/deployment-targets.json")
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
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*([^\s,;&]+)"
)
SECRET_TOKEN_RE = re.compile(r"(?i)\b(sk-[a-z0-9._-]+|bearer\s+[a-z0-9._~+/=-]+)")


def _redact_sensitive_text(value: str) -> str:
    redacted = SECRET_TOKEN_RE.sub("[REDACTED]", value)
    redacted = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    return redacted


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
            "NERD-OS Palette 3: obsidian base, emerald operations, dusty violet memory paths",
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
            r = int(8 + 18 * nx + 16 * ny + wave / 3)
            g = int(11 + 24 * nx + 18 * ny)
            b = int(17 + 38 * nx + 26 * ny)
            if (x - 720) ** 2 + (y - 150) ** 2 < 78_000:
                r, g, b = 34, 197, 94
            if (x - 250) ** 2 + (y - 400) ** 2 < 65_000:
                r, g, b = 109, 80, 182
            if 80 + (seed % 120) < x < 180 + (seed % 120) and 70 < y < 470:
                r = min(255, r + 84)
                g = min(255, g + 58)
                b = min(255, b + 20)
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
      color-scheme: dark;
      --nerd-bg: #080B11;
      --nerd-panel: #101722;
      --nerd-panel-2: #151D2A;
      --nerd-text: #F2F7F4;
      --nerd-muted: #9CA8B6;
      --nerd-line: #263241;
      --nerd-emerald: #22C55E;
      --nerd-violet: #6D50B6;
      --nerd-amber: #EAB308;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 18% 12%, rgba(34,197,94,.16), transparent 32%),
        radial-gradient(circle at 76% 18%, rgba(109,80,182,.18), transparent 30%),
        var(--nerd-bg);
      color: var(--nerd-text);
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
      background: linear-gradient(90deg, rgba(8,11,17,.96), rgba(8,11,17,.68) 52%, rgba(8,11,17,.22));
    }}
    .hero-content {{
      position: relative;
      z-index: 1;
      max-width: 760px;
      padding-bottom: 42px;
      color: var(--nerd-text);
    }}
    .eyebrow {{
      text-transform: uppercase;
      font-size: 13px;
      letter-spacing: 0;
      color: var(--nerd-emerald);
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
      background: var(--nerd-emerald);
      color: #06100A;
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
      border: 1px solid var(--nerd-line);
      border-radius: 8px;
      padding: 18px;
      background: linear-gradient(180deg, rgba(21,29,42,.92), rgba(16,23,34,.82));
    }}
    article span {{
      color: var(--nerd-emerald);
      font-weight: 800;
      font-size: 13px;
    }}
    article p {{
      margin: 20px 0 0;
      color: var(--nerd-text);
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
      color: var(--nerd-muted);
      line-height: 1.45;
    }}
    .panel {{
      border-left: 4px solid var(--nerd-violet);
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


def _idempotency_key(*, request: str, mode: str, source: str) -> str:
    source_text = "\n".join([_redact_sensitive_text(request), mode, source])
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _verification_for(
    *,
    mode: str,
    site_path: Path | None,
    artifact_paths: list[Path],
    dry_run: bool = False,
    static_site_expected: bool = True,
) -> dict[str, str]:
    if dry_run:
        return {
            "request_captured": "planned",
            "artifacts_written": "planned",
            "html_smoke": "planned"
            if mode == "landing_page" and static_site_expected
            else "not_applicable",
            "asset_smoke": "planned"
            if mode == "landing_page" and static_site_expected
            else "not_applicable",
            "browser_smoke": "not_run",
        }
    html_smoke = "not_applicable"
    asset_smoke = "not_applicable"
    if mode == "landing_page" and static_site_expected:
        html_smoke = "passed" if site_path and site_path.is_file() else "failed"
        hero_path = site_path.parent / "assets" / "hero.png" if site_path else None
        asset_smoke = "passed" if hero_path and hero_path.is_file() else "failed"
    return {
        "request_captured": "passed",
        "artifacts_written": "passed" if artifact_paths else "failed",
        "html_smoke": html_smoke,
        "asset_smoke": asset_smoke,
        "browser_smoke": "not_run",
    }


def _playwright_browser_paths() -> list[Path]:
    cache_root = Path.home() / ".cache" / "ms-playwright"
    if not cache_root.is_dir():
        return []
    return sorted(cache_root.glob("chromium-*/chrome-linux*/chrome"), reverse=True)


def _browser_command_from_value(value: str) -> list[str] | None:
    parts = shlex.split(value)
    if not parts:
        return None
    executable = parts[0]
    resolved = shutil.which(executable)
    if resolved:
        return [resolved, *parts[1:]]
    path = Path(executable).expanduser()
    if path.is_file() and os.access(path, os.X_OK):
        return [str(path), *parts[1:]]
    return None


def _discover_browser_command() -> list[str] | None:
    for env_name in BROWSER_ENV_NAMES:
        value = os.environ.get(env_name)
        if not value:
            continue
        command = _browser_command_from_value(value)
        if command:
            return command
        return None
    for name in BROWSER_COMMAND_NAMES:
        resolved = shutil.which(name)
        if resolved:
            return [resolved]
    for path in [*BROWSER_FIXED_PATHS, *_playwright_browser_paths()]:
        if path.is_file() and os.access(path, os.X_OK):
            return [str(path)]
    return None


def _run_browser_smoke(site_path: Path | None, delivery_dir: Path) -> dict[str, object]:
    if site_path is None:
        return {"status": "not_applicable"}
    browser_command = _discover_browser_command()
    if not browser_command:
        return {
            "status": "blocked_missing_browser",
            "blocker": "Browser smoke is blocked until browser tooling is available.",
        }

    screenshot_path = delivery_dir / "verification" / "browser-smoke.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        *browser_command,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        f"--screenshot={screenshot_path}",
        "--window-size=1366,900",
        site_path.resolve().as_uri(),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=site_path.parent,
            timeout=30,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return {
            "status": "blocked_missing_browser",
            "blocker": "Browser smoke is blocked until browser tooling is available.",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "blocker": "Browser smoke timed out while rendering the static artifact.",
        }

    if completed.returncode != 0:
        stderr = _redact_sensitive_text((completed.stderr or completed.stdout).strip())
        return {
            "status": "failed",
            "blocker": (
                "Browser smoke failed while rendering the static artifact."
                if not stderr
                else f"Browser smoke failed while rendering the static artifact: {stderr[:180]}"
            ),
        }
    if not screenshot_path.is_file() or screenshot_path.stat().st_size <= 0:
        return {
            "status": "failed",
            "blocker": "Browser smoke did not produce a screenshot artifact.",
        }
    if not screenshot_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        return {
            "status": "failed",
            "blocker": "Browser smoke screenshot is not a PNG artifact.",
        }
    return {
        "status": "passed",
        "artifact_path": screenshot_path,
    }


def _load_deployment_targets(canonical_root: Path) -> dict[str, object] | None:
    targets_path = canonical_root / DEPLOYMENT_TARGETS_RELATIVE_PATH
    if not targets_path.is_file():
        return None
    try:
        payload = json.loads(targets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid",
            "reason": "Deployment target metadata is not valid JSON.",
        }
    return payload if isinstance(payload, dict) else {
        "status": "invalid",
        "reason": "Deployment target metadata must be a JSON object.",
    }


def _select_static_deployment_target(
    metadata: dict[str, object] | None,
) -> dict[str, object] | None:
    if not metadata or metadata.get("status") == "invalid":
        return None
    targets = metadata.get("targets")
    if not isinstance(targets, list):
        return None
    default_id = str(metadata.get("default_static_target") or "").strip()
    normalized_targets = [
        target
        for target in targets
        if isinstance(target, dict)
        and str(target.get("artifact_kind") or "").strip() == "static_site"
        and str(target.get("status") or "").strip() == "configured"
    ]
    if default_id:
        for target in normalized_targets:
            if str(target.get("id") or "").strip() == default_id:
                return target
    return normalized_targets[0] if normalized_targets else None


def _deployment_for(
    *,
    canonical_root: Path,
    site_path: Path | None,
    run_id: str,
    spec: dict[str, object],
    auto_deploy: bool,
) -> dict[str, object]:
    if site_path is None:
        return {
            "status": "not_applicable",
            "target": _redact_sensitive_text(str(spec.get("deployment_target") or "")),
        }

    metadata = _load_deployment_targets(canonical_root)
    if isinstance(metadata, dict) and metadata.get("status") == "invalid":
        return {
            "status": "blocked_invalid_deployment_target",
            "target": _redact_sensitive_text(str(spec.get("deployment_target") or "")),
            "blocker": str(metadata.get("reason") or "Deployment target metadata is invalid."),
        }

    target = _select_static_deployment_target(metadata)
    if target is None:
        return {
            "status": "deployment_ready",
            "target": _redact_sensitive_text(str(spec.get("deployment_target") or "")),
            "target_metadata": "missing",
            "blocker": "Deployment target metadata is not configured.",
        }

    target_id = _slugify(str(target.get("id") or "static-target"), fallback="static-target")
    provider = str(target.get("provider") or "unknown").strip()
    credentials = str(target.get("credentials") or "not_configured").strip()
    deployment: dict[str, object] = {
        "status": "target_configured",
        "target_id": target_id,
        "provider": provider,
        "credentials": credentials,
    }
    if not auto_deploy or target.get("auto_promote") is not True:
        return deployment
    if provider != "nginx_static":
        return {
            **deployment,
            "status": "blocked_unsupported_provider",
            "blocker": "Configured deployment target provider is not supported by local promotion.",
        }
    if credentials != "not_required":
        return {
            **deployment,
            "status": "blocked_missing_credentials",
            "blocker": "Configured deployment target requires credentials that are not available to this lane.",
        }

    raw_local_root = str(target.get("local_root") or "").strip()
    public_base_url = str(target.get("public_base_url") or "").strip()
    if not raw_local_root or not public_base_url:
        return {
            **deployment,
            "status": "blocked_invalid_deployment_target",
            "blocker": "Configured deployment target is missing local_root or public_base_url.",
        }

    local_root = Path(raw_local_root).expanduser()
    destination = local_root / run_id
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(site_path.parent, destination)
        _make_static_tree_public_readable(destination)
    except OSError as exc:
        return {
            **deployment,
            "status": "failed",
            "blocker": f"Static promotion failed: {_redact_sensitive_text(str(exc))[:180]}",
        }

    return {
        **deployment,
        "status": "deployed",
        "public_url": f"{public_base_url.rstrip('/')}/{run_id}/",
    }


def _deploy_smoke_status(deployment: dict[str, object]) -> str:
    status = str(deployment.get("status") or "").strip()
    if status == "deployed":
        return "passed"
    if status == "not_applicable":
        return "not_applicable"
    if status == "target_configured":
        return "not_run"
    if status == "deployment_ready":
        return "blocked_missing_deployment_target"
    if status.startswith("blocked_"):
        return status
    if status == "failed":
        return "failed"
    return "unknown"


def _make_static_tree_public_readable(root: Path) -> None:
    root.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o644)


def run_delivery(
    request: str,
    *,
    canonical_root: Path = DEFAULT_CANONICAL_ROOT,
    output_root: Path | None = None,
    source: str = "manual",
    task_id: str | None = None,
    mode: str = "auto",
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_LITELLM_BASE_URL,
    timeout_seconds: float = 90.0,
    offline: bool = True,
    dry_run: bool = False,
    no_intake: bool = False,
    build_static_site: bool = True,
    browser_smoke: bool = True,
    auto_deploy: bool = False,
) -> dict[str, object]:
    request = request.strip()
    if not request:
        raise ValueError("request text is required")
    safe_request = _redact_sensitive_text(request)
    safe_task_id = (
        re.sub(r"[^A-Za-z0-9_.:-]+", "_", task_id.strip())[:128]
        if task_id and task_id.strip()
        else ""
    )
    canonical_root = Path(canonical_root)
    output_root = Path(output_root) if output_root else canonical_root / "artifacts" / "deliveries"
    resolved_mode = _detect_mode(safe_request, mode)
    stamp = record_stamp()
    slug = _slugify(_first_line(safe_request))
    delivery_dir = output_root / f"{stamp}-{slug}"
    idempotency_key = _idempotency_key(
        request=safe_request,
        mode=resolved_mode,
        source=source,
    )

    spec, model_status = build_delivery_spec(
        safe_request,
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
            "run_id": f"agency_delivery_{stamp}_{slug}",
            "task_id": safe_task_id or f"task_{stamp}",
            "title": spec["title"],
            "model": model_status,
            "spec": spec,
            "paths": planned_paths,
            "verification": _verification_for(
                mode=resolved_mode,
                site_path=None,
                artifact_paths=[],
                dry_run=True,
                static_site_expected=build_static_site,
            ),
            "idempotency_key": idempotency_key,
            "artifact_paths": [],
            "next_action": "review_or_run",
            "deployment": {"status": "planned"},
        }

    intake = None
    if not no_intake:
        intake = write_brain_intake(
            safe_request,
            canonical_root=canonical_root,
            source=source,
        )

    site_path = None
    if resolved_mode == "landing_page" and build_static_site:
        site_path = _render_static_landing(spec, delivery_dir / "site")

    artifact_paths = [
        _write_text(delivery_dir / "00-request.md", safe_request),
        _write_text(delivery_dir / "agency-prompt.md", _render_prompt(safe_request, spec, resolved_mode)),
        _write_text(delivery_dir / "01-brief.md", _render_brief(safe_request, spec, model_status)),
        _write_text(delivery_dir / "02-design.md", _render_design(spec)),
        _write_text(delivery_dir / "03-implementation-plan.md", _render_plan(spec)),
        _write_text(delivery_dir / "04-deployment.md", _render_deployment(spec, site_path)),
    ]
    if site_path:
        artifact_paths.append(site_path)
        artifact_paths.append(site_path.parent / "assets" / "hero.png")

    task_id = safe_task_id or f"task_{stamp}"
    if isinstance(intake, dict) and isinstance(intake.get("task"), dict):
        task_id = safe_task_id or str(intake["task"].get("id") or task_id)
    verification = _verification_for(
        mode=resolved_mode,
        site_path=site_path,
        artifact_paths=artifact_paths,
        static_site_expected=build_static_site,
    )
    blocker = ""
    browser_smoke_artifact = None
    if browser_smoke and resolved_mode == "landing_page" and site_path:
        browser_result = _run_browser_smoke(site_path, delivery_dir)
        verification["browser_smoke"] = str(browser_result["status"])
        if isinstance(browser_result.get("artifact_path"), Path):
            browser_smoke_artifact = browser_result["artifact_path"]
            artifact_paths.append(browser_smoke_artifact)
        if browser_result.get("blocker"):
            blocker = str(browser_result["blocker"])

    run_id = f"agency_delivery_{stamp}_{slug}"
    deployment = _deployment_for(
        canonical_root=canonical_root,
        site_path=site_path,
        run_id=run_id,
        spec=spec,
        auto_deploy=auto_deploy,
    )
    verification["deploy_smoke"] = _deploy_smoke_status(deployment)
    if not blocker and deployment.get("blocker"):
        blocker = str(deployment["blocker"])

    status = "success"
    next_action = "review_or_deploy"
    if verification["html_smoke"] == "failed" or verification["asset_smoke"] == "failed":
        status = "partial"
        next_action = "fix_blocker"
    elif verification["browser_smoke"] in {
        "blocked_missing_browser",
        "failed",
    }:
        status = "partial"
        next_action = "configure_browser" if verification["browser_smoke"] == "blocked_missing_browser" else "fix_blocker"
    elif verification["deploy_smoke"] == "passed":
        next_action = "review_public_url"
    elif verification["deploy_smoke"] in {
        "blocked_missing_deployment_target",
        "blocked_invalid_deployment_target",
        "blocked_unsupported_provider",
        "blocked_missing_credentials",
    }:
        next_action = "configure_deploy_target"
    elif verification["deploy_smoke"] == "failed":
        status = "partial"
        next_action = "fix_blocker"
    elif resolved_mode == "landing_page" and not site_path:
        next_action = "review_artifacts"
    run_record: dict[str, object] = {
        "id": run_id,
        "kind": "agency_delivery",
        "status": status,
        "created_at": iso_now(),
        "request": safe_request,
        "mode": resolved_mode,
        "source": source,
        "task_id": task_id,
        "model": model_status,
        "title": spec["title"],
        "artifact_paths": [str(path) for path in artifact_paths],
        "site_path": str(site_path) if site_path else None,
        "verification": verification,
        "deployment_target": _redact_sensitive_text(str(spec.get("deployment_target") or "")),
        "deployment": deployment,
        "idempotency_key": idempotency_key,
        "next_action": next_action,
    }
    if blocker:
        run_record["blocker"] = blocker
    if browser_smoke_artifact:
        run_record["browser_smoke_artifact"] = str(browser_smoke_artifact)
    run_path = write_json(delivery_dir / "run.json", run_record)
    artifact_paths.append(run_path)
    run_record["artifact_paths"] = [str(path) for path in artifact_paths]
    write_json(run_path, run_record)
    _append_jsonl(canonical_root / "memory" / "runs" / "agency-deliveries.jsonl", run_record)

    brain_record = ingest_brain_record(
        text="\n".join(
            [
                str(spec["title"]),
                safe_request,
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
        "status": status,
        "mode": resolved_mode,
        "run_id": run_id,
        "task_id": task_id,
        "title": spec["title"],
        "paths": {**planned_paths, "run": str(run_path)},
        "artifact_paths": [str(path) for path in artifact_paths],
        "model": model_status,
        "verification": run_record["verification"],
        "deployment": run_record["deployment"],
        "idempotency_key": idempotency_key,
        "next_action": next_action,
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
    parser.add_argument("--task-id")
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
    parser.set_defaults(browser_smoke=True)
    parser.add_argument("--browser-smoke", dest="browser_smoke", action="store_true")
    parser.add_argument("--no-browser-smoke", dest="browser_smoke", action="store_false")
    parser.set_defaults(auto_deploy=False)
    parser.add_argument("--auto-deploy", dest="auto_deploy", action="store_true")
    parser.add_argument("--no-auto-deploy", dest="auto_deploy", action="store_false")
    args = parser.parse_args(argv)

    result = run_delivery(
        _read_request(args),
        canonical_root=args.canonical_root,
        output_root=args.output_root,
        source=args.source,
        task_id=args.task_id,
        mode=args.mode,
        model=args.model,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        offline=args.offline,
        dry_run=args.dry_run,
        no_intake=args.no_intake,
        build_static_site=not args.no_static_site,
        browser_smoke=args.browser_smoke,
        auto_deploy=args.auto_deploy,
    )
    sys.stdout.write(to_pretty_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
