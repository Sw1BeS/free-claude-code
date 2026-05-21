#!/usr/bin/env python3
"""Migrate legacy free-claude-code environment settings into managed config."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


DEFAULT_LEGACY_ENV = Path("/root/free-claude-code/.env")
DEFAULT_MANAGED_ENV = Path.home() / ".fcc" / ".env"
STAGED_HOST = "127.0.0.1"
STAGED_PORT = "18082"

ALLOWED_KEYS = frozenset(
    {
        "ALLOWED_DIR",
        "ALLOWED_DISCORD_CHANNELS",
        "ALLOWED_TELEGRAM_USER_ID",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CLI_BIN",
        "CLAUDE_WORKSPACE",
        "DEEPSEEK_API_KEY",
        "DISCORD_BOT_TOKEN",
        "ENABLE_HAIKU_THINKING",
        "ENABLE_MODEL_THINKING",
        "ENABLE_OPUS_THINKING",
        "ENABLE_SONNET_THINKING",
        "ENABLE_WEB_SERVER_TOOLS",
        "FAST_PREFIX_DETECTION",
        "FIREWORKS_API_KEY",
        "HF_TOKEN",
        "HTTP_CONNECT_TIMEOUT",
        "HTTP_READ_TIMEOUT",
        "HTTP_WRITE_TIMEOUT",
        "KIMI_API_KEY",
        "KIMI_PROXY",
        "LLAMACPP_BASE_URL",
        "LLAMACPP_PROXY",
        "LMSTUDIO_PROXY",
        "LM_STUDIO_BASE_URL",
        "LOG_API_ERROR_TRACEBACKS",
        "LOG_MESSAGING_ERROR_DETAILS",
        "LOG_RAW_API_PAYLOADS",
        "LOG_RAW_CLI_DIAGNOSTICS",
        "LOG_RAW_MESSAGING_CONTENT",
        "LOG_RAW_SSE_EVENTS",
        "MESSAGING_PLATFORM",
        "MESSAGING_RATE_LIMIT",
        "MESSAGING_RATE_WINDOW",
        "MODEL",
        "MODEL_HAIKU",
        "MODEL_OPUS",
        "MODEL_SONNET",
        "NVIDIA_NIM_API_KEY",
        "NVIDIA_NIM_PROXY",
        "OLLAMA_BASE_URL",
        "OPENCODE_API_KEY",
        "OPENCODE_PROXY",
        "OPENROUTER_API_KEY",
        "OPENROUTER_PROXY",
        "PROVIDER_MAX_CONCURRENCY",
        "PROVIDER_RATE_LIMIT",
        "PROVIDER_RATE_WINDOW",
        "TELEGRAM_BOT_TOKEN",
        "VOICE_NOTE_ENABLED",
        "WAFER_API_KEY",
        "WAFER_PROXY",
        "WEB_FETCH_ALLOWED_SCHEMES",
        "WEB_FETCH_ALLOW_PRIVATE_NETWORKS",
        "WHISPER_DEVICE",
        "WHISPER_MODEL",
        "ZAI_API_KEY",
        "ZAI_PROXY",
    }
)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple dotenv file without interpolation or shell expansion."""
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        values[key] = value

    return values


def build_managed_env(
    legacy_values: dict[str, str],
    existing_values: dict[str, str],
    overwrite: bool,
) -> dict[str, str]:
    values = dict(existing_values)

    for key, value in legacy_values.items():
        if key not in ALLOWED_KEYS:
            continue
        if overwrite or key not in values:
            values[key] = value

    host = values.get("HOST", "")
    if overwrite or host in {"", "0.0.0.0"}:
        values["HOST"] = STAGED_HOST

    port = values.get("PORT", "")
    if overwrite or port in {"", "8082"}:
        values["PORT"] = STAGED_PORT

    return values


def render_env(values: dict[str, str]) -> str:
    lines = []
    for key in sorted(values):
        value = values[key].replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{value}"')
    return "\n".join(lines) + "\n"


def migrate(
    legacy_env: Path = DEFAULT_LEGACY_ENV,
    managed_env: Path = DEFAULT_MANAGED_ENV,
    overwrite: bool = False,
) -> Path:
    legacy_values = parse_env_file(legacy_env)
    existing_values = parse_env_file(managed_env)
    values = build_managed_env(legacy_values, existing_values, overwrite)

    managed_env.parent.mkdir(parents=True, exist_ok=True)
    previous_umask = os.umask(0o077)
    try:
        managed_env.write_text(render_env(values))
        managed_env.chmod(0o600)
    finally:
        os.umask(previous_umask)

    return managed_env


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate legacy free-claude-code env into managed .fcc config."
    )
    parser.add_argument("--legacy-env", type=Path, default=DEFAULT_LEGACY_ENV)
    parser.add_argument("--managed-env", type=Path, default=DEFAULT_MANAGED_ENV)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    path = migrate(args.legacy_env, args.managed_env, args.overwrite)
    print(path)
    print("Secret values were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
