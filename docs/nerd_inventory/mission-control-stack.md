# Mission Control Stack

Generated: `2026-05-22T12:06:31Z`

| ID | Name | Kind | Status | Domain | Risk | Action |
| --- | --- | --- | --- | --- | --- | --- |
| `activation-pack-cms-commerce` | Activation Pack: cms-commerce | config | present | skills | low | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=WordPress, WooCommerce, Shopify, SEO, analytics; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `activation-pack-daily` | Activation Pack: daily | config | present | skills | low | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=GitHub, GitNexus, n8n, Open WebUI, Langfuse, Obsidian, NotebookLM; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `activation-pack-data` | Activation Pack: data | config | present | skills | low | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Polars, vector DB, scraping, data analytics; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `activation-pack-security-safe` | Activation Pack: security-safe | config | present | skills | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Audit/review only; no offensive active tooling in V1; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `memory-layer-clients` | Unified Memory: clients | config | present | unified-memory | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Client context, preferences, constraints, and reusable delivery patterns; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `memory-layer-projects` | Unified Memory: projects | config | present | unified-memory | low | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Client/project docs, task history, GitHub/GitNexus notes, and implementation reports; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `memory-layer-prompts` | Unified Memory: prompts | config | present | unified-memory | low | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Prompt library, reusable skills, activation packs, and workflow templates; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `memory-layer-system` | Unified Memory: system | config | present | unified-memory | low | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Open WebUI knowledge, NERD inventory, manifest, service directory, and operating policies; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `memory-layer-traces` | Unified Memory: traces | config | present | unified-memory | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Langfuse traces, Grafana links, n8n executions, and incident notes; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `mission-docker-compose` | Mission Control docker-compose.yml | config | present | mission-control | medium | keep |
|  | path=/root/nerd-agency-stack/docker-compose.yml; evidence=/root/nerd-agency-stack/docker-compose.yml |  |  |  |  |  |
| `mission-domains` | Mission Control nerd-agency.domains.yaml | config | present | mission-control | low | keep |
|  | path=/root/nerd-agency-stack/nerd-agency.domains.yaml; evidence=/root/nerd-agency-stack/nerd-agency.domains.yaml |  |  |  |  |  |
| `mission-env-example` | Mission Control .env.example | config | present | mission-control | low | keep |
|  | path=/root/nerd-agency-stack/.env.example; evidence=/root/nerd-agency-stack/.env.example |  |  |  |  |  |
| `mission-manifest` | Mission Control nerd-agency.manifest.yaml | config | present | mission-control | medium | keep |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `mission-nginx-http` | Mission Control nginx/nerd-agency-mission-control.http.conf | config | present | mission-control | low | keep |
|  | path=/root/nerd-agency-stack/nginx/nerd-agency-mission-control.http.conf; evidence=/root/nerd-agency-stack/nginx/nerd-agency-mission-control.http.conf |  |  |  |  |  |
| `mission-nginx-https` | Mission Control nginx/nerd-agency-mission-control.https.conf | config | present | mission-control | low | keep |
|  | path=/root/nerd-agency-stack/nginx/nerd-agency-mission-control.https.conf; evidence=/root/nerd-agency-stack/nginx/nerd-agency-mission-control.https.conf |  |  |  |  |  |
| `n8n-v1-workflows` | n8n V1 Workflows | config | present | automation | medium | normalize |
|  | path=/root/nerd-agency-stack/n8n/v1-workflows; notes=count=5; workflows=cms-commerce-planning.workflow.json, github-repo-triage.workflow.json, health-status.workflow.json, langfuse-trace-lookup.workflow.json, regenerate-inventory.workflow.json; evidence=/root/nerd-agency-stack/n8n/v1-workflows |  |  |  |  |  |
| `nerd-agency-stack` | NERD Agency Stack | dir | present | mission-control | medium | keep |
|  | path=/root/nerd-agency-stack; notes=public_url=https://agency.umanoff-analytics.space; open_webui_loopback=http://127.0.0.1:38080; evidence=/root/nerd-agency-stack |  |  |  |  |  |
| `public-domain-agency` | Public Domain: agency.umanoff-analytics.space | service | investigate | public-routing | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Primary Mission Control shell; target=agency.umanoff-analytics.space; backend=Open WebUI; expose_raw_backend=false; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `public-domain-agents` | Public Domain: agents.umanoff-analytics.space | service | investigate | public-routing | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Agent task workspaces routed to Mission Control; target=agency.umanoff-analytics.space; backend=Open WebUI; expose_raw_backend=false; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `public-domain-automations` | Public Domain: automations.umanoff-analytics.space | service | investigate | public-routing | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Automation workspace routed to Mission Control; target=agency.umanoff-analytics.space; backend=Open WebUI; expose_raw_backend=false; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `public-domain-cms` | Public Domain: cms.umanoff-analytics.space | service | investigate | public-routing | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=CMS and commerce workspace routed to Mission Control; target=agency.umanoff-analytics.space; backend=Open WebUI; expose_raw_backend=false; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `public-domain-memory` | Public Domain: memory.umanoff-analytics.space | service | investigate | public-routing | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Unified memory and knowledge workspace routed to Mission Control; target=agency.umanoff-analytics.space; backend=Open WebUI; expose_raw_backend=false; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `public-domain-obs` | Public Domain: obs.umanoff-analytics.space | service | investigate | public-routing | medium | normalize |
|  | path=/root/nerd-agency-stack/nerd-agency.manifest.yaml; notes=Observability workspace routed to Mission Control; target=agency.umanoff-analytics.space; backend=Open WebUI; expose_raw_backend=false; evidence=/root/nerd-agency-stack/nerd-agency.manifest.yaml |  |  |  |  |  |
| `service-free-claude-admin` | Internal Service: free-claude-admin | service | active | service-map | medium | keep |
|  | notes=internal_url=http://127.0.0.1:18082/admin |  |  |  |  |  |
| `service-gitnexus` | Internal Service: gitnexus | service | active | service-map | low | keep |
|  | notes=internal_url=http://127.0.0.1:4173 |  |  |  |  |  |
| `service-grafana` | Internal Service: grafana | service | active | service-map | low | keep |
|  | notes=internal_url=http://127.0.0.1:3002 |  |  |  |  |  |
| `service-langfuse` | Internal Service: langfuse | service | active | service-map | low | keep |
|  | notes=internal_url=http://127.0.0.1:3300 |  |  |  |  |  |
| `service-litellm` | Internal Service: litellm | service | active | service-map | low | keep |
|  | notes=internal_url=http://127.0.0.1:44000 |  |  |  |  |  |
| `service-n8n` | Internal Service: n8n | service | active | service-map | low | keep |
|  | notes=internal_url=http://127.0.0.1:5678 |  |  |  |  |  |
| `service-ollama` | Internal Service: ollama | service | active | service-map | low | keep |
|  | notes=internal_url=http://127.0.0.1:11434 |  |  |  |  |  |
| `service-open-webui` | Internal Service: open-webui | service | active | service-map | medium | keep |
|  | notes=internal_url=http://127.0.0.1:38080 |  |  |  |  |  |
