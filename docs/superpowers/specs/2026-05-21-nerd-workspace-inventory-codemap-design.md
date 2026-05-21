# NERD Workspace Inventory & Codemap Design

## Context

`[NERD-CLAUDE]-free` now has a safe staged ClaudeCore installation at `/root/nerd-claude-free-staging`, while the legacy deployment remains at `/root/free-claude-code`. The staged proxy runs on `127.0.0.1:18082`; the legacy proxy runs on `127.0.0.1:8082`.

The broader `/root` workspace is not clean or centralized. It includes Claude/Codex/Hermes skill stores, GitNexus indexes, Hermes runtime state, `nerd-method`, Obsidian data, nested repositories, archives, generated reports, logs, and multiple partially installed GitInspired-related assets. Some requested capabilities already exist as skills or folders, but they are spread across `.agents`, `.claude`, `.hermes`, archived directories, and project-local folders.

The next step is not to install or wire every GitInspired repository. The next step is to create a reliable inventory and codemap so later implementation can be planned from facts.

## Goals

1. Create a source-of-truth inventory for the current server workspace.
2. Map the staged ClaudeCore codebase and the local NERD additions.
3. Classify installed skills, repositories, services, configs, and GitInspired candidates.
4. Identify duplicate, stale, risky, already-installed, and missing components.
5. Produce documentation that can be converted into implementation prompts and plans.
6. Keep the legacy proxy and staged proxy untouched except for read-only status checks.

## Non-Goals

- Do not move, delete, rename, archive, or install external projects.
- Do not promote staged ClaudeCore to port `8082`.
- Do not commit secrets or print secret values.
- Do not modify existing Claude/Codex/Hermes global skill stores.
- Do not make UI changes in this phase.
- Do not implement WordPress, Shopify, n8n, MCP, data, betting, darkweb, or Moneygen workflows yet.

## Recommended Approach

Use an inventory-first manifest layer inside `/root/nerd-claude-free-staging`. The scanner reads the local filesystem and git metadata, writes deterministic JSON/Markdown reports, and makes no behavioral changes. Later phases will consume the manifest to decide what to install, normalize, expose in UI, or skip.

This approach is slower than direct integration, but it prevents duplicate installs and avoids mixing unrelated systems into ClaudeCore before their boundaries are understood.

## Architecture

The inventory layer lives under `scripts/nerd/inventory/` and outputs to `docs/nerd_inventory/`.

It has four parts:

1. **Workspace scanner**
   - Reads top-level `/root` directories.
   - Detects git repositories, nested repositories, large directories, logs, archives, and runtime state directories.
   - Records path, type, size, git branch, dirty state, remotes, and latest commit when available.

2. **Skills scanner**
   - Reads `SKILL.md` files from known stores:
     - `/root/.agents/plugins/skills`
     - `/root/.agents/skills`
     - `/root/.claude/skills`
     - `/root/.claude/skills/skills`
     - `/root/.codex/skills`
     - `/root/.hermes/skills`
   - Extracts frontmatter fields where present: `name`, `description`, `risk`, `source`, `date_added`, `category`.
   - Groups skills by domains relevant to the user request: WordPress, Shopify, n8n, GitHub, design, security, data, Obsidian, Telegram, scraping/crawling, Chrome extensions, MCP, agents, finance/trading.

3. **GitInspired catalog**
   - Defines the provided GitInspired repository list as input data.
   - Marks each item as one of:
     - `present_repo`: local git repository exists.
     - `present_skill`: matching skill exists.
     - `present_docs`: matching docs/reports exist.
     - `missing`: no strong local evidence.
     - `investigate`: ambiguous or partial evidence.
     - `skip_candidate`: likely not useful or too risky for direct integration.
   - Records rationale and recommended next action.

4. **ClaudeCore codemap**
   - Maps staged ClaudeCore directories:
     - `api`: FastAPI routes, admin UI, request handling, runtime lifecycle.
     - `cli`: `fcc-server`, `fcc-claude`, process/session handling.
     - `config`: settings and provider config.
     - `providers`: Kimi, NVIDIA NIM, Wafer, OpenRouter, DeepSeek, Fireworks, Z.ai, OpenCode, local providers.
     - `messaging`: Discord/Telegram command and session layer.
     - `core`: Anthropic request/stream conversion and shared primitives.
     - `scripts/nerd`: NERD wrappers and migration utilities.
     - `docs`: NERD runbooks and future inventory reports.
   - Adds upstream status: staged branch ahead/behind `upstream/main`, legacy ahead/behind `origin/main`, and patch stack summary.

## Outputs

The phase should produce these generated or maintained files:

- `docs/nerd_inventory/workspace-map.json`
  - Machine-readable workspace inventory.
- `docs/nerd_inventory/workspace-map.md`
  - Human-readable map of `/root`, grouped by ownership and risk.
- `docs/nerd_inventory/skills-inventory.json`
  - Machine-readable skills inventory.
- `docs/nerd_inventory/skills-inventory.md`
  - Domain-grouped skills inventory.
- `docs/nerd_inventory/gitinspired-catalog.json`
  - Machine-readable status for the GitInspired list.
- `docs/nerd_inventory/gitinspired-catalog.md`
  - Human-readable install/present/skip/investigate table.
- `docs/nerd_inventory/claudecore-codemap.md`
  - ClaudeCore component map and NERD extension points.
- `docs/nerd_inventory/next-phase-backlog.md`
  - Prioritized backlog for later specs and implementation plans.

The scanner code should be small, deterministic, and testable. It should not require network access for the first version.

## Data Model

Each inventory item should include:

- `id`: stable slug.
- `name`: display name.
- `kind`: `repo`, `dir`, `skill`, `service`, `config`, `doc`, `archive`, or `candidate`.
- `path`: absolute local path when local.
- `source_url`: external URL when relevant.
- `status`: `active`, `staged`, `legacy`, `present`, `missing`, `investigate`, `skip_candidate`, or `archived`.
- `domain`: high-level capability domain.
- `risk`: `low`, `medium`, `high`, or `unknown`.
- `evidence`: short factual notes with paths.
- `recommended_action`: `keep`, `index`, `normalize`, `install_later`, `review_later`, `skip`, or `archive_later`.

## Safety Rules

- Never print values from `.env`, `.json` auth files, shell history, or credential stores.
- Secret detection should report only file paths and key names/pattern categories, not values.
- Read-only scan defaults should exclude:
  - `.venv`
  - `node_modules`
  - `.git`
  - cache directories
  - large logs
  - SQLite databases
  - JSONL session histories
- Any future cleanup must be a separate plan with explicit approval.

## Error Handling

The scanner should continue when one path is unreadable, missing, too large, or not a git repo. It should record a warning in the output item instead of failing the whole run. A hard failure is appropriate only when the output directory cannot be created or a report cannot be written.

## Testing

Unit tests should use temporary directories with fake git repos, fake `SKILL.md` files, and fake GitInspired entries. They should verify:

- repo metadata extraction;
- skill frontmatter extraction;
- domain classification;
- GitInspired status classification;
- secret-safe behavior;
- deterministic JSON ordering;
- Markdown report generation.

Runtime verification should also check:

- staged proxy remains healthy on `18082`;
- legacy proxy remains healthy on `8082`;
- generated docs contain no pasted API keys.

## External Candidate Notes

The first inventory should include, but not install, WordPress and Shopify candidates discovered during research:

- `docdyhr/mcp-wordpress`: comprehensive WordPress MCP server.
- `cvrt-jh/wordpress-mcp`: token-optimized WordPress MCP server.
- `wordpress/agent-skills`: WordPress-maintained agent skills.
- Composio/Rube Shopify automation skill.

These are candidates for later dedicated specs. They should not be installed during this inventory phase.

## Acceptance Criteria

- The inventory phase runs from `/root/nerd-claude-free-staging`.
- It creates the JSON and Markdown reports listed above.
- It does not change legacy `/root/free-claude-code` application files.
- It does not modify global skill stores.
- It does not start, stop, or reconfigure services.
- `uv run ruff check`, `uv run ty check`, and `uv run pytest` pass.
- `free-claude status` still reports staged and legacy health.
- The staged git branch is clean after commits.

## Future Phases

Likely follow-up specs after this inventory:

1. GitInspired skill normalization and activation manifest.
2. WordPress/CMS workbench layer.
3. Shopify commerce layer.
4. n8n/MCP connector library.
5. Mac companion install and sync.
6. Unified task routing between server and Mac.
7. Data ingestion and automatic triage pipeline.
8. Commercialization and product-template library.
