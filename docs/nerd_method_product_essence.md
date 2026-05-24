# NERD-METHOD Product Essence

Generated: 2026-05-24

## One Sentence

NERD-METHOD is a personal AI agency operating system: one protected command center where human intent, shared memory, agent teams, automations, code intelligence, commerce/CMS delivery, research, observability, and client/project operations become one managed system instead of scattered tools.

## What The Product Is

The product is not just `[NERD-CLAUDE]-free`, Open WebUI, n8n, GitNexus, Ruflo, or a list of skills. Those are components.

The product is the orchestration layer above them:

1. A visible operating shell for you.
2. A shared memory layer every AI entrypoint can read from and write back to.
3. A tool registry with risk policy, owners, endpoints, docs, and auto-mode.
4. A virtual AI agency with departments, roles, assignments, and activity lanes.
5. A delivery factory for client work, GitHub work, CMS/commerce builds, data analysis, content products, and automation.
6. A safety boundary that keeps destructive, financial, social, offensive-security, and identity/personality actions gated until intentionally enabled.

## Product Metaphor

The closest mental model is not "chatbot" and not "dashboard". It is a private AI agency OS:

- `Mission Control`: health, tasks, runs, status, risk, and next actions.
- `Virtual Office`: agents grouped by departments, visible work lanes, handoffs, and live activity.
- `Shared Brain`: inventory, prompts, project/client memory, Obsidian notes, NotebookLM research, GitNexus/CodeGraph code context, Langfuse traces, and generated reports.
- `Tool Mesh`: MCP/OpenAPI/workflow links to internal and external services.
- `Automation Fabric`: n8n, allowlisted runner actions, scheduled checks, update workflows, backup workflows, and kill switches.
- `Delivery Factory`: reusable production pipelines for sites, apps, CMS migrations, Shopify, WordPress, analytics, GitHub publishing, and digital products.

## Current Foundation

Already active:

- Primary public shell: Open WebUI at `agency.umanoff-analytics.space`.
- NERD OS dashboard: `/nerd-os/`.
- Visual architecture map: `/nerd-os/blueprint`.
- Virtual office concept page: `/nerd-os/office`.
- Automation engine: n8n.
- Observability: Langfuse, Grafana, Loki, Prometheus, Uptime Kuma.
- Provider layer: LiteLLM, Ollama, OpenRouter/DeepSeek/NVIDIA/Kimi/Wafer-ready configuration, plus `[NERD-CLAUDE]-free`.
- Code intelligence: GitNexus and CodeGraph.
- Source cache and tool inventory: GitInspired catalog under `/root/nerd-method/tools/git-inspired`.
- Knowledge seeding: Open WebUI knowledge receives the manifest, reports, UI direction, and operating model through deterministic sync.

## Design Principles

1. The manifest is the source of truth.
   If a tool, skill, workflow, endpoint, or service is not in the registry, it is not part of the OS.

2. Memory comes before autonomy.
   An autonomous agency without current shared memory will make confident wrong decisions. The first-class product is the brain: system memory, project memory, client memory, prompt memory, trace memory, and source memory.

3. OpenAPI first, MCP where it fits.
   OpenAPI is preferred for internal execution because it gives normal HTTP semantics, audit, quotas, and easier policy gates. MCP is added for tool ecosystems that already speak MCP.

4. Low-risk auto, high-risk visible but gated.
   Health checks, inventory, read-only repo analysis, report generation, and planning can run automatically. Destructive deploys, credentials, money actions, betting, social scraping, offensive security, and personality cloning stay disabled until a policy explicitly allows them.

5. Everything important becomes observable.
   Agent runs, tool calls, failures, costs, traces, workflows, and memory updates must be linkable from the UI.

6. The UI must be operational, not decorative.
   Dense, readable, status-heavy, built for repeated work: module cards, run lanes, logs, trace links, task boards, virtual office rooms, and command drawers.

## How GitInspired Maps Into The Product

### Agent Orchestration

- Ruflo becomes the deeper agency-orchestration candidate: swarms, memory, federation, background workers, and role coordination.
- agency-agents, OpenMythos, OpenJarvis, successor-agent, MiroFish, and ECC become role packs, behavior patterns, and candidate agent runtimes.
- cc-switch becomes a desktop/Mac companion candidate for switching between Claude Code, Codex, OpenCode, OpenClaw, Gemini CLI, and Hermes-style tools.

### Code And GitHub Intelligence

- GitNexus remains the code/process graph for impact analysis, route mapping, API shape checks, and PR/review workflows.
- CodeGraph is the fast local AST knowledge graph for symbol lookup, callers/callees, impact, and low-token code navigation.
- awesome-copilot and spec-kit become the GitHub automation and spec-driven delivery layer: issues, PRs, articles, repositories, project scaffolds, and client deliverables.

### Knowledge And Research

- NotebookLM skill and notebooklm-py become the Google research surface for source imports, artifact generation, reports, study guides, and knowledge distillation.
- Obsidian is the durable human-readable vault.
- Graphify and open-design become visualization/report-generation helpers.

### UI And Product Design

- OpenUI, open-design, awesome-design-systems, and ui-ux-pro-max-skill become design-system, UI generation, and visual QA inputs.
- NERD OS should use these to generate real product interfaces, not landing pages.

### Data, Crawling, And Ingestion

- crawl4ai becomes the preferred read-only web extraction/RAG ingestion tool.
- CloakBrowser is treated as high-risk browser automation and remains disabled by default.
- The automatic dump layer ingests files, exports, saved posts, likes, chats, browser archives, PDFs, CSVs, and site crawls, classifies them, stores them, and routes them into the right pipeline.

### CMS And Commerce

- WordPress MCP Adapter, WordPress/WooCommerce skills, Shopify Storefront MCP, Shopify developer tooling, Theme Check, and CMS migration workflows form a dedicated `cms-commerce` department.
- The output should cover audits, migrations, theme work, plugin/app development, analytics, SEO, merchandising, and client-ready reporting.

### Security And Dark Lab

- Awesome-Hacking and hackingtool are not V1 execution tools.
- They belong to a read-only `security-safe` lab: audit, inventory, hardening, education, and defensive review only until an explicit isolated lab exists.

### Finance, Betting, Moneygen

- TradingAgents, betting companion, and Moneygen are separate risk domains.
- V1 should support research, simulation, and reporting. Live money/betting actions require explicit credentials, limits, jurisdiction checks, and manual approval gates.

## Main Product Departments

1. `Command Center`
   Health, active runs, stack status, updates, backups, queue, incidents, and kill switches.

2. `Virtual Office`
   Visible agent departments: Strategy, Build, Automation, CMS/Commerce, Data, Knowledge, Observability, Growth, Security-Safe, and Client Ops.

3. `Brain`
   Memory graph, prompt library, Obsidian, NotebookLM, Open WebUI knowledge, reports, GitNexus, CodeGraph, Langfuse trace summaries, and source catalogs.

4. `Automation`
   n8n workflows, OpenAPI runner actions, MCP bridges, scheduled jobs, ingestion routes, update checks, and workflow edit/review.

5. `Build Studio`
   GitHub, spec-kit, code review, app/site generation, Chrome extensions, WordPress, Shopify, full-stack prototypes, QA, deployment, and docs.

6. `Data Studio`
   Large export ingestion, normalization, analytics, dashboards, entity extraction, embeddings, RAG, client datasets, and report generation.

7. `Commerce Studio`
   Shopify, WooCommerce, WordPress migrations, themes, apps/plugins, analytics, SEO, product/content strategy, and client delivery packages.

8. `Growth And Products`
   Moneygen, digital products, guides, courses, templates, commercialization, GitHub writing, repo publishing, and simpler-alternative proposals.

9. `Lab`
   Dark/security, betting, personality models, social automation, browser automation, and other high-risk modules. Visible, documented, disabled by default.

10. `Clients And Projects`
   CRM-like workspace for clients, tasks, documents, history, decisions, deliverables, invoices/commerce later, and cross-device access.

## The Shared Brain Contract

Every AI tool must eventually follow the same memory contract:

- Read current system state before acting.
- Attach work to a project/client/task.
- Write outputs as structured artifacts.
- Record source links and provenance.
- Record tool calls and risk level.
- Send run traces to observability where possible.
- Promote useful output into Obsidian/Open WebUI/NotebookLM only through a controlled sync.
- Never let a private chat become the only copy of important knowledge.

## Implementation Sequence

### Phase 1: Stabilize The OS Core

- Keep working trees clean.
- Make the stack reproducible.
- Expand `nerd-agency.manifest.yaml` into the full source-of-truth registry.
- Add UI surfaces for modules, virtual office departments, memory, tasks, and run history.
- Keep all high-risk actions disabled.

### Phase 2: Unified Brain

- Normalize memory schemas: system, clients, projects, prompts, traces, data, skills.
- Add ingestion queues and classification.
- Sync Open WebUI, Obsidian, NotebookLM, GitNexus, CodeGraph, and Langfuse summaries.
- Add dedupe, provenance, retention, and backup.

### Phase 3: Autonomous Agency

- Convert role packs into agent departments.
- Add assignments, status, handoffs, queue, owner, SLA, and run trace links.
- Use Ruflo only after its memory/daemon/sandbox policy is explicit.
- Keep n8n as full-auto workflow execution for allowlisted actions.

### Phase 4: Delivery Factories

- GitHub factory: issue/PR/review/docs/articles/repo publishing.
- CMS factory: WordPress/WooCommerce migrations, builds, plugins, audits.
- Shopify factory: theme/app/analytics/storefront AI workflows.
- Data factory: export ingestion, analytics, reports, RAG datasets.
- Site/app factory: full-site generation across stacks/CMS.
- Product factory: guides, courses, templates, commercialization.

### Phase 5: Cross-Device And Mac Node

- Install a local Mac companion.
- Sync only the brain and task state, not raw secrets.
- Show server and Mac as separate nodes in the same UI.
- Route tasks to the correct node based on capability, credentials, and risk.

## V1 Definition Of Done

NERD-METHOD V1 is good enough when:

- You can log into one public UI and see the OS, virtual office, tools, memory, and current tasks.
- Every listed module has a registry entry with risk, owner, docs, status, and auto-mode.
- Low-risk actions run from UI and n8n with history.
- All generated knowledge is synced into the shared brain.
- GitHub push/deploy workflow is stable.
- CMS/commerce/data/GitHub workflows produce client-usable artifacts.
- Backups and update checks run predictably.
- High-risk modules are visible but blocked.

## External References

- Open WebUI MCP: https://docs.openwebui.com/features/mcp/
- Open WebUI OpenAI-compatible providers: https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/
- n8n MCP server: https://docs.n8n.io/advanced-ai/mcp/accessing-n8n-mcp-server/
- Langfuse docs: https://langfuse.com/docs
- GitHub Spec Kit: https://github.com/github/spec-kit
- Ruflo: https://github.com/ruvnet/ruflo
- CodeGraph: https://github.com/colbymchenry/codegraph
- NotebookLM Python API: https://github.com/teng-lin/notebooklm-py
- WordPress MCP Adapter: https://github.com/WordPress/mcp-adapter
- Shopify Storefront MCP: https://shopify.dev/docs/apps/build/storefront-mcp
- Crawl4AI: https://docs.crawl4ai.com/
