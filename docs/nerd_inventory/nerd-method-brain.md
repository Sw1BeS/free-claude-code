# NERD Method Brain

Generated: `2026-05-22T01:23:32Z`

| ID | Name | Kind | Status | Domain | Risk | Action |
| --- | --- | --- | --- | --- | --- | --- |
| `brain-canonical-repo` | Brain Canonical Repo | repo | present | brain-source | medium | keep |
|  | path=/root/nerd-claude-free-staging; notes=Versioned implementation source for NERD-METHOD inventory and sync scripts; evidence=/root/nerd-claude-free-staging |  |  |  |  |  |
| `brain-gitnexus` | GitNexus Code Graph | service | active | brain-codegraph | low | keep |
|  | source=http://127.0.0.1:4173; notes=Internal loopback code graph service; evidence=http://127.0.0.1:4173 |  |  |  |  |  |
| `brain-langfuse` | Langfuse Observability | service | active | brain-observability | low | keep |
|  | source=http://127.0.0.1:3300; notes=Internal loopback observability service; evidence=http://127.0.0.1:3300 |  |  |  |  |  |
| `brain-n8n` | n8n Automation | service | active | brain-automation | medium | keep |
|  | source=http://127.0.0.1:5678; notes=Internal loopback automation service; evidence=http://127.0.0.1:5678 |  |  |  |  |  |
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
