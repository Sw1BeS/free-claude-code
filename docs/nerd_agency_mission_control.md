# NERD Agency Mission Control

`NERD Agency Mission Control` is the server-first public-login shell for `[NERD-CLAUDE]-free`.

The implementation is intentionally separate from both existing ClaudeCore checkouts:

- legacy runtime: `/root/free-claude-code`
- staged safe upgrade: `/root/nerd-claude-free-staging`
- agency shell: `/root/nerd-agency-stack`

## Architecture

Open WebUI is one workspace inside the public Mission Control domain. nginx is the only intended public edge for `agency.umanoff-analytics.space`; user-facing links should use the public domains, not backend loopback addresses.

The Open WebUI container joins the existing `hermes-evolution-internal` Docker network so it can call:

- LiteLLM as `http://litellm:4000/v1`
- Ollama as `http://ollama:11434`
- n8n as `http://n8n:5678`
- Langfuse as `http://langfuse-web:3000`

The existing `[NERD-CLAUDE]-free` Admin UI remains a private backend/admin surface and should be surfaced through NERD OS status panels rather than direct public links.

## V1 Product Scope

V1 is Ops + CMS + Automation:

- core status/update/inventory/backup checks
- GitHub and GitNexus-oriented repo triage
- WordPress, WooCommerce, Shopify, SEO, and analytics planning
- n8n workflow search/run templates
- Obsidian, NotebookLM, reports, and prompt-library knowledge surfaces
- Langfuse, Grafana, and Uptime Kuma observability links

Deferred domains stay out of full-auto V1:

- offensive/dark security lab
- betting
- moneygen execution
- personality-clone agents
- social scraping at scale

## Safety Boundaries

Global automation is controlled by `NERD_AGENCY_AUTOMATION_ENABLED`. The manifest adds per-tool `auto_mode`, and n8n workflows must remain inactive/disabled unless they are V1 allowlisted.

The public UI should use Open WebUI auth with signup disabled. Backend services must remain loopback-only or private-network-only.

## Public DNS And HTTPS

Cloudflare DNS is managed from `/root/nerd-agency-stack/scripts/cloudflare-dns-sync.sh`.

Live public hostnames:

- `https://agency.umanoff-analytics.space`
- `https://agency.umanoff-analytics.space/nerd-os/`
- `https://agency.umanoff-analytics.space/nerd-os/blueprint`
- `https://agency.umanoff-analytics.space/nerd-os/office`
- `https://agents.umanoff-analytics.space`
- `https://automations.umanoff-analytics.space`
- `https://memory.umanoff-analytics.space`
- `https://obs.umanoff-analytics.space`
- `https://cms.umanoff-analytics.space`

All hostnames route to the same Open WebUI Mission Control shell. Raw backends remain private.
