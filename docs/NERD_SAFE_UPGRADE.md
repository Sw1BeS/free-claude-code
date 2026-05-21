# [NERD-CLAUDE]-free Safe Upgrade Runbook

## Ownership

- Upstream ClaudeCore: `https://github.com/Alishahryar1/free-claude-code`
- Legacy deployment: `/root/free-claude-code`
- Staged deployment: `/root/nerd-claude-free-staging`
- Staged branch: `nerd/safe-upgrade`
- Managed config: `/root/.fcc/.env`

## Daily Commands

```bash
free-claude status
free-claude ui
free-claude
free-claude stop
free-claude legacy
```

## Staged Proxy

The staged proxy binds to `127.0.0.1:18082` by default. The legacy proxy remains on `8082` until a manual final switch is approved.

Check staged health:

```bash
curl -fsS http://127.0.0.1:18082/health
```

Check legacy health:

```bash
curl -fsS http://127.0.0.1:8082/health
```

## Secrets

Provider keys live only in `/root/.fcc/.env` or process environment. Do not commit `.env` files. Keys shared in chat should be rotated before durable production use.

## Final Switch

The final switch to port `8082` is not automatic. Before switching, all staged checks must pass:

```bash
uv sync
uv run ruff check
uv run ty check
uv run pytest
free-claude status
free-claude ui
curl -fsS http://127.0.0.1:18082/health
curl -fsS http://127.0.0.1:8082/health
```

After a separate approval, stop the legacy process, change `/root/.fcc/.env` `PORT` from `18082` to `8082`, and start `free-claude ui`. Keep `/root/free-claude-code` available for rollback.

## Rollback

Use the legacy command:

```bash
free-claude legacy
```

The staged stop command only stops the staged managed PID:

```bash
free-claude stop
```
