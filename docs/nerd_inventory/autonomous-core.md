# Autonomous Core

Generated: `2026-05-24T17:25:52Z`

| ID | Name | Kind | Status | Domain | Risk | Action |
| --- | --- | --- | --- | --- | --- | --- |
| `autonomous-core-canonical-root` | NERD-METHOD Canonical Root | dir | present | autonomous-core | low | keep |
|  | classification=installed; path=/root/nerd-method; notes=Product root for Autonomous Core state; staging workspaces must not replace it.; evidence=/root/nerd-method/AGENTS.md, /root/nerd-method/memory |  |  |  |  |  |
| `autonomous-core-lab` | High-Risk Lab Gate | config | staged | lab | high | review_later |
|  | classification=high-risk-disabled; path=/root/nerd-method/departments/lab; notes=Lab requests are recorded and routed to approval; real-world harmful actions remain blocked.; evidence=/root/nerd-method/system/risk-policy.yaml, /root/nerd-method/departments/lab |  |  |  |  |  |
| `autonomous-core-memory` | Autonomous Core Memory | dir | present | memory | medium | index |
|  | classification=installed; path=/root/nerd-method/memory; notes=JSON-first memory queues for inbox, tasks, runs, traces, reports, and artifacts.; evidence=/root/nerd-method/memory/inbox, /root/nerd-method/memory/tasks, /root/nerd-method/memory/runs, /root/nerd-method/memory/artifacts |  |  |  |  |  |
| `autonomous-core-n8n-visibility` | n8n Workflow Visibility | service | present | automations | medium | normalize |
|  | classification=runtime-candidate; path=/root/nerd-agency-stack/n8n/v1-workflows; source=https://automations.umanoff-analytics.space; notes=Workflows are visible records with gates; Autonomous Core does not run hidden workflow state.; evidence=/root/nerd-agency-stack/n8n/v1-workflows, /root/nerd-method/registry/workflows.json |  |  |  |  |  |
| `autonomous-core-registry` | Autonomous Core Registry | config | present | autonomous-core | low | index |
|  | classification=installed; path=/root/nerd-method/registry; notes=Canonical registry for existing work, departments, tools, workflows, and model profiles.; evidence=/root/nerd-method/registry/existing-work.json, /root/nerd-method/registry/departments.json, /root/nerd-method/registry/models.json, /root/nerd-method/registry/workflows.json |  |  |  |  |  |
| `autonomous-core-runtime-integrations` | Runtime Integrations Registry | config | present | runtimes | medium | index |
|  | classification=runtime-candidate; path=/root/nerd-method/registry/runtime-integrations.json; notes=Read-only registry for Hermes, OpenClaw sources, local LLMs, LiteLLM, Ollama, and model routers.; evidence=/root/nerd-method/registry/runtime-integrations.json, /root/nerd-method/system/model-routing.yaml, /root/hermes, /root/nerd-method/tools/git-inspired/awesome-openclaw-skills |  |  |  |  |  |
| `autonomous-core-system-policy` | Autonomous Core System Policy | config | present | autonomous-core | medium | normalize |
|  | classification=runtime-candidate; path=/root/nerd-method/system; notes=Policy files define model routing, autonomy levels, risk gates, and memory writeback.; evidence=/root/nerd-method/system/autonomy-policy.yaml, /root/nerd-method/system/risk-policy.yaml, /root/nerd-method/system/model-routing.yaml, /root/nerd-method/system/memory-contract.yaml |  |  |  |  |  |
