# ClaudeCore Codemap

Generated: `2026-05-22T06:16:33Z`

| ID | Name | Kind | Status | Domain | Risk | Action |
| --- | --- | --- | --- | --- | --- | --- |
| `codemap-api` | api | dir | present | api | low | keep |
|  | path=/root/nerd-claude-free-staging/api; notes=FastAPI routes, admin UI, request handling, runtime lifecycle.; evidence=/root/nerd-claude-free-staging/api |  |  |  |  |  |
| `codemap-cli` | cli | dir | present | cli | low | keep |
|  | path=/root/nerd-claude-free-staging/cli; notes=fcc-server, fcc-claude, process/session handling.; evidence=/root/nerd-claude-free-staging/cli |  |  |  |  |  |
| `codemap-config` | config | dir | present | config | low | keep |
|  | path=/root/nerd-claude-free-staging/config; notes=Settings, provider config, constants, logging.; evidence=/root/nerd-claude-free-staging/config |  |  |  |  |  |
| `codemap-core` | core | dir | present | core | low | keep |
|  | path=/root/nerd-claude-free-staging/core; notes=Anthropic request/stream conversion and shared primitives.; evidence=/root/nerd-claude-free-staging/core |  |  |  |  |  |
| `codemap-docs` | docs | dir | present | docs | low | keep |
|  | path=/root/nerd-claude-free-staging/docs; notes=Runbooks, specs, plans, generated inventory reports.; evidence=/root/nerd-claude-free-staging/docs |  |  |  |  |  |
| `codemap-messaging` | messaging | dir | present | messaging | low | keep |
|  | path=/root/nerd-claude-free-staging/messaging; notes=Discord/Telegram command and session layer.; evidence=/root/nerd-claude-free-staging/messaging |  |  |  |  |  |
| `codemap-providers` | providers | dir | present | providers | low | keep |
|  | path=/root/nerd-claude-free-staging/providers; notes=Kimi, NVIDIA NIM, Wafer, OpenRouter, DeepSeek, Fireworks, Z.ai, OpenCode, local providers.; evidence=/root/nerd-claude-free-staging/providers |  |  |  |  |  |
| `codemap-scripts-nerd` | scripts/nerd | dir | present | nerd | low | keep |
|  | path=/root/nerd-claude-free-staging/scripts/nerd; notes=NERD wrappers, migration utilities, inventory tooling.; evidence=/root/nerd-claude-free-staging/scripts/nerd |  |  |  |  |  |
| `codemap-upstream-status` | ClaudeCore upstream status | repo | staged | upstream | medium | review_later |
|  | path=/root/nerd-claude-free-staging; notes=staged_ahead=30; staged_behind=5; legacy_ahead=2; legacy_behind=94; evidence=/root/nerd-claude-free-staging, /root/free-claude-code |  |  |  |  |  |
