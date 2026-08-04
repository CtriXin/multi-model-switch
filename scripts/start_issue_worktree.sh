#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/start_issue_worktree.sh <issue-number> <slug>

Example:
  scripts/start_issue_worktree.sh 14 redline-gate

Creates:
  branch:   issue/<issue-number>-<slug>
  worktree: .worktrees/issue-<issue-number>-<slug>
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

info() {
  echo "==> $*"
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

ensure_clean_root() {
  local bad=0
  local line
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    if is_allowed_local_status "$line"; then
      echo "warning: allowed local file in root dev checkout: ${line#?? }" >&2
      continue
    fi
    echo "dirty root entry blocks issue worktree creation: $line" >&2
    bad=1
  done < <(git_text status --porcelain=v1 --untracked-files=all)
  [ "$bad" -eq 0 ] || die "repo root must be clean before opening an issue worktree"
}

sanitize_slug() {
  local raw="$1"
  local slug
  slug="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
  [ -n "$slug" ] || die "slug becomes empty after sanitizing: $raw"
  printf '%s\n' "$slug"
}

main() {
  if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
    exit 0
  fi
  [ "$#" -eq 2 ] || {
    usage >&2
    exit 2
  }

  local issue="$1"
  local slug
  [[ "$issue" =~ ^[0-9]+$ ]] || die "issue number must be numeric: $issue"
  slug="$(sanitize_slug "$2")"

  local branch="issue/${issue}-${slug}"
  local worktree_name="issue-${issue}-${slug}"
  local worktree_path="$REPO_ROOT/.worktrees/$worktree_name"

  git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null || die "not a git checkout: $REPO_ROOT"
  [ "$(git_text rev-parse --abbrev-ref HEAD)" = "dev" ] || die "repo root must be checked out on dev"
  [ "$(git_text config --get branch.dev.remote || true)" = "origin" ] || die "dev must track origin/dev"
  [ "$(git_text config --get branch.dev.merge || true)" = "refs/heads/dev" ] || die "dev must track origin/dev"

  ensure_clean_root

  info "fetching and fast-forwarding dev"
  git -C "$REPO_ROOT" fetch --prune origin dev
  git -C "$REPO_ROOT" pull --ff-only origin dev
  ensure_clean_root

  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$branch"; then
    die "local branch already exists: $branch"
  fi
  if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    die "remote branch already exists: origin/$branch"
  fi
  [ ! -e "$worktree_path" ] || die "worktree path already exists: $worktree_path"

  mkdir -p "$REPO_ROOT/.worktrees"
  info "creating $worktree_path on $branch"
  git -C "$REPO_ROOT" worktree add -b "$branch" "$worktree_path" HEAD

  # TB-09.1:fresh worktree 自动就位(node_modules symlink 契约 + hook 兼容),fail-soft 不挡创建
  "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/worktree-post-create.sh" "$REPO_ROOT" "$worktree_path" \
    || info "worktree-post-create 警告(不阻断;见上)"

  cat <<EOF

Created issue worktree.

  Issue:    #$issue
  Branch:   $branch
  Worktree: $worktree_path
  Base:     dev

Next commands:

  cd "$worktree_path"
  git status --short --branch
  # develop, validate, commit, push
  git push -u origin "$branch"
  gh pr create --base dev --head "$branch" --fill

After merge, fast-forward the root dev checkout before the next task:

  git -C "$REPO_ROOT" pull --ff-only origin dev
EOF
}

SCRIPT_DIR="$(script_dir)"
REPO_ROOT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel)"
main "$@"
