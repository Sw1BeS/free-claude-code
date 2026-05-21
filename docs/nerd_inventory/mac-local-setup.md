# Mac Local Setup

Purpose: mirror this staged `[NERD-CLAUDE]-free` setup on a local Mac without replacing the server deployment.

## Install

1. Install runtime dependencies:

```bash
brew install git uv node ripgrep
uv python install 3.14
npm install -g @anthropic-ai/claude-code
```

2. Clone the upstream and create a NERD staging branch:

```bash
git clone https://github.com/Alishahryar1/free-claude-code.git ~/nerd-claude-free-staging
cd ~/nerd-claude-free-staging
git remote rename origin upstream
git checkout -b nerd/safe-upgrade
uv sync
```

3. Copy the NERD wrapper:

```bash
mkdir -p ~/.local/bin ~/.fcc/logs
cp scripts/nerd/free-claude ~/.local/bin/free-claude
chmod +x ~/.local/bin/free-claude
```

4. Create private Mac env at `~/.fcc/.env`. Keep provider keys out of git. Use the Admin UI or a local password manager to fill:

```dotenv
HOST="127.0.0.1"
PORT="18082"
ANTHROPIC_AUTH_TOKEN="change-me"
MODEL="open_router/stepfun/step-3.5-flash:free"
NVIDIA_NIM_API_KEY=""
OPENROUTER_API_KEY=""
DEEPSEEK_API_KEY=""
KIMI_API_KEY=""
WAFER_API_KEY=""
```

5. Launch:

```bash
free-claude status
free-claude ui
free-claude
```

## Sync Boundary

- Sync durable knowledge: `docs/nerd_inventory`, selected skills, activation manifests, project notes, Obsidian vault, and explicit MCP server configs.
- Do not sync raw `.env`, `.ssh`, `.git-credentials`, logs, caches, or provider tokens.
- Use Git for code/config and a private encrypted sync layer for personal knowledge and client data.
- Treat server and Mac as separate workers in the UI/task layer until a proper job router exists.

## Next Mac Work

1. Package `scripts/nerd/free-claude` as a Homebrew-friendly installer.
2. Add a signed launchd plist for optional background proxy startup.
3. Add an activation manifest for skills/MCP servers that can be replayed on Mac.
4. Add a task router that can target `server`, `mac`, or `both` after authentication and sync are designed.
