#!/bin/bash
# MMS + Hive compact hook — 自动保存 Hive restore 文件
# 用法：在 settings.json 中配置 PreCompact/PostCompact hook

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HIVE_HOME="$REPO_ROOT/hive"
HOOK_SCRIPT="$HIVE_HOME/dist/bin/hive-claude-compact-hook.js"

# 如果当前 main 构建产物不存在，静默退出（fail open）
[ ! -f "$HOOK_SCRIPT" ] && exit 0

# 读取 stdin 的 JSON 输入
INPUT=$(cat)
[ -z "$INPUT" ] && exit 0

# 调用 hook
node "$HOOK_SCRIPT" <<< "$INPUT"

exit 0
