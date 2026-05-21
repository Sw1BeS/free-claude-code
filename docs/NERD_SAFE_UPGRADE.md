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

### Final Switch Checklist

- Confirm the staged branch is clean and points at the reviewed commit:

```bash
git -C /root/nerd-claude-free-staging status --short --branch
git -C /root/nerd-claude-free-staging log --oneline --decorate -8
```

- Confirm both services are healthy before any port move:

```bash
free-claude status
curl -fsS http://127.0.0.1:18082/health
curl -fsS http://127.0.0.1:8082/health
```

- Confirm the Admin UI is local-only and branded:

```bash
curl -fsS http://127.0.0.1:18082/admin | rg '\[NERD-CLAUDE\]-free|admin.js'
curl -sS -o /tmp/nerd-admin-forbidden.txt -w '%{http_code}' http://127.0.0.1:18082/admin -H 'Origin: https://example.com'
```

Expected remote-origin response: `403`.

- Confirm secret material is not committed:

```bash
git -C /root/nerd-claude-free-staging grep -n -E 'sk-[A-Za-z0-9_-]{20,}|nvapi-[A-Za-z0-9_-]{20,}|wfr_[A-Za-z0-9_-]{20,}' HEAD || true
```

- Stop staged service before moving ports:

```bash
free-claude stop
```

- Stop legacy only after explicit approval and record how it was running:

```bash
systemctl status legacy-free-claude --no-pager --lines=20 || true
ss -ltnp | rg ':8082' || true
```

- Move staged config to `8082`:

```bash
python3 - <<'PY'
from pathlib import Path

path = Path("/root/.fcc/.env")
lines = []
updated = False
for line in path.read_text(encoding="utf-8").splitlines():
    if line.startswith("PORT="):
        lines.append('PORT="8082"')
        updated = True
    else:
        lines.append(line)
if not updated:
    lines.append('PORT="8082"')
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
```

- Start the promoted service and verify:

```bash
free-claude ui
free-claude status
curl -fsS http://127.0.0.1:8082/health
```

- Roll back by stopping staged, restoring `PORT="18082"` in `/root/.fcc/.env`, and starting the legacy service or original legacy command again.

## Rollback

Use the legacy command:

```bash
free-claude legacy
```

The staged stop command only stops the staged managed PID:

```bash
free-claude stop
```
