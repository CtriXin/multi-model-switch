#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/dev_doctor.sh [--no-fetch] [--quiet] [--allow-docs-dirty]

Checks that the repository root is a healthy dev coordination entrypoint.
It reports stale/prunable worktrees but never deletes or resets anything.

Options:
  --no-fetch           Do not refresh origin/dev before ahead/behind checks.
  --quiet             Print only failures and warnings.
  --allow-docs-dirty  Permit docs-only tracked edits for direct plan/report work.
EOF
}

FETCH=1
QUIET=0
ALLOW_DOCS_DIRTY=0

die() {
  echo "FAIL: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

ok() {
  [ "$QUIET" -eq 1 ] || echo "OK: $*"
}

script_dir() {
  CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
}

git_text() {
  git -C "$REPO_ROOT" "$@" | tr -d '\r'
}

is_allowed_local_status() {
  local line="$1"
  case "$line" in
    "?? vendor/handover/CLAUDE.md") return 0 ;;
    "?? .rtk/"*) return 0 ;;
  esac
  return 1
}

is_docs_status() {
  local line="$1"
  local path="${line:3}"
  case "$path" in
    docs/*|README.md|README.en.md|README.zh-CN.md|AGENT.md|AGENTS.md|CLAUDE.md) return 0 ;;
  esac
  return 1
}

check_clean_root() {
  local bad=0
  local docs_dirty=0
  local line
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    if is_allowed_local_status "$line"; then
      warn "allowed local root file: ${line#?? }"
      continue
    fi
    if [ "$ALLOW_DOCS_DIRTY" -eq 1 ] && is_docs_status "$line"; then
      docs_dirty=1
      warn "docs-only direct root edit allowed by flag: $line"
      continue
    fi
    echo "root dev dirty entry: $line" >&2
    bad=1
  done < <(git_text status --porcelain=v1 --untracked-files=all)

  [ "$bad" -eq 0 ] || die "root dev checkout is not clean"
  if [ "$docs_dirty" -eq 1 ]; then
    ok "root has only docs changes allowed for this run"
  else
    ok "root is clean except allowlisted local files"
  fi
}

check_branch() {
  local branch
  branch="$(git_text rev-parse --abbrev-ref HEAD)"
  [ "$branch" = "dev" ] || die "repo root branch must be dev, got $branch"
  ok "repo root is on dev"

  local remote merge
  remote="$(git_text config --get branch.dev.remote || true)"
  merge="$(git_text config --get branch.dev.merge || true)"
  [ "$remote" = "origin" ] || die "dev remote must be origin, got ${remote:-<none>}"
  [ "$merge" = "refs/heads/dev" ] || die "dev merge ref must be refs/heads/dev, got ${merge:-<none>}"
  ok "dev tracks origin/dev"
}

check_remote_freshness() {
  if [ "$FETCH" -eq 1 ]; then
    git -C "$REPO_ROOT" fetch --quiet --prune origin dev || die "failed to fetch origin dev"
  fi

  git -C "$REPO_ROOT" rev-parse --verify --quiet refs/remotes/origin/dev >/dev/null || die "origin/dev is missing"
  local counts ahead behind
  counts="$(git_text rev-list --left-right --count HEAD...refs/remotes/origin/dev)"
  ahead="${counts%%[[:space:]]*}"
  behind="${counts##*[[:space:]]}"
  [ "${behind:-0}" = "0" ] || die "root dev is behind origin/dev by $behind commit(s)"
  if [ "${ahead:-0}" != "0" ]; then
    warn "root dev is ahead of origin/dev by $ahead commit(s); push or reconcile before sharing"
  else
    ok "root dev is not behind origin/dev"
  fi
}

check_legacy_dev_worktree() {
  local legacy="$REPO_ROOT/.worktrees/dev"
  if [ ! -e "$legacy" ]; then
    ok ".worktrees/dev is absent"
    return
  fi
  if git -C "$legacy" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    local branch
    branch="$(git -C "$legacy" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    [ "$branch" != "dev" ] || die ".worktrees/dev is still checked out as dev"
    warn ".worktrees/dev exists but is on $branch, not dev"
  else
    warn ".worktrees/dev exists but is not a readable git worktree"
  fi
}

extract_wrapper_root() {
  local wrapper="$1"
  sed -n -E 's/^ROOT="(.*)"$/\1/p' "$wrapper" | head -n 1
}

check_mmf_wrapper() {
  local mmf_path
  mmf_path="$(command -v mmf || true)"
  if [ -z "$mmf_path" ]; then
    warn "mmf wrapper not found on PATH"
    return
  fi
  if [ ! -f "$mmf_path" ]; then
    warn "mmf exists but is not a regular wrapper file: $mmf_path"
    return
  fi
  local wrapper_root
  wrapper_root="$(extract_wrapper_root "$mmf_path" || true)"
  if [ -z "$wrapper_root" ]; then
    warn "could not read ROOT from mmf wrapper: $mmf_path"
    return
  fi
  local real_wrapper_root real_repo_root
  real_wrapper_root="$(cd "$wrapper_root" 2>/dev/null && pwd -P || true)"
  real_repo_root="$(cd "$REPO_ROOT" && pwd -P)"
  if [ "$real_wrapper_root" = "$real_repo_root" ]; then
    ok "mmf wrapper points to repo-root dev checkout"
  else
    warn "mmf wrapper points to $wrapper_root, expected $REPO_ROOT"
  fi
}

report_prunable_worktrees() {
  local current_path prunable reason seen=0
  while IFS= read -r line; do
    case "$line" in
      worktree\ *) current_path="${line#worktree }"; prunable=0; reason="" ;;
      prunable*) prunable=1; reason="${line#prunable }" ;;
      "")
        if [ "${prunable:-0}" -eq 1 ]; then
          warn "prunable worktree reported by git: $current_path ${reason:+($reason)}"
          seen=1
        fi
        ;;
    esac
  done < <(git -C "$REPO_ROOT" worktree list --porcelain; echo)
  [ "$seen" -eq 1 ] || ok "no prunable worktrees reported"
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --no-fetch) FETCH=0 ;;
      --quiet) QUIET=1 ;;
      --allow-docs-dirty) ALLOW_DOCS_DIRTY=1 ;;
      -h|--help) usage; exit 0 ;;
      *) usage >&2; exit 2 ;;
    esac
    shift
  done
}

main() {
  parse_args "$@"
  git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null || die "not a git checkout: $REPO_ROOT"
  check_branch
  check_clean_root
  check_remote_freshness
  check_legacy_dev_worktree
  check_mmf_wrapper
  report_prunable_worktrees
  ok "dev coordination entrypoint is healthy"
}

SCRIPT_DIR="$(script_dir)"
REPO_ROOT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel)"
main "$@"
