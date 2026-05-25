# NERD Method Brain

Generated: `2026-05-24T17:25:52Z`

| ID | Name | Kind | Status | Domain | Risk | Action |
| --- | --- | --- | --- | --- | --- | --- |
| `brain-canonical-repo` | Brain Canonical Repo | repo | present | brain-source | medium | keep |
|  | path=/root/nerd-claude-free-staging; notes=Versioned implementation source for NERD-METHOD inventory and sync scripts; evidence=/root/nerd-claude-free-staging |  |  |  |  |  |
| `brain-gitnexus` | GitNexus Code Graph | service | active | brain-codegraph | low | keep |
|  | source=https://agency.umanoff-analytics.space/nerd-os/; notes=Code intelligence surface is linked through NERD OS; raw backend remains private; evidence=https://agency.umanoff-analytics.space/nerd-os/ |  |  |  |  |  |
| `brain-langfuse` | Langfuse Observability | service | active | brain-observability | low | keep |
|  | source=https://obs.umanoff-analytics.space; notes=Observability workspace route; raw trace backend remains private; evidence=https://obs.umanoff-analytics.space |  |  |  |  |  |
| `brain-n8n` | n8n Automation | service | active | brain-automation | medium | keep |
|  | source=https://automations.umanoff-analytics.space; notes=Automation workspace route; raw n8n backend remains private; evidence=https://automations.umanoff-analytics.space |  |  |  |  |  |
| `brain-nerd-method` | NERD Method Knowledge | repo | present | brain-knowledge | medium | normalize |
|  | path=/root/nerd-method; notes=Knowledge repo expected to hold normalized NERD-METHOD operating material; evidence=/root/nerd-method |  |  |  |  |  |
| `brain-obsidian-vault` | Obsidian Vault | dir | present | brain-surface | low | normalize |
|  | path=/root/obsidian-vault; notes=markdown_note_count=1; evidence=/root/obsidian-vault |  |  |  |  |  |
| `brain-openwebui-knowledge` | Open WebUI Knowledge Surface | service | investigate | brain-surface | medium | normalize |
|  | source=https://agency.umanoff-analytics.space; notes=Public knowledge surface; verify seeded docs through controlled sync; evidence=https://agency.umanoff-analytics.space |  |  |  |  |  |
| `brain-runtime-stack` | Brain Runtime Stack | dir | present | brain-runtime | medium | keep |
|  | path=/root/nerd-agency-stack; notes=Live runtime target for Mission Control and local brain services; evidence=/root/nerd-agency-stack |  |  |  |  |  |
| `brain-sync-inventory` | Inventory Generator | config | present | brain-sync | medium | keep |
|  | path=/root/nerd-claude-free-staging/scripts/nerd/generate_inventory.py; notes=Deterministic brain sync target; evidence=/root/nerd-claude-free-staging/scripts/nerd/generate_inventory.py |  |  |  |  |  |
| `brain-sync-openwebui-seed` | Open WebUI Seed Script | config | present | brain-sync | medium | keep |
|  | path=/root/nerd-claude-free-staging/scripts/nerd/agency/openwebui_seed.py; notes=Deterministic brain sync target; evidence=/root/nerd-claude-free-staging/scripts/nerd/agency/openwebui_seed.py |  |  |  |  |  |
| `brain-sync-stack-seed` | Runtime Open WebUI Seed Script | config | present | brain-sync | medium | keep |
|  | path=/root/nerd-agency-stack/scripts/seed-openwebui.sh; notes=Deterministic brain sync target; evidence=/root/nerd-agency-stack/scripts/seed-openwebui.sh |  |  |  |  |  |

## Warnings

- /root/obsidian-vault: fewer than two Markdown notes found for the brain surface
- /root/nerd-method: not a git repository
