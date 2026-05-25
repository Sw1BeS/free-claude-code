#!/usr/bin/env bash
set -uo pipefail

secret_pattern='(sk-or-v1-[A-Za-z0-9]{32,}|sk-[A-Za-z0-9]{32,}|nvapi-[A-Za-z0-9_-]{20,}|wfr_[A-Fa-f0-9]{20,})'

fail() {
  printf 'git-guard: %s\n' "$*" >&2
  exit 1
}

git_value() {
  git "$@" 2>/dev/null || true
}

remote_owner() {
  local url="${1%.git}"
  case "$url" in
    https://github.com/*/*)
      url="${url#https://github.com/}"
      printf '%s\n' "${url%%/*}"
      ;;
    git@github.com:*/*)
      url="${url#git@github.com:}"
      printf '%s\n' "${url%%/*}"
      ;;
    ssh://git@github.com/*/*)
      url="${url#ssh://git@github.com/}"
      printf '%s\n' "${url%%/*}"
      ;;
    *)
      printf '\n'
      ;;
  esac
}

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "not inside a git repository"

branch="$(git_value branch --show-current)"
origin_fetch="$(git_value remote get-url origin)"
origin_push="$(git_value remote get-url --push origin)"
upstream_fetch="$(git_value remote get-url upstream)"
upstream_push="$(git_value remote get-url --push upstream)"
allowed_owner="${NERD_GIT_ALLOWED_OWNER:-$(remote_owner "$origin_push")}"

[ -n "$branch" ] || fail "unable to resolve current branch"
[ -n "$origin_push" ] || fail "origin push remote is not configured"
[ -n "$allowed_owner" ] || fail "unable to infer allowed GitHub owner; set NERD_GIT_ALLOWED_OWNER"

printf 'branch=%s\n' "$branch"
printf 'origin_fetch=%s\n' "$origin_fetch"
printf 'origin_push=%s\n' "$origin_push"
printf 'upstream_fetch=%s\n' "$upstream_fetch"
printf 'upstream_push=%s\n' "$upstream_push"
printf 'allowed_owner=%s\n' "$allowed_owner"

origin_owner="$(remote_owner "$origin_push")"
[ "$origin_owner" = "$allowed_owner" ] || fail "origin push remote is not owned by $allowed_owner: $origin_push"

if [ -n "$upstream_push" ] && [ "$upstream_push" != "DISABLED" ] && [ "$upstream_push" != "no_push" ]; then
  upstream_owner="$(remote_owner "$upstream_push")"
  [ "$upstream_owner" = "$allowed_owner" ] || fail "upstream push remote is not protected: $upstream_push"
fi

dirty="$(git status --porcelain)"
if [ -n "$dirty" ] && [ "${NERD_GIT_ALLOW_DIRTY:-0}" != "1" ]; then
  fail "dirty tree; commit/stash changes or set NERD_GIT_ALLOW_DIRTY=1 for inspection-only runs"
fi

if git diff --cached --no-ext-diff | grep -E "$secret_pattern" >/dev/null 2>&1; then
  printf 'git-guard: warning: staged diff appears to contain a private token\n' >&2
fi
if git diff --no-ext-diff | grep -E "$secret_pattern" >/dev/null 2>&1; then
  printf 'git-guard: warning: unstaged diff appears to contain a private token\n' >&2
fi

printf 'git-guard=ok\n'
