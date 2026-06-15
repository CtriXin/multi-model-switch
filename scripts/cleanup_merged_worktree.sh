#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/cleanup_merged_worktree.sh [--base dev] [--dry-run] [--no-prune] [--delete-local-branch] <branch|pr-number|pr-url>

Safely removes a local task worktree only after the branch/PR is merged into
the base branch and the worktree is clean. The script never resets files and
never removes dirty or unmerged worktrees.

Examples:
  scripts/cleanup_merged_worktree.sh issue/17-dev-worktree-automation
  scripts/cleanup_merged_worktree.sh 23
  scripts/cleanup_merged_worktree.sh --dry-run --base dev issue/18-clean-merged-worktrees
EOF
}

BASE_BRANCH="dev"
DRY_RUN=0
PRUNE=1
DELETE_LOCAL_BRANCH=0
TARGET=""
PR_NUMBER=""
PR_STATE=""
PR_MERGED_AT=""
PR_HEAD_OID=""

die() {
  echo "FAIL: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

info() {
  echo "==> $*"
}

script_dir() {
  CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
}

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'DRY-RUN:'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --base)
        [ "$#" -ge 2 ] || die "--base requires a value"
        BASE_BRANCH="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --no-prune)
        PRUNE=0
        shift
        ;;
      --delete-local-branch)
        DELETE_LOCAL_BRANCH=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      -*)
        usage >&2
        exit 2
        ;;
      *)
        [ -z "$TARGET" ] || die "only one branch or PR target is allowed"
        TARGET="$1"
        shift
        ;;
    esac
  done
  [ -n "$TARGET" ] || {
    usage >&2
    exit 2
  }
}

parse_pr_number() {
  local value="$1"
  case "$value" in
    \#*) value="${value#\#}" ;;
  esac
  if [[ "$value" =~ ^https://github.com/[^/]+/[^/]+/pull/([0-9]+)$ ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
    return 0
  fi
  if [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$value"
    return 0
  fi
  return 1
}

github_repo_slug() {
  local remote
  remote="$(git -C "$REPO_ROOT" config --get remote.origin.url || true)"
  case "$remote" in
    git@github.com:*.git) remote="${remote#git@github.com:}"; remote="${remote%.git}" ;;
    git@github.com:*) remote="${remote#git@github.com:}" ;;
    https://github.com/*.git) remote="${remote#https://github.com/}"; remote="${remote%.git}" ;;
    https://github.com/*) remote="${remote#https://github.com/}" ;;
    *) remote="" ;;
  esac
  [ -n "$remote" ] || die "could not derive GitHub repo from origin remote"
  printf '%s\n' "$remote"
}

resolve_target_branch() {
  local value="$1"
  if PR_NUMBER="$(parse_pr_number "$value")"; then
    command -v gh >/dev/null 2>&1 || die "gh is required to resolve PR #$PR_NUMBER"
    local pr_json
    pr_json="$(gh -R "$(github_repo_slug)" pr view "$PR_NUMBER" --json headRefName,baseRefName,state,mergedAt,headRefOid)"
    parse_pr_json "$pr_json"
    [ -n "$TARGET_BRANCH" ] || die "could not resolve PR #$PR_NUMBER head branch"
    [ "$PR_STATE" = "MERGED" ] || die "PR #$PR_NUMBER is not merged; state=$PR_STATE"
    [ -n "$PR_MERGED_AT" ] || die "PR #$PR_NUMBER has no mergedAt timestamp"
    return
  fi

  TARGET_BRANCH="$value"
  if command -v gh >/dev/null 2>&1; then
    local pr_json
    if pr_json="$(gh pr view "$TARGET_BRANCH" --json headRefName,baseRefName,state,mergedAt,headRefOid 2>/dev/null)"; then
      parse_pr_json "$pr_json"
    fi
  fi
}

parse_pr_json() {
  local pr_json="$1"
  local parsed
  parsed="$(python3 - "$pr_json" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
print(data.get("headRefName") or "")
print(data.get("baseRefName") or "")
print(data.get("state") or "")
print(data.get("mergedAt") or "")
print(data.get("headRefOid") or "")
PY
)"
  TARGET_BRANCH="$(printf '%s\n' "$parsed" | sed -n '1p')"
  BASE_BRANCH="$(printf '%s\n' "$parsed" | sed -n '2p')"
  PR_STATE="$(printf '%s\n' "$parsed" | sed -n '3p')"
  PR_MERGED_AT="$(printf '%s\n' "$parsed" | sed -n '4p')"
  PR_HEAD_OID="$(printf '%s\n' "$parsed" | sed -n '5p')"
}

find_worktree_for_branch() {
  local branch_ref="refs/heads/$1"
  local current_path=""
  local current_branch=""
  while IFS= read -r line; do
    case "$line" in
      worktree\ *) current_path="${line#worktree }"; current_branch="" ;;
      branch\ *) current_branch="${line#branch }" ;;
      "")
        if [ "$current_branch" = "$branch_ref" ]; then
          printf '%s\n' "$current_path"
          return 0
        fi
        ;;
    esac
  done < <(git -C "$REPO_ROOT" worktree list --porcelain; echo)
  return 1
}

ensure_base_ref() {
  git -C "$REPO_ROOT" fetch --quiet --prune origin "$BASE_BRANCH" || die "failed to fetch origin $BASE_BRANCH"
  git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/remotes/origin/$BASE_BRANCH" >/dev/null ||
    die "missing refs/remotes/origin/$BASE_BRANCH"
}

ensure_branch_merged() {
  local branch="$1"
  git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/heads/$branch" >/dev/null ||
    die "local branch does not exist: $branch"
  if [ "$PR_STATE" = "MERGED" ] && [ -n "$PR_MERGED_AT" ]; then
    if [ -n "$PR_HEAD_OID" ]; then
      local local_oid
      local_oid="$(git -C "$REPO_ROOT" rev-parse "refs/heads/$branch")"
      [ "$local_oid" = "$PR_HEAD_OID" ] ||
        die "$branch has local commits beyond merged PR head $PR_HEAD_OID; preserving worktree"
    fi
    info "$branch is recorded as merged PR into $BASE_BRANCH at $PR_MERGED_AT"
    return
  fi
  if git -C "$REPO_ROOT" merge-base --is-ancestor "refs/heads/$branch" "refs/remotes/origin/$BASE_BRANCH"; then
    info "$branch is merged into origin/$BASE_BRANCH"
  else
    die "$branch is not fully merged into origin/$BASE_BRANCH; preserving worktree"
  fi
}

ensure_worktree_clean() {
  local path="$1"
  local status
  status="$(git -C "$path" status --porcelain=v1 --untracked-files=all)"
  if [ -n "$status" ]; then
    echo "$status" >&2
    die "worktree has uncommitted or untracked files; preserving $path"
  fi
  info "worktree is clean: $path"
}

delete_branch_if_requested() {
  local branch="$1"
  [ "$DELETE_LOCAL_BRANCH" -eq 1 ] || {
    info "local branch preserved: $branch"
    return
  }
  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$branch"; then
    run git -C "$REPO_ROOT" branch -d "$branch"
  else
    warn "local branch already absent: $branch"
  fi
}

main() {
  parse_args "$@"
  git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null || die "not a git checkout: $REPO_ROOT"

  resolve_target_branch "$TARGET"
  info "cleanup target branch: $TARGET_BRANCH"
  info "base branch: $BASE_BRANCH"
  [ -z "$PR_NUMBER" ] || info "resolved from merged PR #$PR_NUMBER at $PR_MERGED_AT"

  ensure_base_ref
  local worktree_path
  if ! worktree_path="$(find_worktree_for_branch "$TARGET_BRANCH")"; then
    warn "no local worktree found for $TARGET_BRANCH; nothing to remove"
    exit 0
  fi
  ensure_branch_merged "$TARGET_BRANCH"
  ensure_worktree_clean "$worktree_path"

  run git -C "$REPO_ROOT" worktree remove "$worktree_path"
  if [ "$PRUNE" -eq 1 ]; then
    run git -C "$REPO_ROOT" worktree prune
  fi
  delete_branch_if_requested "$TARGET_BRANCH"

  info "cleanup complete for $TARGET_BRANCH"
}

SCRIPT_DIR="$(script_dir)"
REPO_ROOT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel)"
TARGET_BRANCH=""
main "$@"
