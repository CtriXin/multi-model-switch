#!/bin/bash
# MMS 一键安装脚本
# 用法: curl -fsSL <url>/install.sh | bash
#   或: bash install.sh [--write-shell-rc] [--run-setup] [--ensure-node22] [--launch-after-install]
#   或: bash install.sh --ref v1.2.0

set -e
set -o pipefail

REPO_OWNER="CtriXin"
REPO_NAME="multi-model-switch"
SCRIPT_SOURCE_PATH="${BASH_SOURCE[0]:-}"
SCRIPT_DIR=""
case "$SCRIPT_SOURCE_PATH" in
    ""|stdin|/dev/fd/*|/proc/*/fd/*)
        SCRIPT_DIR=""
        ;;
    *)
        if [ -f "$SCRIPT_SOURCE_PATH" ]; then
            SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE_PATH")" 2>/dev/null && pwd 2>/dev/null || echo "")"
        fi
        ;;
esac
SOURCE_DIR=""
SOURCE_TMP_DIR=""
INSTALL_REF=""
RESOLVED_INSTALL_REF=""
INSTALL_CHANNEL="latest-tag"
LATEST_TAG_CACHE=""
LATEST_RELEASE_TAG_CACHE=""
DEFAULT_INSTALL_FALLBACK_TAG="${MMS_INSTALL_FALLBACK_TAG:-v3.0.1}"
BRAINKEEPER_DEFAULT_REF="${BRAINKEEPER_DEFAULT_REF:-${MINDKEEPER_DEFAULT_REF:-v2.4.1}}"
BRAINKEEPER_INSTALL_REF="${BRAINKEEPER_INSTALL_REF:-${MINDKEEPER_INSTALL_REF:-}}"
# Legacy env names remain accepted by installer aliases and downstream scripts.
MINDKEEPER_DEFAULT_REF="$BRAINKEEPER_DEFAULT_REF"
MINDKEEPER_INSTALL_REF="$BRAINKEEPER_INSTALL_REF"
MAP_DEFAULT_REF="${MAP_DEFAULT_REF:-v0.3.1}"
MAP_INSTALL_REF="${MAP_INSTALL_REF:-}"
CODEGRAPH_PACKAGE_SPEC="${CODEGRAPH_PACKAGE_SPEC:-@colbymchenry/codegraph@latest}"
CLAUDE_CLI_PACKAGE_SPEC="${CLAUDE_CLI_PACKAGE_SPEC:-@anthropic-ai/claude-code@latest}"
CODEX_CLI_PACKAGE_SPEC="${CODEX_CLI_PACKAGE_SPEC:-@openai/codex@latest}"
OPENCODE_CLI_PACKAGE_SPEC="${OPENCODE_CLI_PACKAGE_SPEC:-opencode-ai@latest}"
ECC_REPO_URL="${ECC_REPO_URL:-https://github.com/affaan-m/everything-claude-code}"
ECC_INSTALL_REF="${ECC_INSTALL_REF:-}"
OMC_REPO_URL="${OMC_REPO_URL:-https://github.com/Yeachan-Heo/oh-my-claudecode}"
OMC_INSTALL_REF="${OMC_INSTALL_REF:-}"
NVM_INSTALL_VERSION="${NVM_INSTALL_VERSION:-v0.40.3}"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11
BOOTSTRAP_PYTHON_VERSION="${MMS_BOOTSTRAP_PYTHON_VERSION:-3.13}"
PYTHON_CMD="${MMS_INSTALL_PYTHON:-${MMS_PYTHON:-}}"
INSTALL_LANG="zh"
INSTALL_LANG_EXPLICIT=0
WRITE_SHELL_RC=0
RUN_SETUP=0
ENSURE_NODE22=0
LAUNCH_AFTER_INSTALL=0
INSTALL_RTK=0
INSTALL_RTK_EXPLICIT=0
INSTALL_BRAINKEEPER_CONTEXT=0
INSTALL_BRAINKEEPER_CONTEXT_EXPLICIT=0
INSTALL_MAP=0
INSTALL_MAP_EXPLICIT=0
INSTALL_CODEGRAPH=0
INSTALL_CODEGRAPH_EXPLICIT=0
INSTALL_READ_ONCE=0
INSTALL_READ_ONCE_EXPLICIT=0
INSTALL_OPS_ENV_SAFE=0
INSTALL_OPS_ENV_SAFE_EXPLICIT=0
INSTALL_TOKEN_SAVER=0
INSTALL_TOKEN_SAVER_EXPLICIT=0
INSTALL_TOON=0
INSTALL_TOON_EXPLICIT=0
INSTALL_ECC=0
INSTALL_ECC_EXPLICIT=0
INSTALL_OMC=0
INSTALL_OMC_EXPLICIT=0
INSTALL_CLI_LIST=""
INSTALL_CLI_EXPLICIT=0
CHECK_ONLY=0
PRINT_ONLY_VERSION=0

REAL_HOME_CANDIDATE="${REAL_HOME:-${MMS_REAL_HOME:-${ORIGINAL_HOME:-}}}"
REAL_HOME="${REAL_HOME_CANDIDATE:-$HOME}"
if [[ "$REAL_HOME" == */.config/mms/* ]]; then
    REAL_HOME="${REAL_HOME%%/.config/mms/*}"
fi
if [ -z "$REAL_HOME_CANDIDATE" ] && [[ "$HOME" == */.config/mms/* ]]; then
    REAL_HOME="${HOME%%/.config/mms/*}"
fi

MMS_HOME="$REAL_HOME/.mms"
BIN_DIR="$REAL_HOME/.local/bin"
VENV_DIR="$MMS_HOME/.venv"
MMS_UV_BIN_DIR="$MMS_HOME/bin"
MMS_UV_BIN="$MMS_UV_BIN_DIR/uv"
MMS_UV_PYTHON_DIR="$MMS_HOME/uv-python/install"
MMS_UV_PYTHON_BIN_DIR="$MMS_HOME/uv-python/bin"
MMS_UV_CACHE_DIR="$MMS_HOME/uv-cache"
CREDENTIALS_PATH="$REAL_HOME/.config/mms/credentials.sh"
CONFIG_PATH="$REAL_HOME/.config/mms/config.toml"
VERSION_META_PATH="$REAL_HOME/.config/mms/version.json"

cleanup() {
    if [ -n "$SOURCE_TMP_DIR" ] && [ -d "$SOURCE_TMP_DIR" ]; then
        rm -rf "$SOURCE_TMP_DIR"
    fi
}

trap cleanup EXIT

t() {
    local zh="$1"
    local en="$2"
    if [ "$INSTALL_LANG" = "en" ]; then
        printf "%s" "$en"
    else
        printf "%s" "$zh"
    fi
}

normalize_install_ref() {
    local ref="$1"
    ref="${ref#refs/tags/}"
    ref="${ref#refs/heads/}"
    ref="${ref%^{\}}"
    printf "%s" "$ref"
}

is_local_source_install() {
    [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/install.sh" ] && [ -f "$SCRIPT_DIR/mms_core.py" ]
}

resolve_local_source_ref() {
    if ! is_local_source_install; then
        return 1
    fi
    if command -v git >/dev/null 2>&1 && git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git -C "$SCRIPT_DIR" describe --tags --always --dirty 2>/dev/null || true
        return 0
    fi
    echo "local-source"
}

ensure_install_ref_resolved() {
    if is_local_source_install; then
        INSTALL_CHANNEL="local-source"
        RESOLVED_INSTALL_REF="$(resolve_local_source_ref || true)"
        RESOLVED_INSTALL_REF="${RESOLVED_INSTALL_REF:-local-source}"
        return
    fi
    if [ -z "$RESOLVED_INSTALL_REF" ]; then
        resolve_requested_ref
    fi
}

optional_rtk_installed() {
    [ -x "$REAL_HOME/.claude/hooks/rtk-rewrite.sh" ]
}

optional_brainkeeper_context_installed() {
    [ -f "$REAL_HOME/.claude/commands/distill.md" ] \
        && [ -f "$REAL_HOME/.claude/commands/cz.md" ] \
        && [ -x "$REAL_HOME/.claude/hooks/token-monitor-hook.sh" ] \
        && [ -x "$BIN_DIR/bk" ] \
        && [ -x "$BIN_DIR/brainkeeper" ]
}

optional_map_installed() {
    [ -x "$REAL_HOME/.claude/hooks/map-auto-index.sh" ]
}

optional_codegraph_installed() {
    find_cli_binary codegraph >/dev/null 2>&1
}

optional_read_once_installed() {
    [ -x "$REAL_HOME/.claude/read-once/hook.sh" ] \
        && [ -x "$REAL_HOME/.claude/read-once/compact.sh" ]
}

optional_ops_env_safe_installed() {
    [ -f "$REAL_HOME/.codex/skills/ops-env-safe/SKILL.md" ] \
        && [ -f "$REAL_HOME/.claude/commands/ops-env-safe.md" ]
}

optional_token_saver_installed() {
    [ -f "$REAL_HOME/.codex/skills/token-saver/SKILL.md" ] \
        && [ -f "$REAL_HOME/.claude/skills/token-saver/SKILL.md" ] \
        && [ -x "$BIN_DIR/token-saver" ]
}

optional_toon_installed() {
    [ -f "$REAL_HOME/.codex/skills/toon/SKILL.md" ] \
        && [ -f "$REAL_HOME/.claude/skills/toon/SKILL.md" ] \
        && [ -x "$BIN_DIR/mms-toon" ]
}

optional_ecc_installed() {
    local pack_dir="$MMS_HOME/agent-packs/everything-claude-code"
    [ -f "$pack_dir/hooks/hooks.json" ] \
        && [ -d "$pack_dir/commands" ] \
        && [ -d "$pack_dir/skills" ]
}

optional_omc_installed() {
    local pack_dir="$MMS_HOME/agent-packs/oh-my-claudecode"
    [ -f "$pack_dir/hooks/hooks.json" ] \
        && [ -d "$pack_dir/skills" ] \
        && [ -f "$pack_dir/.claude-plugin/plugin.json" ]
}

note_optional_pack_detected() {
    local zh_label="$1"
    local en_label="$2"
    if [ "$INSTALL_LANG" = "en" ]; then
        echo "  ✓ Detected existing ${en_label}; keeping current setup (pass the explicit install flag to reinstall)"
    else
        echo "  ✓ 已检测到现有${zh_label}，保留当前配置（如需重装请显式传对应 --install-* 参数）"
    fi
}

can_prompt_interactively() {
    [ -r /dev/tty ] && [ -w /dev/tty ] || return 1
    { : < /dev/tty > /dev/tty; } 2>/dev/null
}

read_from_tty() {
    local prompt="$1"
    local value=""

    if ! can_prompt_interactively; then
        return 1
    fi

    printf "%s" "$prompt" > /dev/tty
    IFS= read -r value < /dev/tty || return 1
    printf "%s" "$value"
}

confirm_from_tty() {
    local prompt="$1"
    local default_value="$2"
    local answer=""
    local normalized=""

    answer="$(read_from_tty "$prompt")" || return 1
    normalized="$(printf "%s" "$answer" | tr '[:upper:]' '[:lower:]' | xargs)"
    if [ -z "$normalized" ]; then
        normalized="$default_value"
    fi
    case "$normalized" in
        y|yes)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

fetch_url_stdout() {
    local url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl --retry 3 --retry-delay 2 --connect-timeout 10 -fsSL "$url"
        return $?
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -qO- "$url"
        return $?
    fi
    return 1
}

download_url_to_file() {
    local url="$1"
    local output="$2"
    if command -v curl >/dev/null 2>&1; then
        curl --retry 3 --retry-delay 2 --connect-timeout 10 -fsSL "$url" -o "$output"
        return $?
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -qO "$output" "$url"
        return $?
    fi
    return 1
}

usage() {
    cat <<EOF
$(t "用法:" "Usage:")
  bash install.sh [--write-shell-rc] [--run-setup] [--ensure-node22] [--launch-after-install] [--lang zh|en] [--install-brainkeeper-context] [--brainkeeper-ref <tag-or-branch>] [--install-map] [--map-ref <tag-or-branch>] [--install-codegraph] [--codegraph-package <npm-spec>] [--install-read-once] [--install-token-saver] [--install-toon] [--install-ops-env-safe] [--install-ecc] [--ecc-ref <tag-or-branch>] [--install-omc] [--omc-ref <tag-or-branch>] [--install-agent-packs] [--install-cli name[,name2]]
  bash install.sh --ref <tag-or-branch>
  bash install.sh --main
  bash install.sh --latest-tag
  bash install.sh --latest-release
  bash install.sh --version
  bash install.sh --check

$(t "说明:" "Notes:")
  - $(t "默认远程安装/升级使用最新 semver tag" "By default, remote install/upgrade uses the latest semver tag")
  - $(t "--ref 可指定版本号或分支，例如 v1.2.0 / main" "--ref can pin a specific version or branch, for example v1.2.0 / main")
  - $(t "--version 仅显示当前脚本将安装的版本，不执行安装" "--version prints the version/ref this script would install without installing")
  - $(t "--check 仅检查当前环境与已安装状态，不执行安装" "--check inspects the current environment and installed state without installing")
  - $(t "--lang 可设置默认 UI 语言（zh / en）" "--lang sets the default UI language (zh / en)")
  - $(t "--install-rtk 会额外安装 jq + rtk，并把 Claude 的 RTK rewrite hook 配好" "--install-rtk installs jq + rtk and enables the Claude RTK rewrite hook")
  - $(t "--install-brainkeeper-context 会全量安装/更新 BrainKeeper context pack：BrainKeeper MCP、Claude 的 /distill /cz /cr、token hooks、bk/brainkeeper 命令；默认锁定到经过 MMS 验证的 BrainKeeper tag" "--install-brainkeeper-context installs/updates the full BrainKeeper context pack: BrainKeeper MCP, Claude /distill /cz /cr commands, token hooks, and bk/brainkeeper commands; by default it pins the MMS-tested BrainKeeper tag")
  - $(t "--brainkeeper-ref 可覆盖 BrainKeeper 安装版本，例如 v2.4.1 / main" "--brainkeeper-ref overrides the BrainKeeper install ref, for example v2.4.1 / main")
  - $(t "旧参数 --install-mindkeeper-context / --mindkeeper-ref 仍兼容，但已 deprecated" "Legacy --install-mindkeeper-context / --mindkeeper-ref remain compatible but are deprecated")
  - $(t "--install-map 会安装项目结构地图 Map，并启用 Claude 的 SessionStart auto-index hook；默认锁定到经过 MMS 验证的 Map release" "--install-map installs the project-structure Map and enables the Claude SessionStart auto-index hook; by default it pins the MMS-tested Map release")
  - $(t "--map-ref 可覆盖 Map 安装版本，例如 v0.3.1 / main" "--map-ref overrides the Map version, for example v0.3.1 / main")
  - $(t "--install-codegraph 会通过 npm 安装 CodeGraph CLI/MCP，用于 symbol/call graph 代码索引；MMS session hook 会在 git repo 中自动 init/index，已有索引则 sync" "--install-codegraph installs the CodeGraph CLI/MCP via npm for symbol/call-graph code indexing; MMS session hooks auto init/index git repos and sync existing indexes")
  - $(t "--codegraph-package 可覆盖 npm 包规格，例如 @colbymchenry/codegraph@0.7.6" "--codegraph-package overrides the npm package spec, for example @colbymchenry/codegraph@0.7.6")
  - $(t "--install-read-once 会安装 read-once，并启用 Claude 的 Read 省 token hooks：同一 session 避免重复全文读文件，改动后优先提示 diff" "--install-read-once installs read-once and enables Claude Read token-saving hooks: avoid repeated full-file rereads in a session and prefer diffs after edits")
  - $(t "--install-token-saver 会安装 Codex/Claude 共用 token-saver skill 和本机 token-saver 命令，用于长日志/测试输出/diff 的 ref+snippet 收纳" "--install-token-saver installs the shared Codex/Claude token-saver skill plus the local token-saver command for long logs/test output/diff refs and snippets")
  - $(t "--install-toon 会安装 Codex/Claude 共用 TOON skill 和本机 mms-toon 命令，用于结构化 JSON/status/handoff 压缩；MMS session 内仍默认内建 TOON" "--install-toon installs the shared Codex/Claude TOON skill plus the local mms-toon command for structured JSON/status/handoff compression; MMS sessions still bundle TOON by default")
  - $(t "--install-ops-env-safe 是高级可选项：安装 path-only host path hints；普通 MMS session 已自动带真实 HOME 路径提示，通常不用安装" "--install-ops-env-safe is advanced-only: installs path-only host path hints; normal MMS sessions already receive real-HOME path hints and usually do not need it")
  - $(t "--install-ecc / --install-omc 会把 Claude agent packs 安装为 MMS-managed session assets，不写全局 Claude 配置" "--install-ecc / --install-omc installs Claude agent packs as MMS-managed session assets without writing global Claude config")
  - $(t "--install-agent-packs 等同于同时安装 ECC 和 OMC；可用 --ecc-ref / --omc-ref 固定版本" "--install-agent-packs installs both ECC and OMC; use --ecc-ref / --omc-ref to pin refs")
  - $(t "Caveman、Web automation bundle（weber router + web-access 登录态 Chrome + agent-browser headless）、TOON、token-saver 作为 MMS 内建 session assets 随安装一起提供" "Caveman, the Web automation bundle (weber router + web-access logged-in Chrome + agent-browser headless), TOON, and token-saver ship as bundled MMS session assets")
  - $(t "--install-cli 可选安装 claude/codex/opencode（支持逗号分隔）；能用 npm 的 CLI 均走 npm package" "--install-cli optionally installs claude/codex/opencode (comma-separated); CLIs with npm packages are installed through npm")
  - $(t "--write-shell-rc 支持 bash/zsh/fish；Ghostty/iTerm/Terminal 重开 tab 后即可直接输入 mms" "--write-shell-rc supports bash/zsh/fish; reopen Ghostty/iTerm/Terminal tabs to type mms directly")
  - $(t "同一条命令可重复执行，用于升级" "The same command can be re-run later for upgrades")
EOF
}

append_csv_item() {
    local value="$1"
    if [ -z "$value" ]; then
        return
    fi
    case ",$INSTALL_CLI_LIST," in
        *,"$value",*)
            ;;
        *)
            if [ -n "$INSTALL_CLI_LIST" ]; then
                INSTALL_CLI_LIST="${INSTALL_CLI_LIST},$value"
            else
                INSTALL_CLI_LIST="$value"
            fi
            ;;
    esac
}

parse_install_cli_arg() {
    local raw="$1"
    local item=""
    local normalized=""

    if [ -z "$raw" ]; then
        echo "❌ $(t "--install-cli 需要至少一个名称" "--install-cli requires at least one name")"
        usage
        exit 1
    fi

    IFS=',' read -r -a _install_items <<< "$raw"
    for item in "${_install_items[@]}"; do
        normalized="$(printf "%s" "$item" | tr '[:upper:]' '[:lower:]' | xargs)"
        if [ -z "$normalized" ]; then
            continue
        fi
        case "$normalized" in
            claude|codex|opencode)
                append_csv_item "$normalized"
                ;;
            *)
                echo "❌ $(t "不支持的 CLI 名称" "Unsupported CLI name"): $normalized"
                usage
                exit 1
                ;;
        esac
    done

    if [ -z "$INSTALL_CLI_LIST" ]; then
        echo "❌ $(t "--install-cli 未解析出有效 CLI 名称" "--install-cli did not resolve any valid CLI names")"
        usage
        exit 1
    fi
}

prompt_install_language() {
    local answer=""
    local normalized=""

    if [ "$INSTALL_LANG_EXPLICIT" -eq 1 ]; then
        return 0
    fi

    if ! can_prompt_interactively; then
        return 0
    fi

    echo ""
    echo "Language / 语言"
    echo "  1) 中文"
    echo "  2) English"
    answer="$(read_from_tty 'Choose UI language [1/2, default 1]: ')" || return 0
    normalized="$(printf "%s" "$answer" | tr '[:upper:]' '[:lower:]' | xargs)"

    case "$normalized" in
        2|en|english)
            INSTALL_LANG="en"
            ;;
        *)
            INSTALL_LANG="zh"
            ;;
    esac
}

prompt_optional_install_choices() {
    local cli_name=""
    local cli_command=""
    local cli_label=""
    local cli_path=""

    if ! can_prompt_interactively; then
        return 0
    fi

    if [ "$INSTALL_RTK_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_rtk_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional enhancement"
            else
                echo "可选增强"
            fi
            note_optional_pack_detected " RTK 改写" "RTK rewrite"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional enhancement"
            echo "  RTK rewrite reduces token-heavy Bash commands in Claude sessions."
            if confirm_from_tty "Install jq + rtk and enable Claude RTK rewrite hook? [y/N]: " "n"; then
                INSTALL_RTK=1
            fi
        else
            echo "可选增强"
            echo "  RTK rewrite 可以把 Claude 里的 Bash 命令改写成更省 token 的形式。"
            if confirm_from_tty "是否安装 jq + rtk 并启用 Claude RTK rewrite hook？[y/N]: " "n"; then
                INSTALL_RTK=1
            fi
        fi
    fi

    if [ "$INSTALL_BRAINKEEPER_CONTEXT_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_brainkeeper_context_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional context tools"
            else
                echo "可选上下文工具"
            fi
            note_optional_pack_detected " BrainKeeper 上下文包" "BrainKeeper context pack"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional context tools"
            echo "  Full BrainKeeper context pack: installs/updates the BrainKeeper repo into ~/.local/share/brainkeeper."
            echo "  Adds BrainKeeper MCP, Claude /distill /cz /cr, token hooks, and bk/brainkeeper commands."
            echo "  By default MMS pins BrainKeeper to ${BRAINKEEPER_INSTALL_REF:-$BRAINKEEPER_DEFAULT_REF}."
            if confirm_from_tty "Install BrainKeeper context pack for Claude? [y/N]: " "n"; then
                INSTALL_BRAINKEEPER_CONTEXT=1
            fi
        else
            echo "可选上下文工具"
            echo "  BrainKeeper 全量 context pack：会把 BrainKeeper 仓库安装/更新到 ~/.local/share/brainkeeper。"
            echo "  同时添加 BrainKeeper MCP、Claude /distill /cz /cr、token hooks，以及 bk/brainkeeper 命令。"
            echo "  默认会锁定到 ${BRAINKEEPER_INSTALL_REF:-$BRAINKEEPER_DEFAULT_REF}。"
            if confirm_from_tty "是否安装 BrainKeeper 上下文包（Claude）？[y/N]: " "n"; then
                INSTALL_BRAINKEEPER_CONTEXT=1
            fi
        fi
    fi

    if [ "$INSTALL_MAP_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_map_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional Claude hook"
            else
                echo "可选 Claude hook"
            fi
            note_optional_pack_detected " Map 自动索引" "Map auto-index"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional Claude hook"
            echo "  Map builds a lightweight project-structure map so Claude can orient in a repo faster."
            echo "  The SessionStart hook refreshes the structure index automatically."
            echo "  By default MMS reuses an existing Node.js 18+ runtime when available; otherwise Map is skipped unless you explicitly ask for --ensure-node22."
            if confirm_from_tty "Install Map plus the Claude SessionStart auto-index hook? [y/N]: " "n"; then
                INSTALL_MAP=1
            fi
        else
            echo "可选 Claude hook"
            echo "  Map 会建立轻量项目结构地图，让 Claude 更快理解 repo。"
            echo "  SessionStart hook 会在会话启动时自动刷新结构索引。"
            echo "  默认优先复用现有 Node.js 18+；如果没有合适版本，会先跳过 Map，除非你显式要求 --ensure-node22。"
            if confirm_from_tty "是否安装 Map 并启用 Claude 启动自动索引 hook？[y/N]: " "n"; then
                INSTALL_MAP=1
            fi
        fi
    fi

    if [ "$INSTALL_CODEGRAPH_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_codegraph_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional code intelligence"
            else
                echo "可选代码索引"
            fi
            note_optional_pack_detected " CodeGraph CLI" "CodeGraph CLI"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional code intelligence"
            echo "  CodeGraph installs a local CLI/MCP server for symbol search, callers/callees, and code context."
            echo "  MMS session hooks auto-register git repos with CodeGraph, then sync existing .codegraph/ indexes."
            echo "  It uses npm and may fall back to MMS-managed nvm Node.js 22 without changing your default Node."
            if confirm_from_tty "Install CodeGraph CLI? [y/N]: " "n"; then
                INSTALL_CODEGRAPH=1
            fi
        else
            echo "可选代码索引"
            echo "  CodeGraph 会安装本机 CLI/MCP server，用于 symbol search、callers/callees 和代码上下文检索。"
            echo "  MMS session hook 会自动为 git repo 注册 CodeGraph；已有 .codegraph/ 时只做 sync。"
            echo "  它使用 npm；必要时会临时用 MMS-managed nvm Node.js 22，不会修改你的默认 Node。"
            if confirm_from_tty "是否安装 CodeGraph CLI？[y/N]: " "n"; then
                INSTALL_CODEGRAPH=1
            fi
        fi
    fi

    if [ "$INSTALL_READ_ONCE_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_read_once_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional Claude hook"
            else
                echo "可选 Claude hook"
            fi
            note_optional_pack_detected " read-once" "read-once"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional Claude hook"
            echo "  Read token saver (read-once) avoids redundant full-file rereads and prefers diffs after edits."
            echo "  It works automatically for Claude Read; you do not need to remember a command."
            if confirm_from_tty "Install read-once for Claude Read token saving? [y/N]: " "n"; then
                INSTALL_READ_ONCE=1
            fi
        else
            echo "可选 Claude hook"
            echo "  Read 省 token 工具（read-once）会避免重复全文读取文件，并在改动后优先提供 diff。"
            echo "  它会自动作用于 Claude Read，不需要你记命令。"
            if confirm_from_tty "是否安装 Claude 的 read-once 读文件省 token hook？[y/N]: " "n"; then
                INSTALL_READ_ONCE=1
            fi
        fi
    fi

    if [ "$INSTALL_TOKEN_SAVER_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_token_saver_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional token saving"
            else
                echo "可选省 token 工具"
            fi
            note_optional_pack_detected " token-saver" "token-saver"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional token saving"
            echo "  Token Saver installs a shared Codex/Claude skill and local command for large-output refs/snippets."
            echo "  Use it for long logs, test output, broad rg, git diff/show, and noisy diagnostics."
            echo "  Agents use the low-level commands automatically; users can just say /token-saver or ask to save context."
            if confirm_from_tty "Install Token Saver for Codex and Claude? [y/N]: " "n"; then
                INSTALL_TOKEN_SAVER=1
            fi
        else
            echo "可选省 token 工具"
            echo "  Token Saver 会安装 Codex/Claude 共用 skill 和本机命令，用 ref/snippet 收纳长输出。"
            echo "  适合长日志、测试输出、大范围 rg、git diff/show 和 noisy diagnostics。"
            echo "  底层命令由 agent 自动使用；用户只需要说 /token-saver 或“省点 context”。"
            if confirm_from_tty "是否为 Codex 和 Claude 安装 Token Saver？[y/N]: " "n"; then
                INSTALL_TOKEN_SAVER=1
            fi
        fi
    fi

    if [ "$INSTALL_TOON_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_toon_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional structured context compression"
            else
                echo "可选结构化上下文压缩"
            fi
            note_optional_pack_detected " TOON" "TOON"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional structured context compression"
            echo "  TOON compresses structured JSON/status/handoff packets for model-to-model context."
            echo "  It installs a Codex/Claude skill plus the local mms-toon command for export-only sessions."
            echo "  Do not use it for prose, code, raw logs, secrets, or exact API JSON."
            echo "  MMS-launched sessions already receive TOON as a session-local built-in asset."
            if confirm_from_tty "Install global TOON skill and mms-toon command? [y/N]: " "n"; then
                INSTALL_TOON=1
            fi
        else
            echo "可选结构化上下文压缩"
            echo "  TOON 用来压缩结构化 JSON/status/handoff，方便模型之间传递上下文。"
            echo "  它会安装 Codex/Claude 共用 skill 和本机 mms-toon 命令，方便 export-only 会话使用。"
            echo "  不用于 prose、代码、原始日志、secret 或 CLI/API 要求精确的 JSON。"
            echo "  通过 MMS 启动的 session 已经默认内建 TOON session asset。"
            if confirm_from_tty "是否安装全局 TOON skill 和 mms-toon 命令？[y/N]: " "n"; then
                INSTALL_TOON=1
            fi
        fi
    fi

    if [ "$INSTALL_ECC_EXPLICIT" -eq 0 ] || [ "$INSTALL_OMC_EXPLICIT" -eq 0 ]; then
        local answer=""
        local normalized=""
        local ecc_ready=0
        local omc_ready=0

        optional_ecc_installed && ecc_ready=1 || true
        optional_omc_installed && omc_ready=1 || true

        echo ""
        if [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional Claude agent packs"
            [ "$ecc_ready" -eq 1 ] && note_optional_pack_detected " ECC" "ECC"
            [ "$omc_ready" -eq 1 ] && note_optional_pack_detected " OMC" "OMC"
            echo "  ECC: engineering workflow / rules / quality hooks."
            echo "  OMC: orchestration runtime / team / verify loop."
            echo "  These are installed under ~/.mms/agent-packs and stay disabled until selected in the launch confirm page."
            if [ "$ecc_ready" -eq 1 ] && [ "$omc_ready" -eq 1 ]; then
                :
            else
                answer="$(read_from_tty "Install Claude agent packs? [n/ecc/omc/both, default n]: ")" || answer="n"
            fi
        else
            echo "可选 Claude agent packs"
            [ "$ecc_ready" -eq 1 ] && note_optional_pack_detected " ECC" "ECC"
            [ "$omc_ready" -eq 1 ] && note_optional_pack_detected " OMC" "OMC"
            echo "  ECC：工程 workflow / rules / quality hooks。"
            echo "  OMC：orchestration runtime / team / verify loop。"
            echo "  它们会安装到 ~/.mms/agent-packs，默认不启用，只在启动确认页选择后注入 session。"
            if [ "$ecc_ready" -eq 1 ] && [ "$omc_ready" -eq 1 ]; then
                :
            else
                answer="$(read_from_tty "是否安装 Claude agent packs？[n/ecc/omc/both，默认 n]: ")" || answer="n"
            fi
        fi

        normalized="$(printf "%s" "$answer" | tr '[:upper:]' '[:lower:]' | xargs)"
        [ -z "$normalized" ] && normalized="n"
        case "$normalized" in
            e|ecc)
                if [ "$INSTALL_ECC_EXPLICIT" -eq 0 ] && [ "$ecc_ready" -eq 0 ]; then
                    INSTALL_ECC=1
                fi
                ;;
            o|omc)
                if [ "$INSTALL_OMC_EXPLICIT" -eq 0 ] && [ "$omc_ready" -eq 0 ]; then
                    INSTALL_OMC=1
                fi
                ;;
            b|both|all|agent-packs|agent_packs)
                if [ "$INSTALL_ECC_EXPLICIT" -eq 0 ] && [ "$ecc_ready" -eq 0 ]; then
                    INSTALL_ECC=1
                fi
                if [ "$INSTALL_OMC_EXPLICIT" -eq 0 ] && [ "$omc_ready" -eq 0 ]; then
                    INSTALL_OMC=1
                fi
                ;;
            *)
                :
                ;;
        esac
    fi

    echo ""
    if [ "$INSTALL_LANG" = "en" ]; then
        echo "Bundled session mode"
        echo "  Caveman, TOON, token-saver, and the Web automation bundle ship inside MMS as pinned session assets."
        echo "  Web automation bundle = weber router + web-access logged-in Chrome + agent-browser headless CLI."
        echo "  MMS-launched Claude/Codex can expose them per session without touching your global hooks or config."
    else
        echo "内建 session 模式"
        echo "  Caveman、TOON、token-saver 和 Web automation bundle 会随 MMS 一起作为内建 session 资产提供。"
        echo "  Web automation bundle = weber 路由器 + web-access 登录态 Chrome + agent-browser headless CLI。"
        echo "  通过 MMS 启动的 Claude/Codex 可按 session 暴露这些能力，不会改你的全局 hooks 或配置。"
    fi

    if [ "$INSTALL_CLI_EXPLICIT" -eq 1 ]; then
        return 0
    fi

    echo ""
    echo "$(t "可选 CLI 工具" "Optional CLI tools")"

    for cli_name in claude codex opencode; do
        case "$cli_name" in
            claude)
                cli_command="claude"
                cli_label="Claude Code"
                ;;
            codex)
                cli_command="codex"
                cli_label="Codex CLI"
                ;;
            opencode)
                cli_command="opencode"
                cli_label="OpenCode CLI"
                ;;
        esac

        if cli_path="$(find_cli_binary "$cli_command" 2>/dev/null)"; then
            echo "  ✓ $(t "已检测到" "Detected"): $cli_label ($cli_path)"
            continue
        fi

        if [ "$INSTALL_LANG" = "en" ]; then
            if confirm_from_tty "  ${cli_label} not found. Install now? [y/N]: " "n"; then
                append_csv_item "$cli_name"
            fi
        else
            if confirm_from_tty "  未检测到 ${cli_label}，现在安装吗？[y/N]: " "n"; then
                append_csv_item "$cli_name"
            fi
        fi
    done
}

resolve_latest_tag() {
    if [ -n "${MMS_INSTALL_LATEST_TAG_OVERRIDE:-}" ]; then
        normalize_install_ref "$MMS_INSTALL_LATEST_TAG_OVERRIDE"
        return 0
    fi
    if [ -n "$LATEST_TAG_CACHE" ]; then
        printf "%s" "$LATEST_TAG_CACHE"
        return 0
    fi
    local resolved_tag=""
    if command -v python3 >/dev/null 2>&1; then
        resolved_tag="$(python3 - <<'PY'
import json
import re
import sys
from urllib.request import Request, urlopen

url = "https://api.github.com/repos/CtriXin/multi-model-switch/tags?per_page=100"
req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "mms-install-script"})
try:
    with urlopen(req, timeout=15) as resp:
        data = json.load(resp)
except Exception:
    sys.exit(1)

if not isinstance(data, list):
    sys.exit(1)

semver = []
for item in data:
    if not isinstance(item, dict):
        continue
    tag = str(item.get("name") or "").strip()
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
    if not m:
        continue
    semver.append(((int(m.group(1)), int(m.group(2)), int(m.group(3))), tag))

if not semver:
    sys.exit(1)

semver.sort(reverse=True)
print(semver[0][1])
PY
)" || true
    fi
    if [ -z "$resolved_tag" ]; then
        resolved_tag="$(
            fetch_url_stdout "https://api.github.com/repos/CtriXin/multi-model-switch/tags?per_page=100" \
                | sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\(v[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)".*/\1/p' \
                | awk -F'[v.]' '{ printf "%09d %09d %09d %s\n", $2, $3, $4, $0 }' \
                | sort -r \
                | head -n 1 \
                | awk '{ print $4 }'
        )" || true
    fi
    if [ -z "$resolved_tag" ] && command -v git >/dev/null 2>&1; then
        resolved_tag="$(
            git ls-remote --tags "https://github.com/${REPO_OWNER}/${REPO_NAME}.git" 'v[0-9]*.[0-9]*.[0-9]*' 2>/dev/null \
                | sed 's#refs/tags/##; s#\^{}##' \
                | awk '{ print $2 }' \
                | sort -u \
                | awk -F'[v.]' '{ printf "%09d %09d %09d %s\n", $2, $3, $4, $0 }' \
                | sort -r \
                | head -n 1 \
                | awk '{ print $4 }'
        )" || true
    fi
    if [ -z "$resolved_tag" ] && [ -n "$DEFAULT_INSTALL_FALLBACK_TAG" ]; then
        resolved_tag="$DEFAULT_INSTALL_FALLBACK_TAG"
    fi
    resolved_tag="$(normalize_install_ref "$resolved_tag")"
    [ -n "$resolved_tag" ] || return 1
    LATEST_TAG_CACHE="$resolved_tag"
    printf "%s" "$resolved_tag"
}

resolve_latest_release_tag() {
    if [ -n "${MMS_INSTALL_LATEST_RELEASE_OVERRIDE:-}" ]; then
        normalize_install_ref "$MMS_INSTALL_LATEST_RELEASE_OVERRIDE"
        return 0
    fi
    if [ -n "$LATEST_RELEASE_TAG_CACHE" ]; then
        printf "%s" "$LATEST_RELEASE_TAG_CACHE"
        return 0
    fi
    local resolved_release_tag=""
    if command -v python3 >/dev/null 2>&1; then
        resolved_release_tag="$(python3 - <<'PY'
import json
import sys
from urllib.request import Request, urlopen

url = "https://api.github.com/repos/CtriXin/multi-model-switch/releases/latest"
req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "mms-install-script"})
try:
    with urlopen(req, timeout=15) as resp:
        data = json.load(resp)
except Exception:
    sys.exit(1)

tag = str(data.get("tag_name") or "").strip()
if not tag:
    sys.exit(1)
print(tag)
PY
)" || true
    fi
    if [ -z "$resolved_release_tag" ]; then
        resolved_release_tag="$(
            fetch_url_stdout "https://api.github.com/repos/CtriXin/multi-model-switch/releases/latest" \
                | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
                | head -n 1
        )" || true
    fi
    resolved_release_tag="$(normalize_install_ref "$resolved_release_tag")"
    [ -n "$resolved_release_tag" ] || return 1
    LATEST_RELEASE_TAG_CACHE="$resolved_release_tag"
    printf "%s" "$resolved_release_tag"
}

download_remote_source() {
    local ref="$1"
    local archive_url=""
    local tarball="$SOURCE_TMP_DIR/source.tar.gz"

    if [ -z "$ref" ]; then
        return 1
    fi
    ref="$(normalize_install_ref "$ref")"

    if [ "$ref" = "main" ]; then
        archive_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/main.tar.gz"
    else
        archive_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/tags/${ref}.tar.gz"
    fi

    echo "$(t "正在下载源码归档" "Downloading source archive"): $archive_url"
    if ! download_url_to_file "$archive_url" "$tarball"; then
        echo "❌ $(t "下载源码归档失败，请检查网络后重试；中国网络环境下建议稍后再试或改用 --ref main" "Failed to download the source archive. Please check your network and retry; in China, try again later or use --ref main")"
        return 1
    fi
    if ! tar -xzf "$tarball" -C "$SOURCE_TMP_DIR"; then
        echo "❌ $(t "源码归档解压失败，下载内容可能不完整" "Failed to extract the source archive; the download may be incomplete")"
        return 1
    fi

    SOURCE_DIR="$(find "$SOURCE_TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    if [ -z "$SOURCE_DIR" ] || [ ! -f "$SOURCE_DIR/mms_core.py" ]; then
        echo "❌ $(t "远程源码解压失败" "Failed to extract downloaded source archive")"
        return 1
    fi
    echo "✓ $(t "已获取源码" "Source prepared"): $SOURCE_DIR"
}

write_version_metadata() {
    ensure_install_ref_resolved
    mkdir -p "$(dirname "$VERSION_META_PATH")"
    "$(_python_bin)" - "$VERSION_META_PATH" "$RESOLVED_INSTALL_REF" "$INSTALL_CHANNEL" "$INSTALL_LANG" <<'PY'
import json
import re
import sys
from datetime import datetime, timezone

path, resolved_ref, install_channel, preferred_language = sys.argv[1:5]
resolved_ref = str(resolved_ref or "").strip()
installed_version = resolved_ref if re.fullmatch(r"v\d+\.\d+\.\d+", resolved_ref) else ""
preferred_language = "en" if str(preferred_language).strip().lower().startswith("en") else "zh"

payload = {
    "installed_ref": resolved_ref,
    "installed_version": installed_version,
    "install_channel": install_channel,
    "preferred_language": preferred_language,
    "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "source": "install.sh",
}

with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
    chmod 600 "$VERSION_META_PATH"
    if [ -n "$RESOLVED_INSTALL_REF" ]; then
        echo "✓ $(t "已记录安装版本" "Recorded installed version"): $RESOLVED_INSTALL_REF"
    fi
}

write_language_config() {
    mkdir -p "$(dirname "$CONFIG_PATH")"
    "$(_python_bin)" - "$CONFIG_PATH" "$INSTALL_LANG" <<'PY'
import os
import sys

config_path, preferred_language = sys.argv[1:3]
preferred_language = "en" if str(preferred_language).strip().lower().startswith("en") else "zh"

if not os.path.exists(config_path):
    sys.exit(0)

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import tomli_w
except ImportError:
    tomli_w = None

if tomli_w is None:
    sys.exit(0)

with open(config_path, "rb") as handle:
    data = tomllib.load(handle)

ui = data.get("ui")
if not isinstance(ui, dict):
    ui = {}
data["ui"] = ui
ui["language"] = preferred_language

with open(config_path, "wb") as handle:
    tomli_w.dump(data, handle)
PY
}

prepare_source_dir() {
    ensure_install_ref_resolved
    if is_local_source_install; then
        SOURCE_DIR="$SCRIPT_DIR"
        echo "✓ $(t "使用本地源码" "Using local source tree"): $SOURCE_DIR"
        return
    fi

    SOURCE_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mms-install.XXXXXX")"
    download_remote_source "$RESOLVED_INSTALL_REF"
}

resolve_requested_ref() {
    local ref="$INSTALL_REF"
    if [ -z "$ref" ] && [ "$INSTALL_CHANNEL" = "latest-release" ]; then
        ref="$(resolve_latest_release_tag || true)"
        if [ -n "$ref" ]; then
            echo "✓ latest release: $ref"
        else
            echo "⚠ $(t "获取 latest release 失败，回退到最新 tag" "Failed to fetch latest release, falling back to latest tag")"
            INSTALL_CHANNEL="latest-tag"
        fi
    fi
    if [ -z "$ref" ] && [ "$INSTALL_CHANNEL" = "latest-tag" ]; then
        ref="$(resolve_latest_tag || true)"
        if [ -n "$ref" ]; then
            echo "✓ latest tag: $ref"
        else
            echo "⚠ $(t "获取最新 tag 失败，回退到 main" "Failed to fetch latest tag, falling back to main")"
            ref="main"
        fi
    fi
    if [ -z "$ref" ]; then
        ref="main"
    fi
    ref="$(normalize_install_ref "$ref")"
    RESOLVED_INSTALL_REF="$ref"
}

detect_node_major() {
    if ! command -v node >/dev/null 2>&1; then
        return 1
    fi

    local version
    version="$(node --version 2>/dev/null || true)"
    version="${version#v}"
    echo "${version%%.*}"
}

node_version_label() {
    if ! command -v node >/dev/null 2>&1; then
        return 1
    fi
    node --version 2>/dev/null || true
}

find_cli_binary() {
    local command_name="$1"
    local candidate=""
    local dir=""

    if [ -z "$command_name" ]; then
        return 1
    fi

    candidate="$(command -v "$command_name" 2>/dev/null || true)"
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        printf "%s\n" "$candidate"
        return 0
    fi

    for dir in \
        "$BIN_DIR" \
        "/opt/homebrew/bin" \
        "/usr/local/bin" \
        "$REAL_HOME/.npm-global/bin" \
        "$REAL_HOME/.bun/bin" \
        "$REAL_HOME/.cargo/bin" \
        "$REAL_HOME/.nvm/versions/node/"*/bin \
        "/usr/bin" \
        "/bin"; do
        [ -d "$dir" ] || continue
        candidate="$dir/$command_name"
        if [ -x "$candidate" ]; then
            printf "%s\n" "$candidate"
            return 0
        fi
    done

    return 1
}

shell_name() {
    basename "${SHELL:-}" 2>/dev/null || true
}

write_posix_path_rc() {
    local target="$1"
    local marker="# Added by MMS"
    local path_line='export PATH="$HOME/.local/bin:$PATH"'

    [ -n "$target" ] || return 1
    mkdir -p "$(dirname "$target")"
    touch "$target"
    if ! grep -q "$marker" "$target" 2>/dev/null; then
        {
            echo ""
            echo "$marker"
            echo "$path_line"
        } >> "$target"
        echo "✓ PATH $(t "已写入" "written to") $target"
    fi
}

write_fish_path_rc() {
    local target="$REAL_HOME/.config/fish/conf.d/mms.fish"
    local marker="# Added by MMS"
    local path_line='fish_add_path -g "$HOME/.local/bin"'

    mkdir -p "$(dirname "$target")"
    if ! grep -q "$marker" "$target" 2>/dev/null; then
        {
            echo "$marker"
            echo "$path_line"
        } >> "$target"
        echo "✓ PATH $(t "已写入" "written to") $target"
    fi
}

write_shell_path_config() {
    local shell_base=""
    shell_base="$(shell_name)"

    case "$shell_base" in
        fish)
            write_fish_path_rc
            ;;
        zsh)
            write_posix_path_rc "$REAL_HOME/.zshrc"
            ;;
        bash)
            write_posix_path_rc "$REAL_HOME/.bashrc"
            if [ "$(uname -s 2>/dev/null || true)" = "Darwin" ]; then
                write_posix_path_rc "$REAL_HOME/.bash_profile"
            fi
            ;;
        *)
            if [ -f "$REAL_HOME/.zshrc" ]; then
                write_posix_path_rc "$REAL_HOME/.zshrc"
            elif [ -f "$REAL_HOME/.bashrc" ]; then
                write_posix_path_rc "$REAL_HOME/.bashrc"
            elif [ -d "$REAL_HOME/.config/fish" ]; then
                write_fish_path_rc
            else
                write_posix_path_rc "$REAL_HOME/.profile"
            fi
            ;;
    esac
}

print_path_setup_hint() {
    local shell_base=""
    shell_base="$(shell_name)"

    echo "⚠ $(t "未修改你的 shell 配置。" "Your shell config was not modified.")"
    echo "  $(t "当前 shell 里可直接运行绝对路径:" "You can run the absolute path now:")"
    echo "    $BIN_DIR/mms"
    echo "  $(t "如需以后直接输入 mms，请添加 PATH:" "To type mms directly later, add PATH:")"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "  fish:"
    echo "    mkdir -p ~/.config/fish/conf.d"
    echo "    echo 'fish_add_path -g \"\$HOME/.local/bin\"' > ~/.config/fish/conf.d/mms.fish"
    echo "  $(t "或重新执行:" "Or rerun:") bash install.sh --write-shell-rc"
    echo "  $(t "Ghostty/iTerm/Terminal 只需重开 tab，或执行 exec \$SHELL -l。" "Ghostty/iTerm/Terminal: reopen the tab, or run exec \$SHELL -l.")"
}

node_meets_min_major() {
    local required_major="$1"
    local current_major
    current_major="$(detect_node_major || true)"
    if [[ -n "$current_major" ]] && [[ "$current_major" -ge "$required_major" ]]; then
        return 0
    fi
    return 1
}

ensure_node22() {
    local major
    major="$(detect_node_major || true)"
    if [[ -n "$major" ]] && [[ "$major" -ge 22 ]]; then
        echo "✓ Node.js: v$(node --version | sed 's/^v//')"
        return
    fi

    echo ""
    echo "$(t "未检测到可直接复用的 Node.js 22，开始准备 Node.js 22（通过 nvm）..." "No reusable Node.js 22 detected; preparing Node.js 22 (via nvm)...")"
    echo "  $(t "只影响本次安装和 MMS CLI 发现；不会改默认 Node，也不会写 shell rc。" "Only affects this install and MMS CLI discovery; no default Node switch and no shell rc writes.")"
    export NVM_DIR="$REAL_HOME/.nvm"

    if [ -s "$NVM_DIR/nvm.sh" ]; then
        # shellcheck disable=SC1090
        . "$NVM_DIR/nvm.sh"
        if [ "$(nvm version 22)" != "N/A" ]; then
            nvm use 22 >/dev/null
            echo "✓ $(t "检测到 nvm 已安装；仅本次安装进程使用，不修改默认 Node" "Detected existing nvm Node.js installation; using it for this install only, default Node unchanged"): $(node --version)"
            return
        fi
    else
        echo "$(t "未检测到 nvm，开始安装..." "nvm not found, installing...")"
        fetch_url_stdout "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_INSTALL_VERSION}/install.sh" | PROFILE=/dev/null METHOD=script bash
    fi

    # shellcheck disable=SC1090
    . "$NVM_DIR/nvm.sh"
    nvm install 22
    nvm use 22 >/dev/null
    echo "✓ $(t "Node.js 已切换到本次安装进程" "Node.js switched for this install process") $(node --version)"
}

ensure_nvm_node22() {
    export NVM_DIR="$REAL_HOME/.nvm"

    if [ ! -s "$NVM_DIR/nvm.sh" ]; then
        echo "$(t "未检测到 nvm，开始安装..." "nvm not found, installing...")"
        fetch_url_stdout "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_INSTALL_VERSION}/install.sh" | PROFILE=/dev/null METHOD=script bash
    fi

    # shellcheck disable=SC1090
    . "$NVM_DIR/nvm.sh"
    nvm install 22
    nvm use 22 >/dev/null
    echo "✓ $(t "Node.js 已切换到本次安装进程" "Node.js switched for this install process") $(node --version)"
}

run_optional_command() {
    local label="$1"
    local status=0
    local rendered_cmd=""

    shift

    if [ "$#" -eq 0 ]; then
        echo "⚠ $(t "缺少可执行命令，跳过" "Missing command, skipping"): $label"
        return 1
    fi

    printf -v rendered_cmd '%q ' "$@"
    rendered_cmd="${rendered_cmd% }"

    echo ""
    echo "→ $(t "正在处理" "Processing") $label"
    echo "  $rendered_cmd"

    set +e
    "$@"
    status=$?
    set -e

    if [ "$status" -eq 0 ]; then
        echo "✓ $label"
        return 0
    fi

    echo "⚠ $(t "可选安装失败" "Optional install failed"): $label (exit $status)"
    return "$status"
}

ensure_brew_package() {
    local command_name="$1"
    local package_name="$2"
    local label="$3"

    if command -v "$command_name" >/dev/null 2>&1; then
        echo "✓ $label"
        return 0
    fi

    if ! command -v brew >/dev/null 2>&1; then
        echo "⚠ $(t "未检测到 Homebrew，跳过可选安装" "Homebrew not found, skipping optional install"): $label"
        return 1
    fi

    run_optional_command "$label" brew install "$package_name"
}

npm_global_install_with_nvm_fallback() {
    local label="$1"
    local package_name="$2"

    if command -v npm >/dev/null 2>&1; then
        if run_optional_command "$label" npm install -g "$package_name"; then
            return 0
        fi
    fi

    echo "⚠ $(t "npm 全局安装失败或不可用，尝试 MMS-managed nvm Node.js 22 fallback。" "npm global install failed or is unavailable; trying MMS-managed nvm Node.js 22 fallback.")"
    ensure_nvm_node22 || return 1
    run_optional_command "$label (nvm)" npm install -g "$package_name"
}

ensure_node18_npm_for_optional_pack() {
    local label="$1"

    if node_meets_min_major 18 && command -v npm >/dev/null 2>&1; then
        echo "✓ $label Node.js: $(node_version_label || true)"
        return 0
    fi

    echo "⚠ $(t "缺少 Node.js 18+/npm，尝试 MMS-managed nvm Node.js 22 fallback。" "Node.js 18+/npm is missing; trying MMS-managed nvm Node.js 22 fallback."): $label"
    ensure_nvm_node22 || return 1

    if node_meets_min_major 18 && command -v npm >/dev/null 2>&1; then
        echo "✓ $label Node.js: $(node_version_label || true)"
        return 0
    fi

    echo "⚠ $(t "仍未检测到可用 Node.js 18+/npm，跳过" "Still no usable Node.js 18+/npm detected, skipping"): $label"
    return 1
}

brainkeeper_node_command() {
    local candidate=""
    local path_node=""

    path_node="$(command -v node 2>/dev/null || true)"
    for candidate in \
        "$REAL_HOME/.nvm/versions/node/"*/bin/node \
        "/opt/homebrew/bin/node" \
        "/usr/local/bin/node" \
        "/usr/bin/node" \
        "$path_node"; do
        [ -n "$candidate" ] || continue
        [ -x "$candidate" ] || continue
        if "$candidate" -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)' >/dev/null 2>&1; then
            printf "%s\n" "$candidate"
            return 0
        fi
    done

    return 1
}

install_named_cli() {
    local cli_name="$1"
    local cli_path=""
    local command_name=""
    local label=""
    local package_spec=""

    case "$cli_name" in
        claude)
            command_name="claude"
            label="Claude Code"
            package_spec="$CLAUDE_CLI_PACKAGE_SPEC"
            ;;
        codex)
            command_name="codex"
            label="Codex CLI"
            package_spec="$CODEX_CLI_PACKAGE_SPEC"
            ;;
        opencode)
            command_name="opencode"
            label="OpenCode CLI"
            package_spec="$OPENCODE_CLI_PACKAGE_SPEC"
            ;;
        *)
            echo "⚠ $(t "未知 CLI，跳过" "Unknown CLI, skipping"): $cli_name"
            return 1
            ;;
    esac

    if cli_path="$(find_cli_binary "$command_name" 2>/dev/null)"; then
        echo "✓ $label ($cli_path)"
        return 0
    fi

    npm_global_install_with_nvm_fallback "$label" "$package_spec" || true
    if cli_path="$(find_cli_binary "$command_name" 2>/dev/null)"; then
        echo "✓ $label ($cli_path)"
        return 0
    fi

    echo "⚠ $(t "$label 安装未完成；MMS 仍可安装，之后可重新运行 --install-cli $cli_name。" "$label install did not complete; MMS is still installed, rerun --install-cli $cli_name later.")"
    return 1
}

install_requested_clis() {
    local cli_name=""

    if [ -z "$INSTALL_CLI_LIST" ]; then
        return 0
    fi

    echo ""
    echo "$(t "正在安装可选 CLI..." "Installing optional CLIs...")"

    IFS=',' read -r -a _requested_cli_items <<< "$INSTALL_CLI_LIST"
    for cli_name in "${_requested_cli_items[@]}"; do
        install_named_cli "$cli_name" || true
    done
}

append_claude_hook_command() {
    local settings_path="$1"
    local hook_event="$2"
    local matcher="$3"
    local command_to_add="$4"
    local py_output=""

    shift 4

    py_output="$("$(_python_bin)" - "$settings_path" "$hook_event" "$matcher" "$command_to_add" "$@" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

settings_path = Path(sys.argv[1])
hook_event = sys.argv[2]
matcher = sys.argv[3]
command_to_add = sys.argv[4]

def normalize(value):
    return " ".join(str(value or "").strip().split())

dedupe_commands = {normalize(command_to_add)}
dedupe_commands.update(normalize(value) for value in sys.argv[5:] if normalize(value))

settings_path.parent.mkdir(parents=True, exist_ok=True)
data = {}
backup_path = None

if settings_path.exists():
    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        backup_path = settings_path.with_name(
            f"{settings_path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(settings_path, backup_path)
        data = {}

hooks = data.get("hooks")
if not isinstance(hooks, dict):
    hooks = {}
data["hooks"] = hooks

entries = hooks.get(hook_event)
if not isinstance(entries, list):
    entries = []

exists = False
for entry in entries:
    if not isinstance(entry, dict):
        continue
    hook_items = entry.get("hooks")
    if not isinstance(hook_items, list):
        continue
    for hook in hook_items:
        if not isinstance(hook, dict):
            continue
        command = normalize(hook.get("command"))
        if command in dedupe_commands:
            exists = True
            break
    if exists:
        break

if not exists:
    entries.append(
        {
            "matcher": matcher,
            "hooks": [
                {
                    "type": "command",
                    "command": command_to_add,
                }
            ],
        }
    )

hooks[hook_event] = entries
settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if backup_path is not None:
    print(f"BACKUP:{backup_path}")
PY
)"

    if [ -n "$py_output" ]; then
        echo "$py_output" | while IFS= read -r line; do
            case "$line" in
                BACKUP:*)
                    echo "⚠ $(t "检测到损坏的 Claude settings，已备份" "Detected invalid Claude settings, backup created"): ${line#BACKUP:}"
                    ;;
            esac
        done
    fi

    return 0
}

merge_claude_settings_template() {
    local settings_path="$1"
    local template_path="$2"
    local py_output=""

    if [ ! -f "$template_path" ]; then
        echo "⚠ $(t "找不到 Claude settings 模板，跳过合并" "Claude settings template not found, skipping merge"): $template_path"
        return 1
    fi

    py_output="$("$(_python_bin)" - "$settings_path" "$template_path" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

settings_path = Path(sys.argv[1])
template_path = Path(sys.argv[2])


def normalize(value):
    return " ".join(str(value or "").strip().split())


def load_json(path):
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def ensure_backup(path):
    backup = path.with_name(f"{path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    return backup


def merge_command_groups(existing_groups, template_groups):
    groups = []
    if isinstance(existing_groups, list):
        groups.extend(existing_groups)
    if not isinstance(template_groups, list):
        return groups
    for template_group in template_groups:
        if not isinstance(template_group, dict):
            continue
        matcher = str(template_group.get("matcher") or "").strip()
        template_hooks = template_group.get("hooks")
        if not isinstance(template_hooks, list):
            continue
        target = None
        for group in groups:
            if not isinstance(group, dict):
                continue
            if str(group.get("matcher") or "").strip() == matcher:
                target = group
                break
        if target is None:
            target = {"matcher": matcher, "hooks": []}
            groups.append(target)
        hook_items = target.get("hooks")
        if not isinstance(hook_items, list):
            hook_items = []
            target["hooks"] = hook_items
        seen = {normalize(hook.get("command")) for hook in hook_items if isinstance(hook, dict)}
        for hook in template_hooks:
            if not isinstance(hook, dict):
                continue
            command = normalize(hook.get("command"))
            if not command or command in seen:
                continue
            hook_items.append(dict(hook))
            seen.add(command)
    return groups


settings_path.parent.mkdir(parents=True, exist_ok=True)
backup_path = None
try:
    data = load_json(settings_path)
except Exception:
    backup_path = ensure_backup(settings_path)
    data = {}

template = load_json(template_path)

for key in [
    "includeCoAuthoredBy",
    "skipDangerousModePermissionPrompt",
    "model",
    "promptSuggestionEnabled",
]:
    if key in template and key not in data:
        data[key] = template[key]

if isinstance(template.get("attribution"), dict) and not isinstance(data.get("attribution"), dict):
    data["attribution"] = dict(template["attribution"])

if isinstance(template.get("statusLine"), dict):
    status = dict(data.get("statusLine") or {})
    status.update(template["statusLine"])
    data["statusLine"] = status

if isinstance(template.get("permissions"), dict):
    permissions = dict(data.get("permissions") or {})
    for list_key in ["allow", "deny"]:
        values = []
        seen = set()
        for item in list(permissions.get(list_key) or []) + list(template["permissions"].get(list_key) or []):
            norm = str(item or "").strip()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            values.append(norm)
        permissions[list_key] = values
    if "defaultMode" in template["permissions"] and not permissions.get("defaultMode"):
        permissions["defaultMode"] = template["permissions"]["defaultMode"]
    data["permissions"] = permissions

hooks = data.get("hooks")
if not isinstance(hooks, dict):
    hooks = {}
for event_name, template_groups in (template.get("hooks") or {}).items():
    hooks[event_name] = merge_command_groups(hooks.get(event_name), template_groups)
data["hooks"] = hooks

settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if backup_path is not None:
    print(f"BACKUP:{backup_path}")
PY
)"

    if [ -n "$py_output" ]; then
        echo "$py_output" | while IFS= read -r line; do
            case "$line" in
                BACKUP:*)
                    echo "⚠ $(t "检测到损坏的 Claude settings，已备份" "Detected invalid Claude settings, backup created"): ${line#BACKUP:}"
                    ;;
            esac
        done
    fi

    echo "✓ $(t "已合并 Claude settings 模板" "Merged Claude settings template"): $settings_path"
    return 0
}

repair_managed_claude_settings() {
    local global_template_path="$SOURCE_DIR/claude-settings.global-template.json"
    local session_template_path="$SOURCE_DIR/claude-settings.template.json"
    local snapshot_path="${MMS_HOME:-$REAL_HOME/.mms}/state/claude-global-managed-snapshot.json"

    if [ -f "$global_template_path" ]; then
        merge_claude_settings_template "$REAL_HOME/.claude/settings.json" "$global_template_path" || true
        mkdir -p "$(dirname "$snapshot_path")"
        cp "$global_template_path" "$snapshot_path" 2>/dev/null || true
    fi
    if [ -f "$session_template_path" ]; then
        merge_claude_settings_template "$HOME/.claude/settings.json" "$session_template_path" || true
    fi
}

_python_bin() {
    if [ -n "$PYTHON_CMD" ]; then
        printf "%s\n" "$PYTHON_CMD"
    else
        printf "%s\n" "python3"
    fi
}

_python_candidate_works() {
    local candidate="$1"
    [ -n "$candidate" ] || return 1
    if [[ "$candidate" == */* ]]; then
        [ -x "$candidate" ] || return 1
    else
        command -v "$candidate" >/dev/null 2>&1 || return 1
    fi
    "$candidate" - "$MIN_PYTHON_MAJOR" "$MIN_PYTHON_MINOR" <<'PY' >/dev/null 2>&1
import sys
major = int(sys.argv[1])
minor = int(sys.argv[2])
raise SystemExit(0 if sys.version_info >= (major, minor) else 1)
PY
}

find_supported_python() {
    local candidate=""
    for candidate in \
        "$PYTHON_CMD" \
        "$MMS_UV_PYTHON_BIN_DIR/python$BOOTSTRAP_PYTHON_VERSION" \
        "$MMS_UV_PYTHON_BIN_DIR/python3" \
        python3.13 \
        python3.12 \
        python3.11 \
        /opt/homebrew/bin/python3.13 \
        /opt/homebrew/bin/python3.12 \
        /opt/homebrew/bin/python3.11 \
        /usr/local/bin/python3.13 \
        /usr/local/bin/python3.12 \
        /usr/local/bin/python3.11 \
        python3; do
        if _python_candidate_works "$candidate"; then
            if [[ "$candidate" == */* ]]; then
                printf "%s\n" "$candidate"
            else
                command -v "$candidate" 2>/dev/null
            fi
            return 0
        fi
    done
    return 1
}

find_uv_managed_python() {
    local uv_bin=""
    local candidate=""
    for uv_bin in \
        "$MMS_UV_BIN" \
        "$(command -v uv 2>/dev/null || true)" \
        "$BIN_DIR/uv"; do
        [ -x "$uv_bin" ] || continue
        candidate="$(
            UV_PYTHON_INSTALL_DIR="$MMS_UV_PYTHON_DIR" \
            UV_PYTHON_BIN_DIR="$MMS_UV_PYTHON_BIN_DIR" \
            UV_CACHE_DIR="$MMS_UV_CACHE_DIR" \
            "$uv_bin" python find "$BOOTSTRAP_PYTHON_VERSION" 2>/dev/null || true
        )"
        if _python_candidate_works "$candidate"; then
            printf "%s\n" "$candidate"
            return 0
        fi
    done
    return 1
}

bootstrap_uv() {
    local uv_bin=""

    if [ -x "$MMS_UV_BIN" ]; then
        printf "%s\n" "$MMS_UV_BIN"
        return 0
    fi

    uv_bin="$(command -v uv 2>/dev/null || true)"
    if [ -n "$uv_bin" ] && [ -x "$uv_bin" ]; then
        printf "%s\n" "$uv_bin"
        return 0
    fi

    mkdir -p "$MMS_UV_BIN_DIR"
    echo "   $(t "正在安装 MMS-managed uv（不写 shell rc）..." "Installing MMS-managed uv (without shell rc writes)...")" >&2
    if fetch_url_stdout "https://astral.sh/uv/install.sh" | env UV_INSTALL_DIR="$MMS_UV_BIN_DIR" UV_NO_MODIFY_PATH=1 INSTALLER_NO_MODIFY_PATH=1 sh >&2; then
        if [ -x "$MMS_UV_BIN" ]; then
            printf "%s\n" "$MMS_UV_BIN"
            return 0
        fi
    fi

    return 1
}

bootstrap_managed_python() {
    local uv_bin=""
    local candidate=""

    uv_bin="$(bootstrap_uv)" || return 1
    [ -x "$uv_bin" ] || return 1

    mkdir -p "$MMS_UV_PYTHON_DIR" "$MMS_UV_PYTHON_BIN_DIR" "$MMS_UV_CACHE_DIR"
    echo "   $(t "正在安装 MMS-managed Python" "Installing MMS-managed Python") $BOOTSTRAP_PYTHON_VERSION..." >&2
    if ! UV_PYTHON_INSTALL_DIR="$MMS_UV_PYTHON_DIR" \
        UV_PYTHON_BIN_DIR="$MMS_UV_PYTHON_BIN_DIR" \
        UV_CACHE_DIR="$MMS_UV_CACHE_DIR" \
        "$uv_bin" python install "$BOOTSTRAP_PYTHON_VERSION" >&2; then
        return 1
    fi

    candidate="$(find_uv_managed_python || true)"
    if _python_candidate_works "$candidate"; then
        printf "%s\n" "$candidate"
        return 0
    fi

    return 1
}

python_version_string() {
    "$(_python_bin)" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
}

python_meets_min_version() {
    "$(_python_bin)" - "$MIN_PYTHON_MAJOR" "$MIN_PYTHON_MINOR" <<'PY'
import sys

major = int(sys.argv[1])
minor = int(sys.argv[2])
sys.exit(0 if sys.version_info >= (major, minor) else 1)
PY
}

ensure_supported_python() {
    local resolved_python=""

    resolved_python="$(find_supported_python || true)"
    if [ -n "$resolved_python" ]; then
        PYTHON_CMD="$resolved_python"
        echo "✓ Python: $("$PYTHON_CMD" --version) ($PYTHON_CMD)"
        return
    fi

    echo "⚠ $(t "未检测到 Python 3.11+，准备安装 MMS-managed Python，不覆盖系统 Python。" "Python 3.11+ not found; preparing MMS-managed Python without overriding system Python.")"
    resolved_python="$(bootstrap_managed_python || true)"
    if [ -n "$resolved_python" ]; then
        PYTHON_CMD="$resolved_python"
        echo "✓ Python: $("$PYTHON_CMD" --version) ($PYTHON_CMD)"
        return
    fi

    if command -v brew >/dev/null 2>&1; then
        echo "   $(t "MMS-managed Python 安装失败，回退到 brew 安装 python@3.11（不切默认版本）..." "MMS-managed Python install failed; falling back to brew python@3.11 without switching defaults...")"
        brew install python@3.11
        resolved_python="$(find_supported_python || true)"
        if [ -n "$resolved_python" ]; then
            PYTHON_CMD="$resolved_python"
            echo "✓ Python: $("$PYTHON_CMD" --version) ($PYTHON_CMD)"
            return
        fi
    fi

    if command -v python3 >/dev/null 2>&1 && ! python_meets_min_version; then
        echo "❌ $(t "MMS 需要 Python 3.11 或更高版本" "MMS requires Python 3.11 or newer")"
        echo "   $(t "当前版本" "Current version"): $(python3 --version 2>/dev/null || python_version_string)"
        if command -v apt-get >/dev/null 2>&1; then
            echo "   $(t "Debian/Ubuntu 可先安装" "On Debian/Ubuntu, install"): sudo apt-get install python3.11 python3.11-venv"
        fi
        exit 1
    fi

    echo "❌ $(t "无法准备 Python 3.11+；请安装 curl/wget 后重试，或设置 MMS_INSTALL_PYTHON=/path/to/python3.11+" "Could not prepare Python 3.11+; install curl/wget and retry, or set MMS_INSTALL_PYTHON=/path/to/python3.11+")"
    exit 1
}

create_python_venv() {
    local venv_python="$VENV_DIR/bin/python"
    local broken_backup=""
    local managed_python=""

    mkdir -p "$MMS_HOME"

    if [ -d "$VENV_DIR" ]; then
        if [ -x "$venv_python" ] && "$venv_python" -m pip --version >/dev/null 2>&1; then
            echo "✓ $(t "复用现有虚拟环境" "Reusing existing virtual environment"): $VENV_DIR"
        else
            broken_backup="${VENV_DIR}.broken-$(date -u +%Y%m%d%H%M%S)"
            if ! mv "$VENV_DIR" "$broken_backup"; then
                echo "❌ $(t "检测到损坏的虚拟环境，但备份旧目录失败" "Detected a broken virtual environment, but failed to back it up")"
                exit 1
            fi
            echo "⚠ $(t "检测到损坏的虚拟环境，已备份后重建" "Detected a broken virtual environment; backed it up before rebuilding"): $broken_backup"
        fi
    fi

    if [ ! -x "$venv_python" ]; then
        if ! "$(_python_bin)" -m venv "$VENV_DIR"; then
            echo "⚠ $(t "当前 Python 无法创建 venv，尝试 MMS-managed Python fallback..." "Current Python cannot create a venv; trying MMS-managed Python fallback...")"
            rm -rf "$VENV_DIR"
            managed_python="$(bootstrap_managed_python || true)"
            if [ -n "$managed_python" ]; then
                PYTHON_CMD="$managed_python"
            fi
            if [ -z "$managed_python" ] || ! "$(_python_bin)" -m venv "$VENV_DIR"; then
                echo "❌ $(t "创建 Python 虚拟环境失败" "Failed to create the Python virtual environment")"
                if command -v apt-get >/dev/null 2>&1; then
                    echo "   $(t "Debian/Ubuntu 通常需要先安装 python3-venv 或 python3.11-venv" "On Debian/Ubuntu, install python3-venv or python3.11-venv first"): sudo apt-get install python3-venv"
                fi
                exit 1
            fi
        fi
    fi

    if ! "$venv_python" -m pip install --quiet --upgrade pip; then
        echo "❌ $(t "虚拟环境中的 pip 初始化失败" "Failed to initialize pip inside the virtual environment")"
        exit 1
    fi

    if ! "$venv_python" -m pip install --quiet rich httpx tomli-w; then
        echo "❌ $(t "安装 Python 依赖失败" "Failed to install Python dependencies")"
        exit 1
    fi
}

copy_dir_safely() {
    local source_dir="$1"
    local target_dir="$2"
    local zh_label="$3"
    local en_label="$4"
    local temp_dir="${target_dir}.new.$$"
    local backup_dir="${target_dir}.bak.$$"

    if [ ! -d "$source_dir" ]; then
        return 0
    fi

    rm -rf "$temp_dir" "$backup_dir"
    if ! cp -R "$source_dir" "$temp_dir"; then
        echo "❌ $(t "复制${zh_label}失败" "Failed to copy the ${en_label}")"
        rm -rf "$temp_dir"
        return 1
    fi

    if [ -e "$target_dir" ]; then
        if ! mv "$target_dir" "$backup_dir"; then
            echo "❌ $(t "备份旧${zh_label}失败" "Failed to back up the existing ${en_label}")"
            rm -rf "$temp_dir"
            return 1
        fi
    fi

    if mv "$temp_dir" "$target_dir"; then
        rm -rf "$backup_dir"
        return 0
    fi

    echo "❌ $(t "替换${zh_label}失败，已尝试恢复旧版本" "Failed to replace the ${en_label}; attempted to restore the previous version")"
    rm -rf "$temp_dir" "$target_dir"
    if [ -e "$backup_dir" ]; then
        mv "$backup_dir" "$target_dir" || true
    fi
    return 1
}


copy_hooks_dir_safely() {
    copy_dir_safely "$1" "$2" "hooks 目录" "hooks directory"
}

rewrite_shebang() {
    local target="$1"
    local python_path="$2"

    "$(_python_bin)" - "$target" "$python_path" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
python_path = sys.argv[2]
text = path.read_text(encoding="utf-8")
lines = text.splitlines(True)

if lines and lines[0].startswith("#!"):
    lines[0] = f"#!{python_path}\n"
else:
    lines.insert(0, f"#!{python_path}\n")

path.write_text("".join(lines), encoding="utf-8")
PY
}

current_installed_ref() {
    local installed_ref=""

    if [ ! -f "$VERSION_META_PATH" ]; then
        return 0
    fi

    if command -v python3 >/dev/null 2>&1; then
        installed_ref="$(python3 - "$VERSION_META_PATH" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    sys.exit(1)

print(str(data.get("installed_ref") or "").strip())
PY
)"
        printf "%s" "$installed_ref"
        return 0
    fi

    sed -n 's/.*"installed_ref"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$VERSION_META_PATH" | head -n 1
}

print_planned_version() {
    ensure_install_ref_resolved
    echo "$(t "计划安装版本" "Planned install ref"): ${RESOLVED_INSTALL_REF:-local-source}"
    echo "$(t "安装通道" "Install channel"): ${INSTALL_CHANNEL}"
}

print_version_overview() {
    local installed_ref=""
    local stable_ref=""
    local latest_tag_ref=""

    ensure_install_ref_resolved
    installed_ref="$(current_installed_ref || true)"
    stable_ref="$(resolve_latest_release_tag || true)"
    latest_tag_ref="$(resolve_latest_tag || true)"

    echo "$(t "版本概览" "Version overview")"
    echo "  $(t "当前已安装" "Currently installed"): ${installed_ref:-$(t "未安装" "none")}"
    echo "  $(t "稳定版（latest release）" "Stable release (latest release)"): ${stable_ref:-$(t "未获取" "unavailable")}"
    echo "  $(t "线上最新（latest tag）" "Latest upstream tag (latest tag)"): ${latest_tag_ref:-$(t "未获取" "unavailable")}"
    echo "  $(t "本次准备安装" "Planned install ref"): ${RESOLVED_INSTALL_REF:-local-source}"
    echo "  $(t "安装通道" "Install channel"): ${INSTALL_CHANNEL}"
}

run_install_check() {
    local node_label=""
    local cli_name=""
    local cli_path=""

    print_version_overview

    if find_supported_python >/dev/null 2>&1; then
        PYTHON_CMD="$(find_supported_python)"
        if python_meets_min_version; then
            echo "✓ $(t "Python 版本满足要求" "Python version is supported"): $("$(_python_bin)" --version)"
        else
            echo "✗ $(t "Python 版本过低，需要 3.11+" "Python version is too old; 3.11+ is required"): $("$(_python_bin)" --version)"
        fi
    else
        echo "✗ $(t "未检测到 Python 3.11+" "Python 3.11+ not found")"
    fi

    node_label="$(node_version_label || true)"
    if [ -n "$node_label" ]; then
        echo "✓ Node.js: $node_label"
    else
        echo "• $(t "未检测到 Node.js（仅影响可选 Map/Node 安装路径）" "Node.js not found (only affects optional Map/Node install paths)")"
    fi

    for cli_name in claude codex opencode; do
        cli_path="$(find_cli_binary "$cli_name" 2>/dev/null || true)"
        if [ -n "$cli_path" ]; then
            echo "✓ $(t "已检测到 CLI" "CLI detected"): $cli_name ($cli_path)"
        else
            echo "• $(t "未检测到 CLI" "CLI not found"): $cli_name"
        fi
    done

    if [ -x "$VENV_DIR/bin/python" ]; then
        echo "✓ $(t "已存在虚拟环境" "Virtual environment present"): $VENV_DIR"
    else
        echo "• $(t "虚拟环境尚未创建" "Virtual environment not created yet"): $VENV_DIR"
    fi

    if [ -L "$BIN_DIR/mms" ]; then
        echo "✓ $(t "已存在 mms 命令链接" "mms symlink present"): $BIN_DIR/mms"
        if [[ ":$PATH:" = *":$BIN_DIR:"* ]]; then
            echo "✓ $(t "~/.local/bin 已在 PATH" "~/.local/bin is on PATH"): mms"
        else
            echo "• $(t "~/.local/bin 不在当前 PATH；可运行绝对路径或用 --write-shell-rc 写入 bash/zsh/fish 配置" "~/.local/bin is not on PATH; run the absolute path or use --write-shell-rc for bash/zsh/fish config"): $BIN_DIR/mms"
        fi
    else
        echo "• $(t "mms 命令链接尚未创建" "mms symlink not created yet"): $BIN_DIR/mms"
    fi
    if [ -L "$BIN_DIR/mmc" ]; then
        echo "• $(t "检测到 retired mmc 命令链接；下次安装会移除 MMS-owned 链接" "Retired mmc command link detected; the next install removes MMS-owned links"): $BIN_DIR/mmc"
    fi
    if [ -L "$BIN_DIR/mmslogs" ]; then
        echo "✓ $(t "已存在 mmslogs 命令链接" "mmslogs symlink present"): $BIN_DIR/mmslogs"
    else
        echo "• $(t "mmslogs 命令链接尚未创建" "mmslogs symlink not created yet"): $BIN_DIR/mmslogs"
    fi


    if optional_brainkeeper_context_installed; then
        echo "✓ $(t "BrainKeeper context pack 已安装" "BrainKeeper context pack installed"): $REAL_HOME/.local/share/brainkeeper"
    else
        echo "• $(t "BrainKeeper context pack 未安装或命令链接不完整（可选）" "BrainKeeper context pack not installed or command wrappers incomplete (optional)"): --install-brainkeeper-context"
    fi

    if optional_codegraph_installed; then
        echo "✓ $(t "CodeGraph CLI 已安装" "CodeGraph CLI installed"): $(find_cli_binary codegraph || true)"
    else
        echo "• $(t "CodeGraph CLI 未安装（可选）" "CodeGraph CLI not installed (optional)"): --install-codegraph"
    fi

    if optional_toon_installed; then
        echo "✓ $(t "TOON 全局 skill/命令已安装" "TOON global skill/command installed"): $BIN_DIR/mms-toon"
    else
        echo "• $(t "TOON 全局 skill/命令未安装（可选；MMS session 内建仍可用）" "TOON global skill/command not installed (optional; bundled MMS sessions still work)"): --install-toon"
    fi

    if [ -f "$MMS_HOME/vendor/weber/SKILL.md" ]; then
        echo "✓ $(t "内建 weber session asset 已存在" "Bundled weber session asset present"): $MMS_HOME/vendor/weber"
    else
        echo "• $(t "未检测到内建 weber session asset" "Bundled weber session asset not found"): $MMS_HOME/vendor/weber"
    fi

    if optional_ecc_installed; then
        echo "✓ $(t "ECC agent pack 已安装" "ECC agent pack installed"): $MMS_HOME/agent-packs/everything-claude-code"
    else
        echo "• $(t "ECC agent pack 未安装（可选）" "ECC agent pack not installed (optional)"): --install-ecc"
    fi

    if optional_omc_installed; then
        echo "✓ $(t "OMC agent pack 已安装" "OMC agent pack installed"): $MMS_HOME/agent-packs/oh-my-claudecode"
    else
        echo "• $(t "OMC agent pack 未安装（可选）" "OMC agent pack not installed (optional)"): --install-omc"
    fi
}


enable_rtk_rewrite_hook() {
    local hook_source="$SOURCE_DIR/hooks/rtk-rewrite.sh"
    local claude_dir="$REAL_HOME/.claude"
    local hook_dir="$claude_dir/hooks"
    local hook_target="$hook_dir/rtk-rewrite.sh"

    if [ ! -f "$hook_source" ]; then
        echo "⚠ $(t "找不到 RTK hook 模板，跳过" "RTK hook template not found, skipping"): $hook_source"
        return 1
    fi

    mkdir -p "$hook_dir"
    cp "$hook_source" "$hook_target"
    chmod +x "$hook_target"

    append_claude_hook_command \
        "$claude_dir/settings.json" \
        "PreToolUse" \
        "Bash" \
        "/bin/bash $hook_target" \
        "$hook_target" \
        "bash $hook_target" \
        "/bin/bash $hook_target"

    echo "✓ $(t "已启用 Claude RTK rewrite hook" "Claude RTK rewrite hook enabled")"
    return 0
}

enable_rtk_codex_integration() {
    if ! command -v codex >/dev/null 2>&1; then
        echo "⚠ $(t "未检测到 Codex CLI，跳过 Codex 的 RTK 初始化" "Codex CLI not found, skipping Codex RTK init")"
        return 1
    fi

    if ! command -v rtk >/dev/null 2>&1; then
        echo "⚠ $(t "未检测到 rtk，跳过 Codex 的 RTK 初始化" "rtk not found, skipping Codex RTK init")"
        return 1
    fi

    run_optional_command \
        "$(t "Codex RTK 全局初始化" "Codex RTK global init")" \
        rtk init --codex --global
}

install_optional_rtk() {
    echo ""
    echo "$(t "正在安装 RTK 可选增强..." "Installing optional RTK enhancement...")"

    ensure_brew_package "jq" "jq" "jq" || true
    ensure_brew_package "rtk" "rtk" "rtk" || true

    if ! command -v jq >/dev/null 2>&1 || ! command -v rtk >/dev/null 2>&1; then
        echo "⚠ $(t "缺少 jq 或 rtk，跳过 hook 注入" "jq or rtk is missing, skipping hook enablement")"
        return 1
    fi

    enable_rtk_rewrite_hook || true
    enable_rtk_codex_integration || true
}

brainkeeper_git_available() {
    local git_bin=""

    git_bin="$(command -v git 2>/dev/null || true)"
    [ -n "$git_bin" ] || return 1

    if [ "$(uname -s 2>/dev/null || true)" = "Darwin" ] \
        && [ "$git_bin" = "/usr/bin/git" ] \
        && ! xcode-select -p >/dev/null 2>&1; then
        return 1
    fi

    "$git_bin" --version >/dev/null 2>&1
}

write_brainkeeper_mcp_config() {
    local settings_path="$REAL_HOME/.claude/settings.json"
    local server_path="$REAL_HOME/.local/share/brainkeeper/dist/server.js"
    local node_command=""
    local py_output=""

    if [ ! -f "$server_path" ]; then
        echo "⚠ $(t "找不到 BrainKeeper MCP server，跳过 MCP 配置" "BrainKeeper MCP server not found, skipping MCP config"): $server_path"
        return 1
    fi

    node_command="$(brainkeeper_node_command || true)"
    if [ -z "$node_command" ]; then
        echo "⚠ $(t "找不到 Node.js 18+，跳过 BrainKeeper MCP 配置" "Node.js 18+ not found, skipping BrainKeeper MCP config")"
        return 1
    fi

    py_output="$("$(_python_bin)" - "$settings_path" "$server_path" "$node_command" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

settings_path = Path(sys.argv[1])
server_path = sys.argv[2]
node_command = sys.argv[3]
settings_path.parent.mkdir(parents=True, exist_ok=True)

data = {}
backup_path = None
if settings_path.exists():
    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        backup_path = settings_path.with_name(
            f"{settings_path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(settings_path, backup_path)
        data = {}

mcp_servers = data.get("mcpServers")
if not isinstance(mcp_servers, dict):
    mcp_servers = {}
data["mcpServers"] = mcp_servers

legacy = mcp_servers.get("mindkeeper")
legacy_text = json.dumps(legacy, ensure_ascii=False).lower() if legacy else ""
if legacy and ("mindkeeper" in legacy_text or "brainkeeper" in legacy_text):
    mcp_servers.pop("mindkeeper", None)

mcp_servers["brainkeeper"] = {
    "command": node_command,
    "args": [server_path],
    "type": "stdio",
}
settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if backup_path is not None:
    print(f"BACKUP:{backup_path}")
PY
)"

    if [ -n "$py_output" ]; then
        echo "$py_output" | while IFS= read -r line; do
            case "$line" in
                BACKUP:*)
                    echo "⚠ $(t "检测到损坏的 Claude settings，已备份" "Detected invalid Claude settings, backup created"): ${line#BACKUP:}"
                    ;;
            esac
        done
    fi

    echo "✓ $(t "已配置 BrainKeeper MCP" "BrainKeeper MCP configured"): $settings_path"
    return 0
}

install_brainkeeper_from_archive() {
    local effective_brainkeeper_ref="$1"
    local install_dir="$REAL_HOME/.local/share/brainkeeper"
    local tmp_dir=""
    local archive_path=""
    local archive_url=""
    local extracted_dir=""
    local new_dir=""
    local backup_dir=""
    local status=0

    if ! ensure_node18_npm_for_optional_pack "BrainKeeper"; then
        return 1
    fi

    tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/mms-brainkeeper.XXXXXX")"
    archive_path="$tmp_dir/brainkeeper.tar.gz"

    case "$effective_brainkeeper_ref" in
        ""|main)
            archive_url="https://github.com/CtriXin/brainkeeper/archive/refs/heads/main.tar.gz"
            ;;
        v[0-9]*)
            archive_url="https://github.com/CtriXin/brainkeeper/archive/refs/tags/${effective_brainkeeper_ref}.tar.gz"
            ;;
        *)
            archive_url="https://github.com/CtriXin/brainkeeper/archive/refs/heads/${effective_brainkeeper_ref}.tar.gz"
            ;;
    esac

    echo "→ $(t "正在处理 BrainKeeper archive 安装" "Processing BrainKeeper archive install")"
    echo "  $archive_url"
    if ! download_url_to_file "$archive_url" "$archive_path"; then
        echo "⚠ $(t "BrainKeeper archive 下载失败" "BrainKeeper archive download failed"): $archive_url"
        rm -rf "$tmp_dir"
        return 1
    fi
    if ! tar -xzf "$archive_path" -C "$tmp_dir"; then
        echo "⚠ $(t "BrainKeeper archive 解压失败" "BrainKeeper archive extraction failed")"
        rm -rf "$tmp_dir"
        return 1
    fi

    extracted_dir="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    if [ -z "$extracted_dir" ] || [ ! -f "$extracted_dir/package.json" ]; then
        echo "⚠ $(t "BrainKeeper archive 结构异常" "BrainKeeper archive has an unexpected structure")"
        rm -rf "$tmp_dir"
        return 1
    fi

    new_dir="${install_dir}.new.$$"
    backup_dir="${install_dir}.bak.$$"
    rm -rf "$new_dir" "$backup_dir"
    mv "$extracted_dir" "$new_dir"
    mkdir -p "$(dirname "$install_dir")"
    if [ -e "$install_dir" ]; then
        mv "$install_dir" "$backup_dir"
    fi
    if ! mv "$new_dir" "$install_dir"; then
        [ -e "$backup_dir" ] && mv "$backup_dir" "$install_dir"
        rm -rf "$tmp_dir" "$new_dir"
        echo "⚠ $(t "BrainKeeper archive 安装失败，已尝试恢复旧版本" "BrainKeeper archive install failed; attempted to restore previous version")"
        return 1
    fi

    (
        cd "$install_dir"
        npm install --production --ignore-scripts
        if [ ! -f "$install_dir/dist/server.js" ] || [ ! -f "$install_dir/dist/cli.js" ]; then
            npm install --ignore-scripts
            npx tsc
        fi
    ) || status=$?

    if [ "$status" -ne 0 ]; then
        rm -rf "$install_dir"
        [ -e "$backup_dir" ] && mv "$backup_dir" "$install_dir"
        rm -rf "$tmp_dir"
        echo "⚠ $(t "BrainKeeper 依赖安装或构建失败，已尝试恢复旧版本" "BrainKeeper dependency install or build failed; attempted to restore previous version")"
        return "$status"
    fi

    rm -rf "$backup_dir" "$tmp_dir"
    write_brainkeeper_mcp_config || true
    echo "✓ $(t "BrainKeeper archive 已安装" "BrainKeeper archive installed"): $install_dir"
    return 0
}

run_brainkeeper_installer() {
    local local_installer=""
    local effective_brainkeeper_ref="${BRAINKEEPER_INSTALL_REF:-$BRAINKEEPER_DEFAULT_REF}"
    local candidate=""

    if ! ensure_node18_npm_for_optional_pack "BrainKeeper"; then
        return 1
    fi

    if brainkeeper_git_available; then
        for candidate in \
            "$(dirname "$SOURCE_DIR")/brainkeeper/install.sh" \
            "$SOURCE_DIR/../../../brainkeeper/install.sh" \
            "$(dirname "$SOURCE_DIR")/mindkeeper/install.sh" \
            "$SOURCE_DIR/../../../mindkeeper/install.sh"; do
            if [ -f "$candidate" ]; then
                local_installer="$candidate"
                break
            fi
        done

        if [ -f "$local_installer" ]; then
            if run_optional_command \
                "$(t "BrainKeeper MCP 安装" "BrainKeeper MCP install")" \
                env HOME="$REAL_HOME" bash "$local_installer" --ref "$effective_brainkeeper_ref"; then
                return 0
            fi
        fi

        if run_optional_command \
            "$(t "BrainKeeper MCP 安装" "BrainKeeper MCP install")" \
            env HOME="$REAL_HOME" BRAINKEEPER_INSTALL_REF="$effective_brainkeeper_ref" bash -lc 'set -o pipefail; curl -fsSL https://raw.githubusercontent.com/CtriXin/brainkeeper/main/install.sh | bash -s -- --ref "$BRAINKEEPER_INSTALL_REF"'; then
            return 0
        fi

        echo "⚠ $(t "BrainKeeper git 安装失败，改用 archive fallback。" "BrainKeeper git install failed; trying archive fallback.")"
    else
        echo "⚠ $(t "未检测到可用 git/Xcode Command Line Tools，改用 BrainKeeper archive fallback。" "Usable git/Xcode Command Line Tools not found; using BrainKeeper archive fallback.")"
    fi

    install_brainkeeper_from_archive "$effective_brainkeeper_ref"
}

write_brainkeeper_distill_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/distill.md"
    local marker="Managed by MMS BrainKeeper context pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-distill.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
<!-- Managed by MMS BrainKeeper context pack -->
# /distill — 上下文蒸馏

蒸馏当前工作状态，保存为 thread 文件，支持跨 session 恢复。

## 执行步骤

1. 回顾本次对话，提取 5 类信息：

   - **decisions** — 关键决策（≤5 条）
   - **changes** — 改了哪些文件
   - **findings** — 踩坑和重要发现
   - **next** — 待续事项
   - **status** — 一句话当前状态

2. 调用 MCP 工具 `brainkeeper.brain_checkpoint`，传入提取的信息。

3. 展示蒸馏回执（仅 1-2 行）。

## 极简写法（最重要！）

**MCP 工具的参数会在终端原样展示，所以必须极度精简，避免文字墙。**

每个字段的写法要求：

- **task**: ≤15 字，如 `"修复计算器5个问题"`
- **status**: ≤20 字，如 `"全部完成已验证"`
- **decisions**: 每条 ≤10 字，如 `"隐藏39页到_hidden"`, `"server-side transform全局清理"`
- **changes**: 每条只写文件名，不要路径和详细描述，如 `"static-server.js"`, `"39 HTML → _hidden/"`
- **findings**: 每条 ≤15 字，如 `"AI cleanup需两轮regex"`, `"右侧栏关闭模式不一致"`
- **next**: 每条 ≤12 字，如 `"部署验证"`, `"恢复hidden页需4步"`

**反例（禁止）**:
```
"隐藏而非删除39个页面 — 移到 public/_hidden/ 和 content/_hidden/，方便以后恢复"
```
**正例（要求）**:
```
"39页移到_hidden/暂藏"
```

## 回执格式

只输出 1-2 行：
```
已蒸馏 `dst-20260326-abc123` — {status一句话}
```

不需要展示决策/变更/发现的详细内容，thread 文件里都有。

## 其他规则

- status 必须让下个 session 立刻知道"从哪续"
- 蒸馏后不需要 /clear，用户可以继续工作
- 如果 `brainkeeper.brain_checkpoint` 不可用，可尝试 legacy `mindkeeper.brain_checkpoint`；仍不可用再写入 `~/.sce/threads/`
EOF

    mkdir -p "$command_dir"
    if [ -f "$target" ] && ! grep -Fq "$marker" "$target"; then
        echo "⚠ $(t "检测到已有自定义 Claude /distill，跳过覆盖" "Detected custom Claude /distill, skipping overwrite")"
        rm -f "$tmp_file"
        return 1
    fi

    cp "$tmp_file" "$target"
    chmod 644 "$target"
    rm -f "$tmp_file"
    echo "✓ $(t "已安装 Claude 命令" "Installed Claude command"): /distill"
    return 0
}

write_brainkeeper_contextzip_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/contextzip.md"
    local marker="Managed by MMS BrainKeeper context pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-contextzip.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
---
name: contextzip
description: '蒸馏当前工作状态并重置 token 计数器。当用户提到 "contextzip"、"cz"、"压缩 context"、"context 满了"、"达到 token 上限" 时使用。也用于手动触发上下文压缩，保存当前进度到 thread 文件。'
---

<!-- Managed by MMS BrainKeeper context pack -->
# /contextzip — 蒸馏状态 + 重置计数器

## 执行步骤

1. **调用 `brainkeeper.brain_checkpoint`** 蒸馏当前状态：
   - `repo`: 当前工作目录
   - `task`: 当前任务（从对话中提取）
   - `status`: "已压缩 context，准备重置计数器"
   - `decisions`: 提取对话中的关键决策（≤5 条）
   - `changes`: 本次对话修改的文件
   - `findings`: 重要发现/踩坑
   - `next`: 待续事项

2. **调用 `brainkeeper.brain_token_reset`** 重置 token 计数器

3. **输出回执**（1-2 行）：
   ```
   ✅ 已蒸馏到 thread: {threadId}
   💡 运行 /clear 开始新对话；新 session 输入 /cr 恢复
   ```

## 极简写法

MCP 参数要精简：
- `task`: ≤15 字
- `status`: ≤20 字
- `decisions/findings/next`: 每条 ≤15 字

## 快捷方式

用户说 `/cz` 时也使用此命令。
EOF

    mkdir -p "$command_dir"
    if [ -f "$target" ] && ! grep -Fq "$marker" "$target"; then
        echo "⚠ $(t "检测到已有自定义 Claude /cz，跳过覆盖" "Detected custom Claude /cz, skipping overwrite")"
        rm -f "$tmp_file"
        return 1
    fi

    cp "$tmp_file" "$target"
    chmod 644 "$target"
    rm -f "$tmp_file"
    echo "✓ $(t "已安装 Claude 命令" "Installed Claude command"): /contextzip"
    return 0
}

write_brainkeeper_cz_alias_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/cz.md"
    local marker="Managed by MMS BrainKeeper context pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-cz.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
---
name: cz
description: '蒸馏当前工作状态并重置 token 计数器；是 /contextzip 的短命令版本。'
---

<!-- Managed by MMS BrainKeeper context pack -->
# /cz — 蒸馏状态 + 重置计数器

执行逻辑与 `/contextzip` 相同：

1. 调用 `brainkeeper.brain_checkpoint` 蒸馏当前状态
2. 调用 `brainkeeper.brain_token_reset` 重置计数器
3. 输出 1-2 行回执，并提示 `/clear` 后新 session 使用 `/cr` 恢复

## 极简写法

- `task`: ≤15 字
- `status`: ≤20 字
- `decisions/findings/next`: 每条 ≤15 字
EOF

    mkdir -p "$command_dir"
    if [ -f "$target" ] && ! grep -Fq "$marker" "$target"; then
        echo "⚠ $(t "检测到已有自定义 Claude /cz alias，跳过覆盖" "Detected custom Claude /cz alias, skipping overwrite")"
        rm -f "$tmp_file"
        return 1
    fi

    cp "$tmp_file" "$target"
    chmod 644 "$target"
    rm -f "$tmp_file"
    return 0
}

write_brainkeeper_cr_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/cr.md"
    local marker="Managed by MMS BrainKeeper context pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-cr.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
---
name: cr
description: '恢复当前 repo 最近的 thread，或恢复指定 thread id（context restore）。'
argument-hint: [dst-thread-id]
---

<!-- Managed by MMS BrainKeeper context pack -->
# /cr — 恢复上次进度

## 执行步骤

1. 先解析当前 repo：
   - 优先运行 `git rev-parse --show-toplevel`
   - 如果失败，再使用当前工作目录

2. 如果 `$ARGUMENTS` 非空：
   - 提取其中的 thread id（如 `dst-0407-gpkzox`）
   - 调用 `brainkeeper.brain_bootstrap`，传入：
     - `repo`: 上一步解析出的 repo
     - `task`: `"恢复"`
     - `thread`: 提取到的 id

3. 如果 `$ARGUMENTS` 为空：
   - 调用 `brainkeeper.brain_bootstrap`，传入：
     - `repo`: 上一步解析出的 repo
     - `task`: `"恢复"`

4. 直接展示 `brainkeeper.brain_bootstrap` 的返回结果，不额外改写。
EOF

    mkdir -p "$command_dir"
    if [ -f "$target" ] && ! grep -Fq "$marker" "$target"; then
        echo "⚠ $(t "检测到已有自定义 Claude /cr，跳过覆盖" "Detected custom Claude /cr, skipping overwrite")"
        rm -f "$tmp_file"
        return 1
    fi

    cp "$tmp_file" "$target"
    chmod 644 "$target"
    rm -f "$tmp_file"
    echo "✓ $(t "已安装 Claude 命令" "Installed Claude command"): /cr"
    return 0
}

brainkeeper_hook_source() {
    local hook_name="$1"
    local source_dir=""
    for source_dir in \
        "$REAL_HOME/.local/share/brainkeeper" \
        "$REAL_HOME/.local/share/mindkeeper"; do
        if [ -f "$source_dir/hooks/$hook_name" ]; then
            printf "%s" "$source_dir/hooks/$hook_name"
            return 0
        fi
    done
    return 1
}

enable_brainkeeper_token_monitor_hook() {
    local hook_source=""
    local claude_dir="$REAL_HOME/.claude"
    local hook_dir="$claude_dir/hooks"
    local hook_target="$hook_dir/token-monitor-hook.sh"
    local py_output=""

    hook_source="$(brainkeeper_hook_source "token-monitor-hook.sh")"

    if [ ! -f "$hook_source" ]; then
        echo "⚠ $(t "找不到 token monitor hook 模板，跳过" "Token monitor hook template not found, skipping"): $hook_source"
        return 1
    fi

    mkdir -p "$hook_dir"
    cp "$hook_source" "$hook_target"
    chmod +x "$hook_target"

    py_output="$("$(_python_bin)" - "$claude_dir/settings.json" "$hook_target" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

settings_path = Path(sys.argv[1])
hook_path = sys.argv[2]
settings_path.parent.mkdir(parents=True, exist_ok=True)

data = {}
backup_path = None

if settings_path.exists():
    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        backup_path = settings_path.with_name(
            f"{settings_path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(settings_path, backup_path)
        data = {}

hooks = data.get("hooks")
if not isinstance(hooks, dict):
    hooks = {}
data["hooks"] = hooks

user_prompt = hooks.get("UserPromptSubmit")
if not isinstance(user_prompt, list):
    user_prompt = []

exists = False
for entry in user_prompt:
    if not isinstance(entry, dict):
        continue
    hook_items = entry.get("hooks")
    if not isinstance(hook_items, list):
        continue
    for hook in hook_items:
        if not isinstance(hook, dict):
            continue
        command = str(hook.get("command") or "").strip()
        if command in {hook_path, f"bash {hook_path}", f"/bin/bash {hook_path}"}:
            exists = True
            break
    if exists:
        break

if not exists:
    user_prompt.append(
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"/bin/bash {hook_path}",
                }
            ],
        }
    )

hooks["UserPromptSubmit"] = user_prompt
settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if backup_path is not None:
    print(f"BACKUP:{backup_path}")
PY
)"

    if [ -n "$py_output" ]; then
        echo "$py_output" | while IFS= read -r line; do
            case "$line" in
                BACKUP:*)
                    echo "⚠ $(t "检测到损坏的 Claude settings，已备份" "Detected invalid Claude settings, backup created"): ${line#BACKUP:}"
                    ;;
            esac
        done
    fi

    echo "✓ $(t "已启用 Claude token monitor hook" "Claude token monitor hook enabled")"
    return 0
}

enable_brainkeeper_context_restore_hint_hook() {
    local hook_source=""
    local claude_dir="$REAL_HOME/.claude"
    local hook_dir="$claude_dir/hooks"
    local hook_target="$hook_dir/claude-context-restore-hint.sh"
    local py_output=""

    hook_source="$(brainkeeper_hook_source "claude-context-restore-hint.sh")"

    if [ ! -f "$hook_source" ]; then
        echo "⚠ $(t "找不到 context restore hint hook 模板，跳过" "Context restore hint hook template not found, skipping"): $hook_source"
        return 1
    fi

    mkdir -p "$hook_dir"
    cp "$hook_source" "$hook_target"
    chmod +x "$hook_target"

    py_output="$("$(_python_bin)" - "$claude_dir/settings.json" "$hook_target" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

settings_path = Path(sys.argv[1])
hook_path = sys.argv[2]
settings_path.parent.mkdir(parents=True, exist_ok=True)

data = {}
backup_path = None

if settings_path.exists():
    try:
        loaded = json.loads(settings_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        backup_path = settings_path.with_name(
            f"{settings_path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(settings_path, backup_path)
        data = {}

hooks = data.get("hooks")
if not isinstance(hooks, dict):
    hooks = {}
data["hooks"] = hooks

session_start = hooks.get("SessionStart")
if not isinstance(session_start, list):
    session_start = []

exists = False
for entry in session_start:
    if not isinstance(entry, dict):
        continue
    hook_items = entry.get("hooks")
    if not isinstance(hook_items, list):
        continue
    for hook in hook_items:
        if not isinstance(hook, dict):
            continue
        command = str(hook.get("command") or "").strip()
        if command in {hook_path, f"bash {hook_path}", f"/bin/bash {hook_path}"}:
            exists = True
            break
    if exists:
        break

if not exists:
    session_start.append(
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"/bin/bash {hook_path}",
                }
            ],
        }
    )

hooks["SessionStart"] = session_start
settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if backup_path is not None:
    print(f"BACKUP:{backup_path}")
PY
)"

    if [ -n "$py_output" ]; then
        echo "$py_output" | while IFS= read -r line; do
            case "$line" in
                BACKUP:*)
                    echo "⚠ $(t "检测到损坏的 Claude settings，已备份" "Detected invalid Claude settings, backup created"): ${line#BACKUP:}"
                    ;;
            esac
        done
    fi

    echo "✓ $(t "已启用 Claude context restore hint hook" "Claude context restore hint hook enabled")"
    return 0
}

write_brainkeeper_bin_wrapper() {
    local command_name="$1"
    local target="$BIN_DIR/$command_name"
    local cli_path="$REAL_HOME/.local/share/brainkeeper/dist/cli.js"
    local marker="Managed by MMS BrainKeeper context pack"
    local tmp_file=""

    if [ ! -f "$cli_path" ]; then
        echo "⚠ $(t "找不到 BrainKeeper CLI，跳过命令链接" "BrainKeeper CLI not found, skipping command wrapper"): $cli_path"
        return 1
    fi

    mkdir -p "$BIN_DIR"
    if [ -L "$target" ]; then
        rm -f "$target"
    elif [ -e "$target" ] && ! grep -Fq "$marker" "$target" 2>/dev/null; then
        echo "⚠ $(t "检测到已有自定义命令，跳过覆盖" "Detected custom command, skipping overwrite"): $target"
        return 1
    fi

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-brainkeeper-bin.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
#!/bin/sh
# Managed by MMS BrainKeeper context pack
REAL_HOME="${MMS_REAL_HOME:-${REAL_HOME:-${ORIGINAL_HOME:-$HOME}}}"
case "$REAL_HOME" in
  */.config/mms/*) REAL_HOME="${REAL_HOME%%/.config/mms/*}" ;;
esac

CLI_PATH="$REAL_HOME/.local/share/brainkeeper/dist/cli.js"
if [ ! -f "$CLI_PATH" ]; then
  printf '%s\n' "BrainKeeper CLI not found: $CLI_PATH" >&2
  exit 127
fi

export HOME="$REAL_HOME"
export MMS_REAL_HOME="$REAL_HOME"

find_brainkeeper_node() {
  PATH_NODE="$(command -v node 2>/dev/null || true)"
  for NODE_BIN in "$REAL_HOME/.nvm/versions/node/"*/bin/node /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node "$PATH_NODE"; do
    [ -n "$NODE_BIN" ] || continue
    [ -x "$NODE_BIN" ] || continue
    if "$NODE_BIN" -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)' >/dev/null 2>&1; then
      printf '%s\n' "$NODE_BIN"
      return 0
    fi
  done
  return 1
}

NODE_BIN="$(find_brainkeeper_node || true)"
if [ -n "$NODE_BIN" ]; then
  exec "$NODE_BIN" "$CLI_PATH" "$@"
fi

printf '%s\n' "Node.js not found; install Node.js 18+ or rerun MMS installer with --install-brainkeeper-context." >&2
exit 127
EOF
    mv "$tmp_file" "$target"
    chmod 755 "$target"
    echo "✓ $(t "已安装命令" "Installed command"): $target"
    return 0
}

install_optional_brainkeeper_context() {
    echo ""
    echo "$(t "正在安装 BrainKeeper context pack..." "Installing BrainKeeper context pack...")"

    echo "⚠ $(t "这个可选包会修改 ~/.claude/settings.json、~/.claude/commands/、~/.claude/hooks/，并写入 ~/.local/bin/bk 与 ~/.local/bin/brainkeeper；若缺少 Node/npm 会尝试用 nvm 准备本次安装环境。" "This optional pack updates ~/.claude/settings.json, ~/.claude/commands/, ~/.claude/hooks/, and writes ~/.local/bin/bk plus ~/.local/bin/brainkeeper; if Node/npm is missing it tries an nvm fallback for this install.")"

    run_brainkeeper_installer || true
    ensure_brew_package "jq" "jq" "jq" || true

    if ! command -v jq >/dev/null 2>&1; then
        echo "⚠ $(t "未检测到 jq，token monitor hook 已安装但会保持静默，直到 jq 可用" "jq not found; the token monitor hook is installed but remains inactive until jq is available")"
    fi

    write_brainkeeper_distill_command || true
    write_brainkeeper_contextzip_command || true
    write_brainkeeper_cz_alias_command || true
    write_brainkeeper_cr_command || true
    enable_brainkeeper_token_monitor_hook || true
    enable_brainkeeper_context_restore_hint_hook || true
    write_brainkeeper_mcp_config || true
    write_brainkeeper_bin_wrapper "bk" || true
    write_brainkeeper_bin_wrapper "brainkeeper" || true
}

run_map_installer() {
    local local_installer=""
    local effective_map_ref="${MAP_INSTALL_REF:-$MAP_DEFAULT_REF}"
    local_installer="$(dirname "$SOURCE_DIR")/folder-graphy/bin/install.sh"
    if [ -f "$local_installer" ]; then
        run_optional_command \
            "$(t "Map 安装" "Map install")" \
            env HOME="$REAL_HOME" MAP_INSTALL_REF="$effective_map_ref" bash "$local_installer" --ref "$effective_map_ref"
        return 0
    fi

    run_optional_command \
        "$(t "Map 安装" "Map install")" \
        env HOME="$REAL_HOME" MAP_INSTALL_REF="$effective_map_ref" bash -lc 'set -o pipefail; curl -fsSL https://raw.githubusercontent.com/CtriXin/folder-graphy/main/bin/install.sh | bash -s -- --ref "$MAP_INSTALL_REF"'
}

install_optional_map() {
    local hook_source="$SOURCE_DIR/hooks/claude-map-auto-index.sh"
    local claude_dir="$REAL_HOME/.claude"
    local hook_dir="$claude_dir/hooks"
    local hook_target="$hook_dir/map-auto-index.sh"
    local map_install_dir="${MAP_INSTALL_DIR:-$REAL_HOME/.local/share/map}"
    local map_session_start_hook="$map_install_dir/dist/hooks/session-start.js"
    local node_label=""
    node_label="$(node_version_label || true)"

    echo ""
    echo "$(t "正在安装 Map auto-index..." "Installing Map auto-index...")"
    echo "⚠ $(t "这个可选包会安装 Map，并修改 ~/.claude/settings.json 和 ~/.claude/hooks/。" "This optional pack installs Map and updates ~/.claude/settings.json plus ~/.claude/hooks/.")"

    if ! node_meets_min_major 18; then
        if [ -n "$node_label" ]; then
            echo "⚠ $(t "检测到本机 Node 版本不足，跳过 Map 安装，不影响 MMS 主功能" "Detected an insufficient local Node.js version; skipping Map install without affecting core MMS"): $node_label"
        else
            echo "⚠ $(t "未检测到可用 Node.js，跳过 Map 安装，不影响 MMS 主功能" "No usable Node.js detected; skipping Map install without affecting core MMS")"
        fi
        echo "  $(t "如需安装 Map，优先复用现有 Node.js 18+ / 22；只有你明确愿意时再执行 --ensure-node22。" "To install Map later, prefer an existing Node.js 18+ / 22; only use --ensure-node22 when you explicitly want that fallback.")"
        return 0
    fi

    run_map_installer || true

    if [ ! -f "$map_session_start_hook" ]; then
        echo "⚠ $(t "未检测到 Map 的 SessionStart hook 构建产物，跳过 Claude hook 注入" "Map SessionStart hook build output not found, skipping Claude hook enablement"): $map_session_start_hook"
        return 1
    fi

    if [ ! -f "$hook_source" ]; then
        echo "⚠ $(t "找不到 Map hook 模板，跳过" "Map hook template not found, skipping"): $hook_source"
        return 1
    fi

    mkdir -p "$hook_dir"
    cp "$hook_source" "$hook_target"
    chmod +x "$hook_target"

    append_claude_hook_command \
        "$claude_dir/settings.json" \
        "SessionStart" \
        "" \
        "/bin/bash $hook_target" \
        "$hook_target" \
        "bash $hook_target" \
        "/bin/bash $hook_target"

    echo "✓ $(t "已启用 Claude Map auto-index hook" "Claude Map auto-index hook enabled")"
    return 0
}

install_optional_codegraph() {
    echo ""
    echo "$(t "正在安装 CodeGraph..." "Installing CodeGraph...")"
    echo "⚠ $(t "这个可选包会通过 npm 安装 CodeGraph CLI；不写 ~/.config/mms，也不修改 Claude/Codex 全局配置。" "This optional pack installs the CodeGraph CLI via npm; it does not write ~/.config/mms or change global Claude/Codex config.")"
    echo "  $(t "MMS 启动的 session 已带 CodeGraph auto-register hook；未初始化的 git repo 会自动 init/index，已有 .codegraph/ 则 sync。" "MMS-launched sessions already include the CodeGraph auto-register hook; uninitialized git repos auto init/index, and existing .codegraph/ repos sync.")"

    npm_global_install_with_nvm_fallback "CodeGraph CLI" "$CODEGRAPH_PACKAGE_SPEC" || true

    local codegraph_bin=""
    codegraph_bin="$(find_cli_binary codegraph || true)"
    if [ -n "$codegraph_bin" ]; then
        echo "✓ $(t "CodeGraph 可用" "CodeGraph available"): $codegraph_bin"
        print_codegraph_init_hint
    else
        echo "⚠ $(t "安装后仍未在可搜索路径中找到 codegraph" "codegraph was still not found in searchable paths after install")"
    fi
}

print_codegraph_init_hint() {
    if [ "$INSTALL_LANG" = "en" ]; then
        echo "  CodeGraph session behavior:"
        echo "    MMS sessions auto run codegraph init/index for an uninitialized git repo, and codegraph sync when .codegraph/ exists."
        echo "  Prompt for an LLM to initialize all repos now:"
        echo "    Find every git repo under this workspace, run 'codegraph init -i' when .codegraph is missing and 'codegraph sync' when it exists, skip node_modules/vendor/build dirs, and report failures."
        echo "  Tip: keep .codegraph/ local and do not commit it unless your repo intentionally tracks indexes."
    else
        echo "  CodeGraph session 行为："
        echo "    MMS session 会在未初始化的 git repo 自动执行 codegraph init/index；已有 .codegraph/ 时执行 codegraph sync。"
        echo "  让 LLM 立刻一键初始化全部 repo 的指令："
        echo "    找出当前工作区下所有 git repo；没有 .codegraph 就执行 'codegraph init -i'，已有 .codegraph 就执行 'codegraph sync'；跳过 node_modules/vendor/build 目录；最后汇总失败列表。"
        echo "  提醒：.codegraph/ 建议保持本地，不要提交，除非项目明确要追踪索引。"
    fi
}

install_optional_read_once() {
    local claude_dir="$REAL_HOME/.claude"
    local install_dir="$claude_dir/read-once"
    local hook_source="$SOURCE_DIR/hooks/read-once-hook.sh"
    local compact_source="$SOURCE_DIR/hooks/read-once-compact.sh"
    local hook_target="$install_dir/hook.sh"
    local compact_target="$install_dir/compact.sh"

    echo ""
    echo "$(t "正在安装 read-once..." "Installing read-once...")"
    echo "⚠ $(t "这个可选包会修改 ~/.claude/settings.json 和 ~/.claude/read-once/；若缺少 jq 会尝试安装。" "This optional pack updates ~/.claude/settings.json and ~/.claude/read-once/; it also attempts to install jq if missing.")"

    ensure_brew_package "jq" "jq" "jq" || true

    if [ ! -f "$hook_source" ] || [ ! -f "$compact_source" ]; then
        echo "⚠ $(t "找不到 read-once hook 模板，跳过" "read-once hook templates not found, skipping")"
        return 1
    fi

    mkdir -p "$install_dir"
    cp "$hook_source" "$hook_target"
    cp "$compact_source" "$compact_target"
    chmod +x "$hook_target" "$compact_target"

    append_claude_hook_command \
        "$claude_dir/settings.json" \
        "PreToolUse" \
        "Read" \
        "READ_ONCE_DIFF=1 /bin/bash $hook_target" \
        "$hook_target" \
        "bash $hook_target" \
        "/bin/bash $hook_target" \
        "READ_ONCE_DIFF=1 $hook_target" \
        "READ_ONCE_DIFF=1 bash $hook_target" \
        "READ_ONCE_DIFF=1 /bin/bash $hook_target"

    append_claude_hook_command \
        "$claude_dir/settings.json" \
        "PostCompact" \
        "" \
        "/bin/bash $compact_target" \
        "$compact_target" \
        "bash $compact_target" \
        "/bin/bash $compact_target"

    if ! command -v jq >/dev/null 2>&1; then
        echo "⚠ $(t "未检测到 jq，read-once hook 已安装但会保持静默，直到 jq 可用" "jq not found; read-once is installed but remains inactive until jq is available")"
    fi

    echo "✓ $(t "已启用 Claude read-once hooks" "Claude read-once hooks enabled")"
    return 0
}

write_ops_env_safe_config() {
    local template_path="$SOURCE_DIR/config/ops-env-safe.template.toml"
    local target_path="$REAL_HOME/.config/mms/ops-env-safe.toml"

    if [ ! -f "$template_path" ]; then
        echo "⚠ $(t "找不到 ops-env-safe 配置模板，跳过" "ops-env-safe config template not found, skipping"): $template_path"
        return 1
    fi

    mkdir -p "$(dirname "$target_path")"
    if [ -f "$target_path" ]; then
        echo "✓ $(t "保留现有 ops-env-safe 路径映射" "Keeping existing ops-env-safe path map"): $target_path"
        return 0
    fi

    "$(_python_bin)" - "$template_path" "$target_path" "$REAL_HOME" <<'PY'
from pathlib import Path
import sys

template_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
real_home = sys.argv[3]

text = template_path.read_text(encoding="utf-8").replace("__REAL_HOME__", real_home)
target_path.write_text(text, encoding="utf-8")
PY

    echo "✓ $(t "已写入 ops-env-safe 路径映射模板" "Wrote ops-env-safe path-map template"): $target_path"
    return 0
}

install_ops_env_safe_codex_skill() {
    local source_skill_dir="$SOURCE_DIR/assets/optional-packs/ops-env-safe"
    local target_skill_dir="$REAL_HOME/.codex/skills/ops-env-safe"
    local temp_skill_dir="${target_skill_dir}.new.$$"
    local backup_skill_dir="${target_skill_dir}.bak.$$"
    local marker="name: ops-env-safe"

    if [ ! -d "$source_skill_dir" ]; then
        echo "⚠ $(t "找不到 ops-env-safe skill 模板，跳过" "ops-env-safe skill template not found, skipping"): $source_skill_dir"
        return 1
    fi

    mkdir -p "$(dirname "$target_skill_dir")"

    if [ -f "$target_skill_dir/SKILL.md" ] && ! grep -Fq "$marker" "$target_skill_dir/SKILL.md"; then
        echo "⚠ $(t "检测到已有自定义 Codex ops-env-safe skill，跳过覆盖" "Detected custom Codex ops-env-safe skill, skipping overwrite")"
        return 1
    fi

    rm -rf "$temp_skill_dir" "$backup_skill_dir"
    cp -R "$source_skill_dir" "$temp_skill_dir"
    if [ -e "$target_skill_dir" ]; then
        mv "$target_skill_dir" "$backup_skill_dir"
    fi
    if mv "$temp_skill_dir" "$target_skill_dir"; then
        rm -rf "$backup_skill_dir"
        echo "✓ $(t "已安装 Codex skill" "Installed Codex skill"): $target_skill_dir"
        return 0
    fi

    rm -rf "$temp_skill_dir" "$target_skill_dir"
    if [ -e "$backup_skill_dir" ]; then
        mv "$backup_skill_dir" "$target_skill_dir" || true
    fi
    echo "⚠ $(t "安装 Codex ops-env-safe skill 失败" "Failed to install Codex ops-env-safe skill")"
    return 1
}

write_ops_env_safe_claude_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/ops-env-safe.md"
    local marker="Managed by MMS optional ops-env-safe pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-ops-env-safe.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
---
name: ops-env-safe
description: '在隔离会话里只读查看 host path hints，不注入真实 HOME/XDG。'
argument-hint: [entry-name]
---

<!-- Managed by MMS optional ops-env-safe pack -->
# /ops-env-safe — path-only host hints

## 执行步骤

1. 优先读取 `MMS_HOST_CONTEXT_JSON` 指向的 session-local context。
2. 没有 session context 时，读取 `MMS_OPS_ENV_SAFE_CONFIG` 或 `~/.config/mms/ops-env-safe.toml`。
3. 如果 `$ARGUMENTS` 非空：
   - 优先匹配 `[paths]` 里的同名 key
   - 输出该条目的绝对路径和用途
4. 如果 `$ARGUMENTS` 为空：
   - 列出已配置的可用 key
   - 简要说明每个 key 的 path 和 purpose

## 允许的检查

- `test -e`
- `ls`
- `stat`
- `readlink`
- `command -v`

## 红线

- 不要设置真实 `HOME`
- 不要设置任何真实 `XDG_*`
- 不要导出 token / auth env
- 不要把 path lookup 伪装成“已经可直接执行”
- 登录态 Chrome 任务必须走配置里的 WebAccess localhost proxy，不要因隔离 `HOME` 自动降级到 isolated browser
- 如果真正要执行 host 命令，必须明确提示切到单独的非隔离 shell
EOF

    mkdir -p "$command_dir"
    if [ -f "$target" ] && ! grep -Fq "$marker" "$target"; then
        echo "⚠ $(t "检测到已有自定义 Claude /ops-env-safe，跳过覆盖" "Detected custom Claude /ops-env-safe, skipping overwrite")"
        rm -f "$tmp_file"
        return 1
    fi

    cp "$tmp_file" "$target"
    chmod 644 "$target"
    rm -f "$tmp_file"
    echo "✓ $(t "已安装 Claude 命令" "Installed Claude command"): /ops-env-safe"
    return 0
}

install_optional_ops_env_safe() {
    echo ""
    echo "$(t "正在安装 ops-env-safe..." "Installing ops-env-safe...")"
    echo "⚠ $(t "这个可选包会写入 ~/.codex/skills/ops-env-safe、~/.claude/commands/ops-env-safe.md 和 ~/.config/mms/ops-env-safe.toml。" "This optional pack writes ~/.codex/skills/ops-env-safe, ~/.claude/commands/ops-env-safe.md, and ~/.config/mms/ops-env-safe.toml.")"
    echo "  $(t "它只提供 path-only host hints，不会注入真实 HOME/XDG，也不会导出 auth secrets。" "It only provides path-only host hints; it does not inject real HOME/XDG or export auth secrets.")"

    write_ops_env_safe_config || true
    install_ops_env_safe_codex_skill || true
    write_ops_env_safe_claude_command || true
}

install_token_saver_skill_link() {
    local target_skill_dir="$1"
    local source_skill_dir="$MMS_HOME/vendor/token-saver"
    local marker="name: token-saver"
    local backup_skill_dir="${target_skill_dir}.bak.$$"

    if [ ! -f "$source_skill_dir/SKILL.md" ]; then
        echo "⚠ $(t "找不到 token-saver skill，跳过" "token-saver skill not found, skipping"): $source_skill_dir"
        return 1
    fi

    mkdir -p "$(dirname "$target_skill_dir")"

    if [ -L "$target_skill_dir" ]; then
        rm -f "$target_skill_dir"
        ln -s "$source_skill_dir" "$target_skill_dir"
        echo "✓ $(t "已安装 skill" "Installed skill"): $target_skill_dir"
        return 0
    fi

    if [ -e "$target_skill_dir" ]; then
        if [ -f "$target_skill_dir/SKILL.md" ] && grep -Fq "$marker" "$target_skill_dir/SKILL.md"; then
            rm -rf "$backup_skill_dir"
            mv "$target_skill_dir" "$backup_skill_dir"
            ln -s "$source_skill_dir" "$target_skill_dir"
            rm -rf "$backup_skill_dir"
            echo "✓ $(t "已替换托管 skill 为 symlink" "Replaced managed skill with symlink"): $target_skill_dir"
            return 0
        fi
        echo "⚠ $(t "检测到已有自定义 token-saver skill，跳过覆盖" "Detected custom token-saver skill, skipping overwrite"): $target_skill_dir"
        return 1
    fi

    ln -s "$source_skill_dir" "$target_skill_dir"
    echo "✓ $(t "已安装 skill" "Installed skill"): $target_skill_dir"
    return 0
}

install_toon_skill_link() {
    local target_skill_dir="$1"
    local source_skill_dir="$MMS_HOME/vendor/toon"
    local marker="name: toon"
    local backup_skill_dir="${target_skill_dir}.bak.$$"

    if [ ! -f "$source_skill_dir/SKILL.md" ]; then
        echo "⚠ $(t "找不到 TOON skill，跳过" "TOON skill not found, skipping"): $source_skill_dir"
        return 1
    fi

    mkdir -p "$(dirname "$target_skill_dir")"
    if [ -L "$target_skill_dir" ]; then
        rm -f "$target_skill_dir"
        ln -s "$source_skill_dir" "$target_skill_dir"
        echo "✓ $(t "已安装 skill" "Installed skill"): $target_skill_dir"
        return 0
    fi

    if [ -e "$target_skill_dir" ]; then
        if [ -f "$target_skill_dir/SKILL.md" ] && grep -Fq "$marker" "$target_skill_dir/SKILL.md"; then
            rm -rf "$backup_skill_dir"
            mv "$target_skill_dir" "$backup_skill_dir"
            ln -s "$source_skill_dir" "$target_skill_dir"
            rm -rf "$backup_skill_dir"
            echo "✓ $(t "已替换托管 skill 为 symlink" "Replaced managed skill with symlink"): $target_skill_dir"
            return 0
        fi
        echo "⚠ $(t "检测到已有自定义 TOON skill，跳过覆盖" "Detected custom TOON skill, skipping overwrite"): $target_skill_dir"
        return 1
    fi

    ln -s "$source_skill_dir" "$target_skill_dir"
    echo "✓ $(t "已安装 skill" "Installed skill"): $target_skill_dir"
    return 0
}

write_mms_script_wrapper() {
    local command_name="$1"
    local source_script="$MMS_HOME/scripts/$command_name"
    local target="$BIN_DIR/$command_name"
    local marker="Managed by MMS optional script wrapper"
    local legacy_token_saver_marker="Managed by MMS optional token-saver pack"
    local tmp_file=""

    if [ ! -f "$source_script" ]; then
        echo "⚠ $(t "找不到 MMS 命令脚本，跳过" "MMS command script not found, skipping"): $source_script"
        return 1
    fi

    mkdir -p "$BIN_DIR"
    if [ -L "$target" ]; then
        rm -f "$target"
    elif [ -e "$target" ] \
        && ! grep -Fq "$marker" "$target" 2>/dev/null \
        && ! grep -Fq "$legacy_token_saver_marker" "$target" 2>/dev/null; then
        echo "⚠ $(t "检测到已有自定义命令，跳过覆盖" "Detected custom command, skipping overwrite"): $target"
        return 1
    fi

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-token-saver.XXXXXX")"
    cat > "$tmp_file" <<EOF
#!/bin/sh
# $marker
exec "$source_script" "\$@"
EOF
    mv "$tmp_file" "$target"
    chmod 755 "$target"
    echo "✓ $(t "已安装命令" "Installed command"): $target"
    return 0
}

install_token_saver_installed_skills_mirror() {
    local mirror_dir="$REAL_HOME/auto-skills/installed-skills"
    local source_skill_dir="$MMS_HOME/vendor/token-saver"
    local target="$mirror_dir/token-saver"

    if [ ! -d "$mirror_dir" ]; then
        return 0
    fi
    if [ -e "$target" ] && [ ! -L "$target" ]; then
        echo "⚠ $(t "检测到 installed-skills 自定义 token-saver，跳过覆盖" "Detected custom installed-skills token-saver, skipping overwrite"): $target"
        return 1
    fi
    if [ -L "$target" ]; then
        rm -f "$target"
    fi
    ln -s "$source_skill_dir" "$target"
    echo "✓ $(t "已更新 installed-skills 镜像" "Updated installed-skills mirror"): $target"
    return 0
}

install_toon_installed_skills_mirror() {
    local mirror_dir="$REAL_HOME/auto-skills/installed-skills"
    local source_skill_dir="$MMS_HOME/vendor/toon"
    local target="$mirror_dir/toon"

    if [ ! -d "$mirror_dir" ]; then
        return 0
    fi
    if [ -e "$target" ] && [ ! -L "$target" ]; then
        echo "⚠ $(t "检测到 installed-skills 自定义 TOON，跳过覆盖" "Detected custom installed-skills TOON, skipping overwrite"): $target"
        return 1
    fi
    if [ -L "$target" ]; then
        rm -f "$target"
    fi
    ln -s "$source_skill_dir" "$target"
    echo "✓ $(t "已更新 installed-skills 镜像" "Updated installed-skills mirror"): $target"
    return 0
}

install_optional_token_saver() {
    echo ""
    echo "$(t "正在安装 Token Saver..." "Installing Token Saver...")"
    echo "⚠ $(t "这个可选包会写入 ~/.codex/skills/token-saver、~/.claude/skills/token-saver 和 ~/.local/bin/token-saver/mms-context/mms-toon。" "This optional pack writes ~/.codex/skills/token-saver, ~/.claude/skills/token-saver, and ~/.local/bin/token-saver/mms-context/mms-toon.")"
    echo "  $(t "它不写 ~/.config/mms，也不修改模型、账号、proxy 或 reasoning 配置。" "It does not write ~/.config/mms or change model, account, proxy, or reasoning settings.")"

    install_token_saver_skill_link "$REAL_HOME/.codex/skills/token-saver" || true
    install_token_saver_skill_link "$REAL_HOME/.claude/skills/token-saver" || true
    write_mms_script_wrapper "token-saver" || true
    write_mms_script_wrapper "mms-context" || true
    write_mms_script_wrapper "mms-toon" || true
    install_token_saver_installed_skills_mirror || true
}

install_optional_toon() {
    echo ""
    echo "$(t "正在安装 TOON..." "Installing TOON...")"
    echo "⚠ $(t "这个可选包会写入 ~/.codex/skills/toon、~/.claude/skills/toon 和 ~/.local/bin/mms-toon；MMS session 内仍默认内建 TOON。" "This optional pack writes ~/.codex/skills/toon, ~/.claude/skills/toon, and ~/.local/bin/mms-toon; MMS sessions still bundle TOON by default.")"
    echo "  $(t "它不写 ~/.config/mms，也不修改模型、账号、proxy 或 reasoning 配置。" "It does not write ~/.config/mms or change model, account, proxy, or reasoning settings.")"

    install_toon_skill_link "$REAL_HOME/.codex/skills/toon" || true
    install_toon_skill_link "$REAL_HOME/.claude/skills/toon" || true
    write_mms_script_wrapper "mms-toon" || true
    install_toon_installed_skills_mirror || true
}

validate_ecc_pack_dir() {
    local pack_dir="$1"
    [ -f "$pack_dir/hooks/hooks.json" ] \
        && [ -d "$pack_dir/commands" ] \
        && [ -d "$pack_dir/skills" ]
}

validate_omc_pack_dir() {
    local pack_dir="$1"
    [ -f "$pack_dir/hooks/hooks.json" ] \
        && [ -d "$pack_dir/skills" ] \
        && [ -f "$pack_dir/.claude-plugin/plugin.json" ]
}

install_agent_pack_from_git() {
    local label="$1"
    local repo_url="$2"
    local ref="$3"
    local target_dir="$4"
    local validator="$5"
    local tmp_dir=""

    if ! command -v git >/dev/null 2>&1; then
        echo "⚠ $(t "未检测到 git，跳过 agent pack 安装" "git not found, skipping agent pack install"): $label"
        return 1
    fi

    tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/mms-agent-pack.XXXXXX")"
    echo ""
    echo "→ $(t "正在安装 Claude agent pack" "Installing Claude agent pack"): $label"
    echo "  $repo_url${ref:+#$ref}"

    if [ -n "$ref" ]; then
        if ! git clone --depth 1 --branch "$ref" --single-branch "$repo_url" "$tmp_dir"; then
            echo "⚠ $(t "下载 agent pack 失败" "Failed to download agent pack"): $label"
            rm -rf "$tmp_dir"
            return 1
        fi
    else
        if ! git clone --depth 1 "$repo_url" "$tmp_dir"; then
            echo "⚠ $(t "下载 agent pack 失败" "Failed to download agent pack"): $label"
            rm -rf "$tmp_dir"
            return 1
        fi
    fi

    rm -rf "$tmp_dir/.git"
    if ! "$validator" "$tmp_dir"; then
        echo "⚠ $(t "agent pack 结构校验失败，跳过" "Agent pack structure validation failed, skipping"): $label"
        rm -rf "$tmp_dir"
        return 1
    fi

    mkdir -p "$(dirname "$target_dir")"
    if ! copy_dir_safely "$tmp_dir" "$target_dir" "$label" "$label"; then
        rm -rf "$tmp_dir"
        return 1
    fi

    cat > "$target_dir/.mms-agent-pack-source" <<EOF
name=$label
repo=$repo_url
ref=${ref:-default}
installed_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF
    rm -rf "$tmp_dir"
    echo "✓ $(t "已安装 Claude agent pack" "Installed Claude agent pack"): $target_dir"
    return 0
}

install_optional_ecc() {
    echo ""
    echo "$(t "正在安装 ECC agent pack..." "Installing ECC agent pack...")"
    echo "⚠ $(t "这个可选包只写入 ~/.mms/agent-packs/everything-claude-code；不会修改全局 Claude hooks/config。" "This optional pack writes only ~/.mms/agent-packs/everything-claude-code; it does not modify global Claude hooks/config.")"
    install_agent_pack_from_git \
        "ECC" \
        "$ECC_REPO_URL" \
        "$ECC_INSTALL_REF" \
        "$MMS_HOME/agent-packs/everything-claude-code" \
        validate_ecc_pack_dir
}

install_optional_omc() {
    echo ""
    echo "$(t "正在安装 OMC agent pack..." "Installing OMC agent pack...")"
    echo "⚠ $(t "这个可选包只写入 ~/.mms/agent-packs/oh-my-claudecode；不会修改全局 Claude hooks/config。" "This optional pack writes only ~/.mms/agent-packs/oh-my-claudecode; it does not modify global Claude hooks/config.")"
    install_agent_pack_from_git \
        "OMC" \
        "$OMC_REPO_URL" \
        "$OMC_INSTALL_REF" \
        "$MMS_HOME/agent-packs/oh-my-claudecode" \
        validate_omc_pack_dir
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --write-shell-rc)
            WRITE_SHELL_RC=1
            ;;
        --run-setup)
            RUN_SETUP=1
            ;;
        --ensure-node22)
            ENSURE_NODE22=1
            ;;
        --launch-after-install)
            LAUNCH_AFTER_INSTALL=1
            ;;
        --install-rtk)
            INSTALL_RTK=1
            INSTALL_RTK_EXPLICIT=1
            ;;
        --install-brainkeeper-context)
            INSTALL_BRAINKEEPER_CONTEXT=1
            INSTALL_BRAINKEEPER_CONTEXT_EXPLICIT=1
            ;;
        --install-mindkeeper-context)
            INSTALL_BRAINKEEPER_CONTEXT=1
            INSTALL_BRAINKEEPER_CONTEXT_EXPLICIT=1
            ;;
        --brainkeeper-ref)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ $(t "--brainkeeper-ref 需要一个版本号或分支名" "--brainkeeper-ref requires a tag or branch name")"
                usage
                exit 1
            fi
            BRAINKEEPER_INSTALL_REF="$1"
            MINDKEEPER_INSTALL_REF="$BRAINKEEPER_INSTALL_REF"
            ;;
        --mindkeeper-ref)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ $(t "--mindkeeper-ref 需要一个版本号或分支名" "--mindkeeper-ref requires a tag or branch name")"
                usage
                exit 1
            fi
            BRAINKEEPER_INSTALL_REF="$1"
            MINDKEEPER_INSTALL_REF="$BRAINKEEPER_INSTALL_REF"
            ;;
        --install-map)
            INSTALL_MAP=1
            INSTALL_MAP_EXPLICIT=1
            ;;
        --map-ref)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ $(t "--map-ref 需要一个版本号或分支名" "--map-ref requires a tag or branch name")"
                usage
                exit 1
            fi
            MAP_INSTALL_REF="$1"
            ;;
        --install-codegraph)
            INSTALL_CODEGRAPH=1
            INSTALL_CODEGRAPH_EXPLICIT=1
            ;;
        --codegraph-package)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ $(t "--codegraph-package 需要 npm 包规格" "--codegraph-package requires an npm package spec")"
                usage
                exit 1
            fi
            CODEGRAPH_PACKAGE_SPEC="$1"
            ;;
        --install-read-once)
            INSTALL_READ_ONCE=1
            INSTALL_READ_ONCE_EXPLICIT=1
            ;;
        --install-token-saver)
            INSTALL_TOKEN_SAVER=1
            INSTALL_TOKEN_SAVER_EXPLICIT=1
            ;;
        --install-toon)
            INSTALL_TOON=1
            INSTALL_TOON_EXPLICIT=1
            ;;
        --install-ops-env-safe)
            INSTALL_OPS_ENV_SAFE=1
            INSTALL_OPS_ENV_SAFE_EXPLICIT=1
            ;;
        --install-ecc)
            INSTALL_ECC=1
            INSTALL_ECC_EXPLICIT=1
            ;;
        --ecc-ref)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ $(t "--ecc-ref 需要一个版本号或分支名" "--ecc-ref requires a tag or branch name")"
                usage
                exit 1
            fi
            ECC_INSTALL_REF="$1"
            ;;
        --install-omc)
            INSTALL_OMC=1
            INSTALL_OMC_EXPLICIT=1
            ;;
        --omc-ref)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ $(t "--omc-ref 需要一个版本号或分支名" "--omc-ref requires a tag or branch name")"
                usage
                exit 1
            fi
            OMC_INSTALL_REF="$1"
            ;;
        --install-agent-packs)
            INSTALL_ECC=1
            INSTALL_ECC_EXPLICIT=1
            INSTALL_OMC=1
            INSTALL_OMC_EXPLICIT=1
            ;;
        --install-cli)
            shift
            parse_install_cli_arg "${1:-}"
            INSTALL_CLI_EXPLICIT=1
            ;;
        --ref)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ $(t "--ref 需要一个版本号或分支名" "--ref requires a tag or branch name")"
                usage
                exit 1
            fi
            INSTALL_REF="$1"
            ;;
        --main)
            INSTALL_REF="main"
            INSTALL_CHANNEL="branch"
            ;;
        --latest-release)
            INSTALL_REF=""
            INSTALL_CHANNEL="latest-release"
            ;;
        --latest-tag)
            INSTALL_REF=""
            INSTALL_CHANNEL="latest-tag"
            ;;
        --version)
            PRINT_ONLY_VERSION=1
            ;;
        --check)
            CHECK_ONLY=1
            ;;
        --lang)
            shift
            if [[ -z "${1:-}" ]] || [[ "$1" != "zh" && "$1" != "en" ]]; then
                echo "❌ $(t "--lang 只支持 zh 或 en" "--lang only supports zh or en")"
                usage
                exit 1
            fi
            INSTALL_LANG="$1"
            INSTALL_LANG_EXPLICIT=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "❌ $(t "未知参数" "Unknown argument"): $1"
            usage
            exit 1
            ;;
    esac
    shift
done

if [ "$PRINT_ONLY_VERSION" -eq 1 ]; then
    print_version_overview
    exit 0
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
    run_install_check
    exit 0
fi

prompt_install_language
prompt_optional_install_choices

echo "===================================="
echo "  $(t "MMS 一键安装" "MMS one-line installer")"
echo "===================================="
echo ""
print_version_overview
echo ""

if [ -n "$INSTALL_CLI_LIST" ]; then
    echo "• $(t "附带安装 CLI" "Optional CLI install"): $INSTALL_CLI_LIST"
fi

if [ "$INSTALL_RTK" -eq 1 ]; then
    echo "• $(t "附带安装 RTK rewrite 增强" "Optional RTK rewrite enhancement"): on"
fi

if [ "$INSTALL_BRAINKEEPER_CONTEXT" -eq 1 ]; then
    echo "• $(t "附带安装 BrainKeeper context pack" "Optional BrainKeeper context pack"): on"
    echo "  $(t "会写入 Claude 的 MCP / 命令 / hook 配置，并安装 bk/brainkeeper 命令；不包含 Hive 能力。" "This writes Claude MCP / command / hook config and installs bk/brainkeeper commands; it does not include Hive features.")"
    echo "  $(t "BrainKeeper 版本" "BrainKeeper ref"): ${BRAINKEEPER_INSTALL_REF:-$BRAINKEEPER_DEFAULT_REF}"
fi

if [ "$INSTALL_MAP" -eq 1 ]; then
    echo "• $(t "附带安装 Map auto-index" "Optional Map auto-index"): on"
    echo "  $(t "会安装 Map，并写入 Claude 的 SessionStart hook。" "This installs Map and writes the Claude SessionStart hook.")"
    echo "  $(t "Map 版本" "Map ref"): ${MAP_INSTALL_REF:-$MAP_DEFAULT_REF}"
    echo "  $(t "默认优先复用现有 Node.js 18+；若版本不足则跳过，不会自动改你的默认 Node。" "By default MMS reuses an existing Node.js 18+ and skips Map when unavailable; it does not auto-change your default Node.")"
fi

if [ "$INSTALL_CODEGRAPH" -eq 1 ]; then
    echo "• $(t "附带安装 CodeGraph CLI" "Optional CodeGraph CLI"): on"
    echo "  $(t "会通过 npm 安装 codegraph；MMS session hook 会自动 init/index 未初始化的 git repo，已有索引则 sync。" "This installs codegraph via npm; MMS session hooks auto init/index uninitialized git repos and sync existing indexes.")"
    echo "  $(t "CodeGraph npm 包" "CodeGraph npm package"): $CODEGRAPH_PACKAGE_SPEC"
fi

if [ "$INSTALL_READ_ONCE" -eq 1 ]; then
    echo "• $(t "附带安装 read-once" "Optional read-once"): on"
    echo "  $(t "会写入 Claude 的 Read token saver hooks。" "This writes the Claude Read token saver hooks.")"
fi

if [ "$INSTALL_TOKEN_SAVER" -eq 1 ]; then
    echo "• $(t "附带安装 Token Saver" "Optional Token Saver"): on"
    echo "  $(t "会写入 Codex/Claude skill 和 ~/.local/bin/token-saver/mms-context/mms-toon，不写 ~/.config/mms。" "This writes Codex/Claude skills and ~/.local/bin/token-saver/mms-context/mms-toon, without writing ~/.config/mms.")"
fi

if [ "$INSTALL_TOON" -eq 1 ]; then
    echo "• $(t "附带安装 TOON" "Optional TOON"): on"
    echo "  $(t "会写入 Codex/Claude TOON skill 和 ~/.local/bin/mms-toon，不写 ~/.config/mms。" "This writes Codex/Claude TOON skills and ~/.local/bin/mms-toon, without writing ~/.config/mms.")"
fi

if [ "$INSTALL_OPS_ENV_SAFE" -eq 1 ]; then
    echo "• $(t "附带安装 ops-env-safe" "Optional ops-env-safe"): on"
    echo "  $(t "会写入 Codex skill、Claude /ops-env-safe 命令和 path-only 路径映射模板。" "This writes a Codex skill, a Claude /ops-env-safe command, and a path-only path-map template.")"
fi

if [ "$INSTALL_ECC" -eq 1 ]; then
    echo "• $(t "附带安装 ECC agent pack" "Optional ECC agent pack"): on"
    echo "  $(t "写入 ~/.mms/agent-packs/everything-claude-code，默认不启用，不写全局 Claude 配置。" "Writes ~/.mms/agent-packs/everything-claude-code, disabled by default, without global Claude config writes.")"
    [ -n "$ECC_INSTALL_REF" ] && echo "  ECC ref: $ECC_INSTALL_REF"
fi

if [ "$INSTALL_OMC" -eq 1 ]; then
    echo "• $(t "附带安装 OMC agent pack" "Optional OMC agent pack"): on"
    echo "  $(t "写入 ~/.mms/agent-packs/oh-my-claudecode，默认不启用，不写全局 Claude 配置。" "Writes ~/.mms/agent-packs/oh-my-claudecode, disabled by default, without global Claude config writes.")"
    [ -n "$OMC_INSTALL_REF" ] && echo "  OMC ref: $OMC_INSTALL_REF"
fi

echo "• $(t "内建 session assets" "Bundled session assets"): on"
echo "  $(t "安装后会自带 Caveman、TOON、token-saver 和 Web automation bundle（weber 路由器 + web-access 登录态 Chrome + agent-browser headless）；按 session 注入，不改全局 hooks/config。" "Install includes Caveman, TOON, token-saver, and the Web automation bundle (weber router + web-access logged-in Chrome + agent-browser headless); they are injected per session without changing global hooks/config.")"

    if [ "$ENSURE_NODE22" -eq 1 ]; then
        echo "⚠ $(t "将优先复用现有 Node.js 22；若不存在则回退到 nvm 安装，但不会切默认 Node 或写 shell rc。" "This prefers an existing Node.js 22 and only falls back to nvm when needed; it will not switch default Node or write shell rc.")"
fi

# ── 1. 检查 Python3 ──
ensure_supported_python

if [ "$ENSURE_NODE22" -eq 1 ]; then
    ensure_node22
fi

# ── 2. 创建隔离的 Python 环境 ──
echo ""
echo "$(t "正在创建隔离环境..." "Creating isolated environment...")"
create_python_venv
echo "✓ $(t "依赖已安装到" "Dependencies installed to") $VENV_DIR"

# ── 3. 复制文件到 ~/.mms ──
echo ""

prepare_source_dir

if [ -z "$SOURCE_DIR" ] || [ ! -f "$SOURCE_DIR/mms_core.py" ]; then
    echo "❌ $(t "找不到 MMS 源文件" "Cannot find MMS source files")"
    exit 1
fi

cp "$SOURCE_DIR"/mms "$MMS_HOME/mms"
[ -f "$SOURCE_DIR/mmslogs" ] && cp "$SOURCE_DIR"/mmslogs "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_core.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_tui.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_launchers.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_installer.py "$MMS_HOME/"
[ -f "$SOURCE_DIR/statusline-command.sh" ] && cp "$SOURCE_DIR"/statusline-command.sh "$MMS_HOME/"
copy_hooks_dir_safely "$SOURCE_DIR/hooks" "$MMS_HOME/hooks"
copy_dir_safely "$SOURCE_DIR/vendor" "$MMS_HOME/vendor" "vendor 目录" "vendor directory"
copy_dir_safely "$SOURCE_DIR/scripts" "$MMS_HOME/scripts" "scripts 目录" "scripts directory"
# 复制所有 mms_*.py 确保完整
for f in "$SOURCE_DIR"/mms_*.py; do
    [ -f "$f" ] && cp "$f" "$MMS_HOME/"
done
[ -f "$SOURCE_DIR/config.example.toml" ] && cp "$SOURCE_DIR/config.example.toml" "$MMS_HOME/"
echo "✓ $(t "文件已复制到" "Files copied to") $MMS_HOME"
write_version_metadata
repair_managed_claude_settings
write_language_config

chmod +x "$MMS_HOME/mms"
[ -f "$MMS_HOME/mmslogs" ] && chmod +x "$MMS_HOME/mmslogs"
[ -f "$MMS_HOME/statusline-command.sh" ] && chmod +x "$MMS_HOME/statusline-command.sh"
[ -d "$MMS_HOME/hooks" ] && find "$MMS_HOME/hooks" -type f -name '*.sh' -exec chmod +x {} +
[ -d "$MMS_HOME/scripts" ] && find "$MMS_HOME/scripts" -type f -exec chmod +x {} +

# ── 4. 修正入口的 Python 路径 ──
# 确保 shebang 指向隔离环境中的 python3
PYTHON_PATH="$VENV_DIR/bin/python"
rewrite_shebang "$MMS_HOME/mms" "$PYTHON_PATH"
[ -f "$MMS_HOME/mmslogs" ] && rewrite_shebang "$MMS_HOME/mmslogs" "$PYTHON_PATH"

# ── 4.5 可选安装：CLI / RTK ──
install_requested_clis
if [ "$INSTALL_RTK" -eq 1 ]; then
    install_optional_rtk || true
fi
if [ "$INSTALL_BRAINKEEPER_CONTEXT" -eq 1 ]; then
    install_optional_brainkeeper_context || true
fi
if [ "$INSTALL_MAP" -eq 1 ]; then
    install_optional_map || true
fi
if [ "$INSTALL_CODEGRAPH" -eq 1 ]; then
    install_optional_codegraph || true
fi
if [ "$INSTALL_READ_ONCE" -eq 1 ]; then
    install_optional_read_once || true
fi
if [ "$INSTALL_TOKEN_SAVER" -eq 1 ]; then
    install_optional_token_saver || true
fi
if [ "$INSTALL_TOON" -eq 1 ]; then
    install_optional_toon || true
fi
if [ "$INSTALL_OPS_ENV_SAFE" -eq 1 ]; then
    install_optional_ops_env_safe || true
fi
if [ "$INSTALL_ECC" -eq 1 ]; then
    install_optional_ecc || true
fi
if [ "$INSTALL_OMC" -eq 1 ]; then
    install_optional_omc || true
fi

# ── 5. 建立命令入口 ──
echo ""
mkdir -p "$BIN_DIR"

# 创建 primary symlink；legacy ccs / mmc 已下线，仅保留 mms / mmslogs 入口。
ln -sf "$MMS_HOME/mms" "$BIN_DIR/mms"
# Remove stale MMS-owned legacy ccs/mmc artifacts from previous installs without touching unrelated user commands.
rm -f "$MMS_HOME/mmc"
if [ -L "$BIN_DIR/mmc" ]; then
    mmc_target="$(readlink "$BIN_DIR/mmc" 2>/dev/null || true)"
    case "$mmc_target" in
        "$MMS_HOME"/mmc|"$REAL_HOME"/.mms/mmc|"$REAL_HOME"/.config/mms/*/mmc)
            rm -f "$BIN_DIR/mmc"
            echo "• $(t "已移除 retired mmc 命令链接" "Removed retired mmc command link"): $BIN_DIR/mmc"
            ;;
        *)
            echo "• $(t "检测到非 MMS-owned mmc 命令，保持不变" "Non-MMS-owned mmc command detected; left unchanged"): $BIN_DIR/mmc"
            ;;
    esac
fi
rm -f "$MMS_HOME/ccs"
if [ -L "$BIN_DIR/ccs" ]; then
    ccs_target="$(readlink "$BIN_DIR/ccs" 2>/dev/null || true)"
    case "$ccs_target" in
        "$MMS_HOME"/ccs|"$REAL_HOME"/.mms/ccs|"$REAL_HOME"/.config/mms/*/ccs)
            rm -f "$BIN_DIR/ccs"
            echo "• $(t "已移除 retired legacy ccs 命令链接" "Removed retired legacy ccs command link"): $BIN_DIR/ccs"
            ;;
        *)
            echo "• $(t "检测到非 MMS-owned ccs 命令，保持不变" "Non-MMS-owned ccs command detected; left unchanged"): $BIN_DIR/ccs"
            ;;
    esac
fi
if [ -e "$MMS_HOME/mmslogs" ]; then
    ln -sf "$MMS_HOME/mmslogs" "$BIN_DIR/mmslogs"
fi
echo "✓ $(t "命令已链接到" "Command linked to") $BIN_DIR/mms"

# 检查 PATH 是否包含 ~/.local/bin
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    if [ "$WRITE_SHELL_RC" -eq 1 ]; then
        write_shell_path_config
    else
        print_path_setup_hint
    fi
fi

# ── 6. 验证 ──
echo ""
if [ -x "$BIN_DIR/mms" ]; then
    DID_LAUNCH=0
    echo "===================================="
    echo "  ✅ $(t "MMS 安装完成" "MMS install completed")"
    echo "===================================="
    echo ""
    echo "  $(t "运行" "Run") $BIN_DIR/mms $(t "开始使用 / 升级后继续使用" "to start using MMS / keep using it after upgrades")"
    if [[ ":$PATH:" = *":$BIN_DIR:"* ]]; then
        echo "  $(t "当前 shell 已可直接运行:" "Current shell can run directly:") mms"
    else
        echo "  $(t "当前 shell 还未加载 ~/.local/bin；可先运行绝对路径，或重开 Ghostty/iTerm/Terminal tab 后输入 mms。" "Current shell has not loaded ~/.local/bin yet; run the absolute path now, or reopen your Ghostty/iTerm/Terminal tab and type mms.")"
    fi
    echo ""
    echo "  $(t "常用命令:" "Common commands:")"
    echo "    mms              $(t "交互选择场景" "open the interactive launcher")"
    echo "    mms 1            $(t "快速启动场景 1" "launch scene 1 quickly")"
    echo "    mms --preset coding  $(t "使用预设" "launch a preset")"
    echo "    mms config       $(t "查看/修改配置" "view or edit config")"
    echo "    mms --export claude  $(t "导出环境变量" "export env vars")"
    echo ""
    echo "  $(t "简单上手示例:" "Quick examples:")"
    echo "    mms doctor                          $(t "先看 route / auth / protocol 通不通" "check route / auth / protocol first")"
    echo "    mms test --provider <id> --cli claude  $(t "验证 Claude 实际链路" "verify the real Claude message path")"
    echo "    mms test --provider <id> --cli codex   $(t "验证 Codex 实际链路" "verify the real Codex message path")"
    echo "    mms ls                              $(t "查看可见模型" "list visible models")"
    echo "    mms                                 $(t "打开主界面开始使用" "open the main launcher")"
    echo "    mms --help                          $(t "查看完整命令列表" "show the full command list")"
    echo ""
    echo "  $(t "内建 session assets：Caveman、TOON、token-saver 和 Web automation bundle（weber 路由器 + web-access 登录态 Chrome + agent-browser headless）会随 MMS 一起提供，按 session 注入，不改全局 hooks/config。" "Bundled session assets: Caveman, TOON, token-saver, and the Web automation bundle (weber router + web-access logged-in Chrome + agent-browser headless) ship with MMS and are injected per session without global hooks/config writes.")"
    echo ""

    if [ "$INSTALL_RTK" -eq 1 ]; then
        echo "  $(t "RTK rewrite 已配置到 Claude 的 PreToolUse:Bash。" "RTK rewrite has been wired into Claude PreToolUse:Bash.")"
        echo "  $(t "如果本机已有或本轮装上了 Codex CLI，也会顺手执行 rtk init --codex --global。" "If Codex CLI is already available or gets installed in this run, the installer also runs rtk init --codex --global.")"
        echo "  $(t "后续通过 MMS 启动的 Claude session 会自动继承这个 hook。" "Claude sessions launched through MMS will inherit this hook automatically.")"
        echo ""
    fi

    if [ "$INSTALL_BRAINKEEPER_CONTEXT" -eq 1 ]; then
        echo "  $(t "BrainKeeper context pack 已安装：BrainKeeper MCP、Claude /distill /cz /cr、token hooks、bk/brainkeeper 命令。" "BrainKeeper context pack installed: BrainKeeper MCP, Claude /distill /cz /cr, token hooks, and bk/brainkeeper commands.")"
        echo "  $(t "这次不包含 Hive compact/restore，也不会自动给 Codex 写入独立 slash command；命令入口在 ~/.local/bin。" "This does not include Hive compact/restore and does not add a separate Codex slash command automatically; command wrappers live in ~/.local/bin.")"
        echo ""
    fi

    if [ "$INSTALL_CODEGRAPH" -eq 1 ]; then
        echo "  $(t "CodeGraph CLI 可选安装已执行；MMS session start hook 会自动 init/index 未初始化的 git repo，已有索引则 sync。" "CodeGraph CLI optional install ran; MMS session start hooks auto init/index uninitialized git repos and sync existing indexes.")"
        print_codegraph_init_hint
        echo ""
    fi

    if [ "$INSTALL_TOKEN_SAVER" -eq 1 ]; then
        echo "  $(t "Token Saver 已安装：Codex/Claude skill、token-saver/mms-context/mms-toon 命令。" "Token Saver installed: Codex/Claude skill plus token-saver/mms-context/mms-toon commands.")"
        echo "  $(t "普通 export-only Codex/Claude 会话现在可以靠 skill 自动使用长输出 ref/snippet。" "Plain export-only Codex/Claude sessions can now use long-output refs/snippets through the skill.")"
        echo ""
    fi

    if [ "$INSTALL_TOON" -eq 1 ]; then
        echo "  $(t "TOON 已安装：Codex/Claude skill 和 mms-toon 命令；MMS session 内仍使用内建 session asset。" "TOON installed: Codex/Claude skill plus the mms-toon command; MMS sessions still use the bundled session asset.")"
        echo ""
    fi

    if [ "$INSTALL_OPS_ENV_SAFE" -eq 1 ]; then
        echo "  $(t "ops-env-safe 已安装：Codex skill、Claude /ops-env-safe 和 path-only 路径映射模板。" "ops-env-safe installed: Codex skill, Claude /ops-env-safe, and a path-only path-map template.")"
        echo "  $(t "如需自定义宿主路径，请编辑 ~/.config/mms/ops-env-safe.toml；它不会注入真实 HOME/XDG。" "To customize host paths, edit ~/.config/mms/ops-env-safe.toml; it will not inject real HOME/XDG.")"
        echo ""
    fi

    if [ "$INSTALL_ECC" -eq 1 ]; then
        echo "  $(t "ECC agent pack 已安装到 ~/.mms/agent-packs/everything-claude-code；默认关闭，Claude 启动确认页按 X 选择后才注入。" "ECC agent pack installed under ~/.mms/agent-packs/everything-claude-code; it stays off until selected with X on the Claude launch confirm page.")"
        echo ""
    fi

    if [ "$INSTALL_OMC" -eq 1 ]; then
        echo "  $(t "OMC agent pack 已安装到 ~/.mms/agent-packs/oh-my-claudecode；默认关闭，Claude 启动确认页按 X 选择后才注入。" "OMC agent pack installed under ~/.mms/agent-packs/oh-my-claudecode; it stays off until selected with X on the Claude launch confirm page.")"
        echo ""
    fi

    if [ "$RUN_SETUP" -eq 1 ] && { [ ! -f "$CONFIG_PATH" ] || [ ! -f "$CREDENTIALS_PATH" ]; }; then
        echo "$(t "检测到首次使用，启动配置向导..." "First-time setup detected, launching setup wizard...")"
        echo ""
        "$BIN_DIR/mms" || true
        DID_LAUNCH=1
    elif [ ! -f "$CONFIG_PATH" ] || [ ! -f "$CREDENTIALS_PATH" ]; then
        echo "  $(t "首次配置请运行:" "Run this for first-time setup:")"
        echo "    $BIN_DIR/mms"
        echo ""
        echo "  $(t "如需安装完成后立即进入配置向导，可执行:" "To launch setup immediately after install, run:")"
        echo "    bash install.sh --run-setup"
    fi

    echo ""
    if [ ! -f "$CONFIG_PATH" ] || [ ! -f "$CREDENTIALS_PATH" ]; then
        echo "  $(t "完成配置后，建议先做预检，再正式启动 CLI:" "After setup, run these preflight checks before launching the real CLI:")"
    else
        echo "  $(t "正式启动 CLI 前，建议先做这组预检:" "Before launching the real CLI, run this preflight sequence:")"
    fi
    echo "    bash install.sh --check"
    echo "    mms doctor"
    echo "    mms doctor full"
    echo "    mms test --provider <id> --cli claude"
    echo "    mms test --provider <id> --cli codex"
    echo "  $(t "含义：--check 看安装是否落好；doctor 看 route/auth/protocol 通不通；test 看实际消息链路。" "Meaning: --check verifies install landing; doctor checks route/auth/protocol reachability; test checks the real message path.")"

    if [ "$LAUNCH_AFTER_INSTALL" -eq 1 ] && [ "$DID_LAUNCH" -eq 0 ]; then
        echo ""
        echo "$(t "启动 MMS..." "Launching MMS...")"
        "$BIN_DIR/mms" || true
    fi
else
    echo "❌ $(t "安装似乎失败了，请检查上面的错误信息" "Install appears to have failed. Please review the errors above")"
    exit 1
fi
