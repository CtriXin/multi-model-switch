#!/usr/bin/env bash
# worktree-post-create.sh — fresh worktree 创建后的自动就位（TB-09.1，issue #33 C10）
#
# 治两个「fresh worktree 必出血」：
#   件A hook 静默全跳：core.hooksPath=.husky/_ 而 `_` 被 gitignore、不随 worktree 继承
#      → 主解法是把 `.husky/_` 入仓（覆盖所有创建路径，含手动 git worktree add）；
#        本脚本只做兜底——目标仓 `_` 缺失时 npm run prepare 重建。
#   件B vite: command not found：node_modules 未跟踪不继承
#      → 按 patterns/resource-acquisition-gap-writeback.md 契约 symlink 复用：
#        仅当两边 package-lock.json SHA-256 完全一致且源 node_modules/.bin 存在；
#        symlink 绝不可 stage/commit；不满足契约 → 不装、不崩，只提示 npm ci（fail-soft）。
#
# 全程 fail-soft：任何一步不满足条件 → 警告并跳过，exit 0，绝不挡 worktree 创建。
#
# 用法：
#   worktree-post-create.sh <src-checkout> <new-worktree>
# 调用方：multi-model-switch/scripts/start_issue_worktree.sh（工具创建路径）；
#         站点仓 scripts/worktree-new.sh（手动创建路径，如 ptc-ai-salary2）。
set -uo pipefail   # 故意不用 -e:fail-soft 语义自己控制

SRC="${1:-}"; DST="${2:-}"
if [ -z "$SRC" ] || [ -z "$DST" ] || [ ! -d "$DST" ]; then
	echo "usage: $0 <src-checkout> <new-worktree>" >&2
	exit 2
fi

say() { printf '%s\n' "$*"; }
warn() { printf '⚠️  %s\n' "$*" >&2; }

# ── 件B:node_modules symlink（契约：lockfile SHA 一致 + 源 .bin 在）────────────
if [ -e "$DST/node_modules" ] || [ -L "$DST/node_modules" ]; then
	say "✓ node_modules 已存在,跳过复用"
elif [ -f "$SRC/package-lock.json" ] && [ -f "$DST/package-lock.json" ] && \
     [ "$(shasum -a 256 "$SRC/package-lock.json" | cut -d' ' -f1)" = \
       "$(shasum -a 256 "$DST/package-lock.json" | cut -d' ' -f1)" ] && \
     [ -d "$SRC/node_modules/.bin" ]; then
	ln -s "$SRC/node_modules" "$DST/node_modules"
	say "✓ node_modules symlink → $SRC/node_modules（lockfile SHA 一致;绝不可 stage/commit 该 symlink）"
	if git -C "$DST" status --porcelain 2>/dev/null | grep -q "node_modules"; then
		warn "node_modules 出现在 git status——目标仓 .gitignore 需加 /node_modules（无尾斜杠,否则 symlink 不被忽略）"
	fi
else
	warn "node_modules 未复用（lockfile 不一致/源 .bin 缺失/无 lockfile）——首次 build 前: cd $DST && npm ci"
fi

# ── 件A:hook 兜底（`.husky/_` 已入仓的仓直接跳过;未入仓的仓 prepare 重建）───────
if [ -f "$DST/.husky/_/pre-commit" ]; then
	say "✓ hooks 就绪（.husky/_ 随仓继承,TB-09.1 主解法）"
elif [ -f "$DST/.husky/pre-commit" ] || [ -f "$DST/package.json" ]; then
	if [ -x "$DST/node_modules/.bin/husky" ] || [ -f "$DST/node_modules/husky/package.json" ]; then
		if (cd "$DST" && npm run prepare >/dev/null 2>&1) && [ -f "$DST/.husky/_/pre-commit" ]; then
			say "✓ hooks 就绪（prepare 兜底重建 .husky/_）"
		else
			warn ".husky/_ 缺失且 prepare 未能重建——commit 将无钩子静默跳过（TB-08 0fd775b 实证）;建议把 .husky/_ 入仓"
		fi
	else
		warn "无 node_modules 无法 prepare——hooks 未装;npm ci 后补 npm run prepare,或把 .husky/_ 入仓（推荐）"
	fi
else
	say "✓ 非 husky 仓,无 hooks 需要装"
fi

exit 0
