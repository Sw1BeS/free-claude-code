# NERD-METHOD Master Prompt

Generated: 2026-05-24

Use this prompt as the canonical handoff brief for any future agent, coding session, implementation plan, or product architecture pass on NERD-METHOD / NERD OS.

Do not paste secrets into this prompt. API keys, passwords, Cloudflare credentials, provider credentials, and private tokens must stay in private `.env` files, password managers, or server-only credential files.

## Role

You are a senior product engineer, infra engineer, AI systems architect, and pragmatic operator working on `NERD-METHOD`: a personal AI agency operating system for Ruslan Umanoff.

Your job is not to build another chat wrapper. Your job is to turn the existing scattered AI/dev/automation stack into one coherent, navigable, observable, and increasingly autonomous AI agency OS.

## Direct User Quotes

These quotes are the user's own language and should be treated as product intent:

> "Я хочу чтобы у меня была полноценная платформа AI агенство что-ли, с ебанутым визуалом, автоматизациями, и чтобы все можно было отслежживать в рамках одного общего красивого интерфейса."

> "Мне важно чтобы ты просто в процессе обдумывания не придумал создавать его с 0, а использовал лучшие решения и предложил варианты которые будут нормально работать со всем моим стеком а также удовлетворять мои хочухи в полноце мере."

> "Смотри, мне нужен не просто мозг, то о чем мы говорим это основа по сути, потому что в моей голове это общая память к которой в последствии будут обращаться все ии инструменты, и которая должна развиваться и расти ибо иначе это будет безсмысленно."

> "Я тебе говорю, реализуй этот функционал чтобы можно было запускать в текущей системе, и продумай качественную доработку ui-ux всей системы, чтобы все эти модули обьеденять. По сути мы с тобой строим что-то вроде OS типа"

> "Меня не впустило по предоставленным тобой данным, замени пожалуйста их..."

> "Проблему гита ты толком не решил, так что включи и ее в промт."

> "Я не понимаю зачем нам самый базовый webUi ибо он выглядит как обычное окошко чата,к тому же все ресурсы которые мы делаем работают по отдельным урлам, но нет перелинковки или вобщей навигации чтобы удобно было пользоваться, в общем надо продумать в промте что на выходе я хочу получить полноценную ос"

> "Единая среда и связанные автоматизации, для ведения клиентов, проектов и прочего - чтобы все было упорядочено и доступно с любого девайса мне"

## Core Product Definition

NERD-METHOD is a personal AI agency OS.

It must feel like one private operating environment where Ruslan can:

- see system health, tasks, tools, agents, memory, workflows, traces, and client/project context;
- assign work to AI agents and observe their progress;
- run low-risk automations directly;
- keep high-risk capabilities visible but gated;
- manage GitHub, WordPress, Shopify, data, research, content, products, and client delivery from one shell;
- use a shared memory layer that every AI tool can read from and write back to;
- move between server and future Mac node without losing context;
- stop thinking in separate URLs and start thinking in one OS.

The product is not:

- a basic Open WebUI chat page;
- a list of cloned repositories;
- a collection of random MCP servers;
- a set of disconnected dashboards;
- a pile of skills with no activation model;
- an unsafe autonomous agent loop.

The product is:

- one navigable shell;
- one tool registry;
- one shared brain;
- one virtual agency;
- one automation fabric;
- one delivery factory;
- one observability layer;
- one reproducible stack.

## Critical Current Complaint: Open WebUI Is Not Enough

Open WebUI may remain useful as a chat/knowledge/model surface, but it is not the final product shell.

The user explicitly rejects the current state where:

- the visible UI looks like a generic chat window;
- each service lives at a separate URL;
- there is no unified navigation between Open WebUI, NERD OS dashboard, virtual office, n8n, Langfuse, Grafana, GitNexus, free-claude admin, Obsidian/NotebookLM workflows, and future CMS/commerce/data modules;
- the "OS" is not yet experienced as one coherent place.

Target UI requirement:

- Build or integrate a real OS shell / Mission Control shell above Open WebUI.
- It must have persistent global navigation, module routing, service links, task context, agent state, memory surfaces, run history, observability links, and risk controls.
- Open WebUI should be embedded, linked, or treated as one workspace, not the primary identity of the product.
- `/nerd-os/`, `/nerd-os/blueprint`, and `/nerd-os/office` are early prototypes, not the final UX.
- The final shell should make separate services feel like apps inside one OS, not unrelated tabs.

## Critical Current Complaint: Git Is Not Fully Solved

The current local mitigation is not enough as a product-level solution.

Current known state:

- The repo has a writable fork remote at `origin`.
- `upstream` points to the original `Alishahryar1/free-claude-code`.
- `upstream` push was disabled locally to avoid repeated `403`.
- This fixed local pushing for the current branch, but does not solve ownership, canonical repository strategy, GitHub identity, PR workflow, deployment branches, or future multi-repo automation.

Required durable GitHub solution:

1. Define the canonical NERD-METHOD GitHub home.
   Decide whether the canonical repo is:
   - a fork under the user's account;
   - a new repo such as `NERD-METHOD` / `nerd-agency-os`;
   - a private monorepo;
   - or an organization-level repo.

2. Log in with the user's intended GitHub identity through `gh auth login` or a scoped token.
   Do not rely on accidental cached credentials.

3. Establish remote policy:
   - `upstream`: read-only original source repo;
   - `origin`: user-owned writable canonical repo;
   - push to `upstream` must be disabled or protected;
   - branch tracking must always point to `origin`.

4. Add a `scripts/git-guard.sh` or equivalent preflight:
   - show current branch;
   - show fetch/push remotes;
   - refuse push if target is not user-owned;
   - refuse push with dirty tree unless explicitly allowed;
   - warn if secrets are present in diff.

5. Add GitHub automation:
   - issue/PR templates;
   - CI checks for tests, lint, secret scan;
   - release notes;
   - deployment log;
   - automated inventory update PRs;
   - optional GitHub Projects or Issues sync into NERD OS.

6. Add visible GitHub status in NERD OS:
   - current canonical repo;
   - branch;
   - dirty tree count;
   - unpushed commits;
   - last push;
   - PR link;
   - CI status;
   - protected upstream warning.

Definition of done for Git:

- A future agent can run one command and know where to push.
- Pushes do not accidentally target someone else's repo.
- The user can see GitHub health in NERD OS.
- All major generated artifacts are committed or intentionally ignored.
- Multi-repo dirty state is visible and manageable.

## Existing Foundation

Current live services and modules include:

- `[NERD-CLAUDE]-free` from ClaudeCore (`free-claude-code`) as the Claude/proxy backend.
- Open WebUI as current public login and model/knowledge surface.
- n8n as automation engine.
- Langfuse as LLM observability and trace platform.
- Grafana/Loki/Prometheus/Uptime Kuma for ops observability.
- LiteLLM/Ollama/provider layer.
- GitNexus and CodeGraph for code intelligence.
- NERD OS runner for allowlisted actions.
- NERD OS dashboard, blueprint, and virtual office prototypes.
- `/root/nerd-method` as source cache, tools area, and future shared brain workspace.
- `/root/nerd-agency-stack` as runtime stack.
- `/root/nerd-claude-free-staging` as canonical current implementation workspace.

Current public entrypoints:

- `https://agency.umanoff-analytics.space`
- `https://agency.umanoff-analytics.space/nerd-os/`
- `https://agency.umanoff-analytics.space/nerd-os/blueprint`
- `https://agency.umanoff-analytics.space/nerd-os/office`

These should become app routes inside one OS shell, not separate mental destinations.

## Required GitInspired Repositories And Roles

Deduplicate and normalize this list into the product registry. Do not blindly install everything into runtime. Each repo must be classified as `installed`, `source-cache`, `skillpack`, `runtime-candidate`, `research-only`, `high-risk-disabled`, or `deferred`.

### Skills And Prompt Packs

- `travisvn/awesome-claude-skills`
- `ComposioHQ/awesome-claude-skills`
- `VoltAgent/awesome-openclaw-skills`
- `mattpocock/skills`
- `nextlevelbuilder/ui-ux-pro-max-skill`
- `PleasePrompto/notebooklm-skill`
- `github/awesome-copilot`

Use these to build activation packs:

- `daily`
- `cms-commerce`
- `data`
- `github-dev`
- `knowledge`
- `design`
- `security-safe`
- `product-growth`

### Agent And Orchestration Systems

- `ruvnet/ruflo`
- `msitarzewski/agency-agents`
- `kyegomez/OpenMythos`
- `open-jarvis/OpenJarvis`
- `lyc-aon/successor-agent`
- `666ghj/MiroFish`
- `affaan-m/ECC`
- `farion1231/cc-switch`
- `decolua/9router`

Use these as agent role packs, orchestration candidates, routing concepts, desktop/Mac companion candidates, and future autonomous agency infrastructure.

Ruflo is important, but it must not be unleashed as an uncontrolled daemon until memory, sandboxing, observability, and policy gates are explicit.

### Code Intelligence And Developer Infrastructure

- `abhigyanpatwari/GitNexus`
- `colbymchenry/codegraph`
- `github/spec-kit`

Use these for:

- code map;
- impact analysis;
- route/API shape checks;
- spec-driven development;
- PR automation;
- generated docs;
- repo/article/project publishing.

### UI, Design, And Product Generation

- `thesysdev/openui`
- `nexu-io/open-design`
- `alexpate/awesome-design-systems`
- `safishamsi/graphify`

Use these to build the real OS interface, product dashboards, visual reports, design systems, client deliverables, and UI generation flows.

### Data, Crawling, Browser, And Knowledge

- `unclecode/crawl4ai`
- `CloakHQ/CloakBrowser`
- `teng-lin/notebooklm-py`
- `PleasePrompto/notebooklm-skill`

Use Crawl4AI and NotebookLM tooling early.

CloakBrowser is high risk and must be disabled by default until a browser automation policy exists.

### CMS, Commerce, Finance, And Domain Modules

- WordPress MCP Adapter and WordPress-related MCP/skills to be researched and integrated.
- Shopify Storefront MCP, Shopify Dev MCP/tooling, Theme Check, Shopify app/theme workflows.
- `TauricResearch/TradingAgents`
- `Zie619/n8n-workflows`
- `langgenius/dify`
- `Z4nzu/hackingtool`
- `Hack-with-Github/Awesome-Hacking`

Finance, betting, money, social automation, and offensive security must stay research/simulation/read-only until explicitly approved.

## User Wish List To Convert Into Product Modules

Implement as departments, workflows, or disabled lab modules:

1. System-wide updates.
2. Personal GitHub automations and best practices.
3. Analysis of huge data exports: social exports, AI chats, saved items, archives, browser data, documents.
4. Google tools and Google Labs: NotebookLM, Jules, Gemma, Opal, Stitch.
5. Large Shopify layer: themes, analytics, apps, plugins, strategy.
6. Large data analytics layer.
7. Full website generation across stacks and CMSs.
8. Setapp/Mac companion integration.
9. Dark AI / darkweb AI lab as isolated high-risk research environment.
10. Moneygen.
11. Personality analyzer and agent generation from large personal datasets.
12. Betting companion.
13. WordPress CMS migrations and builds.
14. Automatic dump inbox: user drops anything, system classifies and routes it.
15. Commercialization of client solutions, templates, guides, courses, products.
16. Prompt library, memory, skills.
17. Obsidian integration.
18. Backup and portability: easy redeploy to new machine/server.
19. MCP server library and database connectors.
20. GitHub publishing: articles, repos, project docs, PRs, issues.
21. Saved/liked content automation with incremental scan logic.
22. Digital product creator and commercialization strategist.
23. Chrome extension development.
24. Telegram star farming only as a gated/high-risk business experiment.
25. "Simpler alternative proposer" for overcomplex ideas.
26. Unified client/project operating environment available from any device.

## Required OS-Level UX

The target UX must include:

- global left navigation;
- top command bar;
- service/app launcher;
- user/project/client selector;
- task queue;
- agent roster;
- virtual office view;
- memory graph view;
- module registry;
- run console;
- recent runs;
- logs/traces;
- risk and auto-mode indicators;
- kill switches;
- unified search;
- notifications;
- deep links to internal services;
- iframe/proxy/app-shell integration where safe;
- consistent auth and navigation across all surfaces.

Navigation must include at minimum:

- Command Center
- Virtual Office
- Agents
- Tasks
- Automations
- Memory
- Knowledge
- GitHub
- Build Studio
- CMS/Commerce
- Data Studio
- Product/Growth
- Observability
- Lab
- Settings

Every route should know:

- what service it belongs to;
- what credentials or auth are required;
- whether it is internal, public, or loopback-only;
- whether it can execute actions;
- whether it is low, medium, or high risk;
- where logs/traces appear.

## Shared Brain Requirements

The shared brain is the foundation.

It must include:

- system inventory;
- service registry;
- GitInspired catalog;
- skills inventory;
- prompt library;
- Open WebUI knowledge;
- Obsidian vault;
- NotebookLM notebooks/artifacts;
- GitNexus process/code graph notes;
- CodeGraph indexes;
- Langfuse trace summaries;
- n8n execution history;
- client memory;
- project memory;
- task history;
- data ingestion catalog;
- source provenance;
- backups.

Every AI tool must follow this contract:

1. Read current memory before acting.
2. Attach work to a project/client/task.
3. Write structured artifacts.
4. Record source links and provenance.
5. Record tool calls and risk level.
6. Send traces/log links where available.
7. Promote useful output through controlled sync.
8. Never let a private chat become the only copy of important knowledge.

## Automation And Risk Policy

Allowed by default:

- status checks;
- read-only inventory;
- read-only repo analysis;
- report generation;
- backup checks;
- update checks;
- low-risk knowledge sync;
- draft-only GitHub issue/PR/report generation.

Require manual confirmation:

- deployment;
- package upgrades;
- database writes;
- CMS writes;
- Shopify writes;
- GitHub pushes to protected branches;
- n8n workflow activation changes;
- credential changes.

Disabled until explicit policy:

- offensive security;
- darkweb actions;
- betting;
- real-money actions;
- social scraping at scale;
- account farming;
- personality clone training from private data;
- stealth browser automation;
- destructive file operations.

## Desired Implementation Strategy

Do not start from zero if a strong existing component fits.

Use:

- Open WebUI for chat/model/knowledge where useful.
- n8n for durable workflow automation.
- Langfuse for LLM observability and traces.
- GitNexus and CodeGraph for code intelligence.
- Ruflo as future agent orchestration after safety design.
- NotebookLM tooling for research artifacts.
- Crawl4AI for data ingestion and RAG-ready web extraction.
- OpenUI/open-design/design-system sources for interface generation.
- Spec Kit for structured software delivery.

But build the NERD OS shell as the user-facing product identity.

## First Real Milestones

### Milestone A: Clean OS Shell

- Create a proper NERD OS shell with unified navigation.
- Link/embed all current routes.
- Make Open WebUI one app inside the shell, not the shell itself.
- Show service health and auth state.
- Show Git status and GitHub canonical repo state.

### Milestone B: Registry And Memory

- Expand manifest into a full registry.
- Add all GitInspired repos as normalized records.
- Add memory schemas.
- Add source/provenance fields.
- Add sync status.

### Milestone C: Virtual Agency

- Convert role packs into visible departments.
- Show agent cards, queues, current assignments, handoffs, and traces.
- Add "agent activity lanes" connected to actual runs where possible.

### Milestone D: GitHub Hardening

- Resolve canonical repo ownership.
- Add GitHub auth through user-owned account/token.
- Add git guard script.
- Add CI/secret scan.
- Show GitHub panel in NERD OS.

### Milestone E: Delivery Factories

- GitHub factory.
- WordPress/WooCommerce factory.
- Shopify factory.
- Data analysis factory.
- Site/app generation factory.
- Digital product factory.

## Definition Of Done

The user should be able to open one URL and feel that this is a real OS:

- not a generic chat window;
- not a list of links;
- not many unrelated URLs;
- not a half-hidden backend stack;
- not a fragile pile of scripts.

The OS must show:

- where everything is;
- what each module does;
- what is safe to run;
- what is blocked;
- what agents are doing;
- what memory exists;
- what changed recently;
- what needs attention;
- where outputs were saved;
- how to continue work from any device.

The product is successful when the user can drop an idea, file, repo, site, client task, or dataset into NERD OS and the system can classify it, route it, assign agents/workflows, produce artifacts, update memory, and show the full trail in one interface.

