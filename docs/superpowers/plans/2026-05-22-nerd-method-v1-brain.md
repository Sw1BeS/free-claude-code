# NERD-METHOD V1 Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first concrete NERD-METHOD shared brain layer so Mission Control, Open WebUI, n8n, GitNexus, Obsidian, NotebookLM, and future Mac agents share one current operating map.

**Architecture:** Keep `/root/nerd-claude-free-staging` as the versioned implementation source and `/root/nerd-agency-stack` as the live runtime target. Add deterministic inventory/report generation for the brain layer, then seed those reports into Open WebUI knowledge and runtime manifests. Treat new GitHub tools as catalogued candidates unless the task explicitly installs them.

**Tech Stack:** Python inventory scripts, pytest, Markdown/JSON reports, Open WebUI seed utility, existing `nerd-agency-stack` manifest and scripts.

---

### Task 1: Extend GitInspired Catalog With New Repos

**Files:**
- Modify: `scripts/nerd/inventory/gitinspired.py`
- Modify: `tests/nerd/test_inventory_gitinspired.py`
- Regenerate: `docs/nerd_inventory/gitinspired-catalog.json`
- Regenerate: `docs/nerd_inventory/gitinspired-catalog.md`

- [ ] Add these repositories to `GITINSPIRED_REPOS` with domains, aliases, and concise integration notes:
  - `CloakBrowser`, `https://github.com/CloakHQ/CloakBrowser`, domain `browser-automation`, aliases `cloakbrowser`, `cloak-browser`, `cloak`.
  - `ruflo`, `https://github.com/ruvnet/ruflo`, domain `agents`, aliases `ruflo`, `ruvflo`, `claude-flow`.
  - `codegraph`, `https://github.com/colbymchenry/codegraph`, domain `code-graph`, aliases `codegraph`, `code-graph`.
  - `cc-switch`, `https://github.com/farion1231/cc-switch`, domain `desktop-control`, aliases `cc-switch`, `ccswitch`.
  - `notebooklm-py`, `https://github.com/teng-lin/notebooklm-py`, domain `google`, aliases `notebooklm-py`, `notebooklm`, `notebook-lm`.
- [ ] Preserve the existing `agency-agents` entry and add notes that it is an agent-role pack, not a runtime service.
- [ ] Add tests that assert all new URLs are present and that `ruflo`, `codegraph`, and `notebooklm-py` classify as missing when no evidence exists.
- [ ] Run `uv run pytest tests/nerd/test_inventory_gitinspired.py`.
- [ ] Regenerate inventory with `uv run python scripts/nerd/generate_inventory.py`.

### Task 2: Add Unified Brain Inventory Report

**Files:**
- Create: `scripts/nerd/inventory/brain.py`
- Create: `tests/nerd/test_inventory_brain.py`
- Modify: `scripts/nerd/generate_inventory.py`
- Regenerate: `docs/nerd_inventory/nerd-method-brain.json`
- Regenerate: `docs/nerd_inventory/nerd-method-brain.md`
- Modify: `docs/nerd_inventory/next-phase-backlog.md`

- [ ] Implement `build_brain_report(workspace_root: Path, agency_stack_dir: Path, staging_dir: Path, nerd_method_dir: Path, obsidian_vault_dir: Path) -> InventoryReport`.
- [ ] Include canonical source items:
  - `brain-canonical-repo`: `/root/nerd-claude-free-staging`, domain `brain-source`, risk `medium`, action `keep`.
  - `brain-runtime-stack`: `/root/nerd-agency-stack`, domain `brain-runtime`, risk `medium`, action `keep`.
  - `brain-nerd-method`: `/root/nerd-method`, domain `brain-knowledge`, risk `medium`, action `normalize`.
  - `brain-openwebui-knowledge`: `https://agency.umanoff-analytics.space`, domain `brain-surface`, risk `medium`, action `normalize`.
  - `brain-obsidian-vault`: `/root/obsidian-vault`, domain `brain-surface`, risk `low`, action `normalize`.
  - `brain-gitnexus`: `http://127.0.0.1:4173`, domain `brain-codegraph`, risk `low`, action `keep`.
  - `brain-n8n`: `http://127.0.0.1:5678`, domain `brain-automation`, risk `medium`, action `keep`.
  - `brain-langfuse`: `http://127.0.0.1:3300`, domain `brain-observability`, risk `low`, action `keep`.
- [ ] Include sync target items:
  - `brain-sync-openwebui-seed`: `scripts/nerd/agency/openwebui_seed.py`, domain `brain-sync`.
  - `brain-sync-inventory`: `scripts/nerd/generate_inventory.py`, domain `brain-sync`.
  - `brain-sync-stack-seed`: `/root/nerd-agency-stack/scripts/seed-openwebui.sh`, domain `brain-sync`.
- [ ] Status should be `present` when local path exists, `active` for internal loopback services, and `investigate` when missing.
- [ ] Add warnings when `/root/obsidian-vault` has fewer than two Markdown notes or when `/root/nerd-method` is not a git repository.
- [ ] Add tests using temp directories and fake files to verify item IDs, statuses, warnings, and no secrets in notes.
- [ ] Wire the report into `generate_inventory.py` and write it as `nerd-method-brain`.
- [ ] Update backlog priority 1 to make unified brain sync the next hardening phase.
- [ ] Run `uv run pytest tests/nerd/test_inventory_brain.py tests/nerd/test_generate_inventory.py`.

### Task 3: Seed Brain Report Into Open WebUI Knowledge

**Files:**
- Modify: `scripts/nerd/agency/openwebui_seed.py`
- Modify: `tests/nerd/test_agency_openwebui_seed.py`
- Regenerate: `docs/nerd_inventory/nerd-method-brain.json`
- Regenerate: `docs/nerd_inventory/nerd-method-brain.md`

- [ ] Add `docs/nerd_inventory/nerd-method-brain.md` and `docs/nerd_inventory/workspace-map.md` to `mission_control_knowledge_documents`.
- [ ] Update `mission_control_knowledge_base().description` to name NERD-METHOD shared brain, GitNexus, Obsidian, NotebookLM, and n8n.
- [ ] Update `knowledge_vault` prompt and `[NERD-AGENCY memory:knowledge]` memory so they explicitly say the canonical source is versioned NERD reports plus runtime sync targets, not scattered chat memory.
- [ ] Add tests asserting `nerd-method-brain.md` is collected when present and the new canonical-source wording appears in prompt/memory.
- [ ] Run `uv run pytest tests/nerd/test_agency_openwebui_seed.py`.

### Task 4: Update Runtime Manifest and Seed Live Stack

**Files:**
- Modify live runtime: `/root/nerd-agency-stack/nerd-agency.manifest.yaml`
- Modify live runtime: `/root/nerd-agency-stack/README.md`
- Run live script: `/root/nerd-agency-stack/scripts/seed-openwebui.sh`

- [ ] Add a `brain` or `unified_memory` section to the runtime manifest with canonical source, sync targets, surfaces, and safety policy.
- [ ] Add new candidate tool entries for `ruflo`, `codegraph`, `cc-switch`, `CloakBrowser`, `notebooklm-py`, and `agency-agents`.
- [ ] Keep high-risk browser/social/security automation disabled by default; mark CloakBrowser as `auto_mode: disabled`.
- [ ] Update README with the current login URL and operational model, but do not print secrets or passwords.
- [ ] Run `/root/nerd-agency-stack/scripts/seed-openwebui.sh --dry-run`.
- [ ] If dry-run is clean, run `/root/nerd-agency-stack/scripts/seed-openwebui.sh`.

### Task 5: Verification and Commit

**Files:**
- All modified versioned files under `/root/nerd-claude-free-staging`
- Runtime files under `/root/nerd-agency-stack`

- [ ] Run `uv run ruff format scripts/nerd tests/nerd`.
- [ ] Run `uv run ruff check scripts/nerd tests/nerd`.
- [ ] Run `uv run ty check`.
- [ ] Run `uv run pytest tests/nerd`.
- [ ] Run `uv run python scripts/nerd/generate_inventory.py`.
- [ ] Run `/root/nerd-agency-stack/scripts/status.sh`.
- [ ] Run `/root/nerd-agency-stack/scripts/seed-openwebui.sh --dry-run`.
- [ ] Secret-scan generated docs and runtime manifest for raw provider keys.
- [ ] Commit versioned repo changes with `git commit -m "feat: add nerd method brain inventory"`.
