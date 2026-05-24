# NERD OS UI/UX Direction

NERD OS is the interaction layer above NERD Agency Mission Control. The goal is not another chat UI; it is an operator console for one shared AI agency.

## Product Shape

The interface should feel like a dense mission OS:

- one command center for health, active runs, and next actions;
- one agent surface for role packs, Ruflo, Claude/Codex/Gemini/Kimi entrypoints, and assignments;
- one automation surface for n8n workflows and allowlisted full-auto actions;
- one memory surface for Open WebUI knowledge, Obsidian, NotebookLM, prompts, source cache, and reports;
- one build surface for GitHub, GitNexus, CodeGraph, CMS, Shopify, WordPress, and site generation;
- one observability surface for Langfuse, Grafana, Uptime Kuma, logs, and traces;
- one lab surface for risky/experimental modules that are visible but disabled by default.

## UX Rules

- The manifest is the source of truth. If a tool is not in the manifest/actions registry, it should not appear as runnable.
- Every module card must show risk, `auto_mode`, owner, last run, and status.
- Low-risk actions can run directly. Medium-risk actions need clear context. High-risk actions stay blocked unless the policy changes.
- The UI should optimize for scanning and repeated operation, not marketing. Use compact tables, status rows, split panes, logs, and command drawers.
- Chat remains useful, but the main shell should expose runnable modules, memory, traces, and tasks without forcing the user to remember commands.

## Visual System

- Dark operational shell, not decorative hero UI.
- High contrast status colors: green for healthy, amber for attention, red for blocked/failing, blue for running.
- Left rail: Command Center, Agents, Automations, Memory, Build, Observability, Lab, Settings.
- Main area: selected surface with grouped module cards and run history.
- Right drawer: selected module details, docs, last output, policy, and related knowledge.
- Blueprint view: visual OS map that shows entry points, shared brain, tool mesh, automation fabric, and observability in one screen.

## Current Implementation Anchor

The first executable kernel is `nerd-os`:

- `nerd-os list` exposes the module/action registry.
- `nerd-os run <action_id>` runs only allowlisted actions.
- `nerd-os serve` exposes an internal Docker-network API at `172.20.0.1:38181`.
- `https://agency.umanoff-analytics.space/nerd-os/` exposes the first protected dashboard.
- `https://agency.umanoff-analytics.space/nerd-os/blueprint` exposes the protected visual blueprint.
- `/api/runs` exposes recent run history without storing stdout/stderr in the summary log.

Open WebUI and n8n should call this runner instead of directly shelling out to random tools.
