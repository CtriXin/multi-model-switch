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
MINDKEEPER_DEFAULT_REF="${MINDKEEPER_DEFAULT_REF:-v2.2.0}"
MINDKEEPER_INSTALL_REF="${MINDKEEPER_INSTALL_REF:-}"
MAP_DEFAULT_REF="${MAP_DEFAULT_REF:-v0.3.1}"
MAP_INSTALL_REF="${MAP_INSTALL_REF:-}"
NVM_INSTALL_VERSION="${NVM_INSTALL_VERSION:-v0.40.3}"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11
INSTALL_LANG="zh"
INSTALL_LANG_EXPLICIT=0
WRITE_SHELL_RC=0
RUN_SETUP=0
ENSURE_NODE22=0
LAUNCH_AFTER_INSTALL=0
INSTALL_RTK=0
INSTALL_RTK_EXPLICIT=0
INSTALL_MINDKEEPER_CONTEXT=0
INSTALL_MINDKEEPER_CONTEXT_EXPLICIT=0
INSTALL_MAP=0
INSTALL_MAP_EXPLICIT=0
INSTALL_READ_ONCE=0
INSTALL_READ_ONCE_EXPLICIT=0
INSTALL_OPS_ENV_SAFE=0
INSTALL_OPS_ENV_SAFE_EXPLICIT=0
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

optional_mindkeeper_context_installed() {
    [ -f "$REAL_HOME/.claude/commands/distill.md" ] \
        && [ -f "$REAL_HOME/.claude/commands/cz.md" ] \
        && [ -x "$REAL_HOME/.claude/hooks/token-monitor-hook.sh" ]
}

optional_map_installed() {
    [ -x "$REAL_HOME/.claude/hooks/map-auto-index.sh" ]
}

optional_read_once_installed() {
    [ -x "$REAL_HOME/.claude/read-once/hook.sh" ] \
        && [ -x "$REAL_HOME/.claude/read-once/compact.sh" ]
}

optional_ops_env_safe_installed() {
    [ -f "$REAL_HOME/.codex/skills/ops-env-safe/SKILL.md" ] \
        && [ -f "$REAL_HOME/.claude/commands/ops-env-safe.md" ]
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
    [ -r /dev/tty ] && [ -w /dev/tty ]
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

usage() {
    cat <<EOF
$(t "用法:" "Usage:")
  bash install.sh [--write-shell-rc] [--run-setup] [--ensure-node22] [--launch-after-install] [--lang zh|en] [--install-rtk] [--install-mindkeeper-context] [--mindkeeper-ref <tag-or-branch>] [--install-map] [--map-ref <tag-or-branch>] [--install-read-once] [--install-ops-env-safe] [--install-cli name[,name2]]
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
  - $(t "--install-mindkeeper-context 会安装 MindKeeper MCP、Claude 的 /distill /cz 命令和 token monitor hook；默认锁定到经过 MMS 验证的 MindKeeper tag" "--install-mindkeeper-context installs MindKeeper MCP plus Claude /distill /cz commands and the token monitor hook; by default it pins the MMS-tested MindKeeper tag")
  - $(t "--mindkeeper-ref 可覆盖 MindKeeper 安装版本，例如 v2.2.0 / main" "--mindkeeper-ref overrides the MindKeeper install ref, for example v2.2.0 / main")
  - $(t "--install-map 会安装 Map，并启用 Claude 的 SessionStart auto-index hook；默认锁定到经过 MMS 验证的 Map release" "--install-map installs Map and enables the Claude SessionStart auto-index hook; by default it pins the MMS-tested Map release")
  - $(t "--map-ref 可覆盖 Map 安装版本，例如 v0.3.1 / main" "--map-ref overrides the Map version, for example v0.3.1 / main")
  - $(t "--install-read-once 会安装 read-once，并启用 Claude 的 Read token saver hooks" "--install-read-once installs read-once and enables the Claude Read token saver hooks")
  - $(t "--install-ops-env-safe 会安装 path-only 的 host path hints：写入 Codex skill、Claude /ops-env-safe 命令和本地路径映射模板" "--install-ops-env-safe installs path-only host path hints: a Codex skill, a Claude /ops-env-safe command, and a local path-map template")
  - $(t "--install-cli 可选安装 claude/codex（支持逗号分隔）" "--install-cli optionally installs claude/codex (comma-separated)")
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
            claude|codex)
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
            note_optional_pack_detected " RTK rewrite" "RTK rewrite"
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

    if [ "$INSTALL_MINDKEEPER_CONTEXT_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_mindkeeper_context_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional context tools"
            else
                echo "可选上下文工具"
            fi
            note_optional_pack_detected " MindKeeper context pack" "MindKeeper context pack"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional context tools"
            echo "  MindKeeper context pack installs Claude /distill, /cz, and the token monitor hook."
            echo "  By default MMS pins MindKeeper to ${MINDKEEPER_INSTALL_REF:-$MINDKEEPER_DEFAULT_REF}."
            if confirm_from_tty "Install MindKeeper context pack for Claude? [y/N]: " "n"; then
                INSTALL_MINDKEEPER_CONTEXT=1
            fi
        else
            echo "可选上下文工具"
            echo "  MindKeeper context pack 会安装 Claude 的 /distill、/cz 和 token monitor hook。"
            echo "  默认会锁定到 ${MINDKEEPER_INSTALL_REF:-$MINDKEEPER_DEFAULT_REF}。"
            if confirm_from_tty "是否安装 MindKeeper context pack（Claude）？[y/N]: " "n"; then
                INSTALL_MINDKEEPER_CONTEXT=1
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
            note_optional_pack_detected " Map auto-index" "Map auto-index"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional Claude hook"
            echo "  Project map auto-index installs Map and refreshes the project structure index on session start."
            echo "  By default MMS reuses an existing Node.js 18+ runtime when available; otherwise Map is skipped unless you explicitly ask for --ensure-node22."
            if confirm_from_tty "Install Map plus the Claude SessionStart auto-index hook? [y/N]: " "n"; then
                INSTALL_MAP=1
            fi
        else
            echo "可选 Claude hook"
            echo "  Project map auto-index 会安装 Map，并在 SessionStart 时自动建立或刷新项目结构索引。"
            echo "  默认优先复用现有 Node.js 18+；如果没有合适版本，会先跳过 Map，除非你显式要求 --ensure-node22。"
            if confirm_from_tty "是否安装 Map 并启用 Claude SessionStart auto-index hook？[y/N]: " "n"; then
                INSTALL_MAP=1
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
            if confirm_from_tty "Install read-once for Claude Read token saving? [y/N]: " "n"; then
                INSTALL_READ_ONCE=1
            fi
        else
            echo "可选 Claude hook"
            echo "  Read token saver（read-once）会避免重复全文读取文件，并在改动后优先提供 diff。"
            if confirm_from_tty "是否安装 Claude 的 read-once 读文件省 token hook？[y/N]: " "n"; then
                INSTALL_READ_ONCE=1
            fi
        fi
    fi

    if [ "$INSTALL_OPS_ENV_SAFE_EXPLICIT" -eq 0 ]; then
        echo ""
        if optional_ops_env_safe_installed; then
            if [ "$INSTALL_LANG" = "en" ]; then
                echo "Optional isolated host path hints"
            else
                echo "可选隔离路径提示"
            fi
            note_optional_pack_detected " ops-env-safe" "ops-env-safe"
        elif [ "$INSTALL_LANG" = "en" ]; then
            echo "Optional isolated host path hints"
            echo "  ops-env-safe installs a path-only Codex skill, a Claude /ops-env-safe command, and a local path-map template."
            echo "  It does not inject real HOME/XDG or export auth secrets."
            if confirm_from_tty "Install ops-env-safe path-only host hints? [y/N]: " "n"; then
                INSTALL_OPS_ENV_SAFE=1
            fi
        else
            echo "可选隔离路径提示"
            echo "  ops-env-safe 会安装 path-only 的 Codex skill、Claude /ops-env-safe 命令和本地路径映射模板。"
            echo "  它不会注入真实 HOME/XDG，也不会导出认证 secret。"
            if confirm_from_tty "是否安装 ops-env-safe path-only host hints？[y/N]: " "n"; then
                INSTALL_OPS_ENV_SAFE=1
            fi
        fi
    fi

    if [ "$INSTALL_CLI_EXPLICIT" -eq 1 ]; then
        return 0
    fi

    echo ""
    echo "$(t "可选 CLI 工具" "Optional CLI tools")"

    for cli_name in claude codex; do
        case "$cli_name" in
            claude)
                cli_command="claude"
                cli_label="Claude Code"
                ;;
            codex)
                cli_command="codex"
                cli_label="Codex CLI"
                ;;
        esac

        if command -v "$cli_command" >/dev/null 2>&1; then
            echo "  ✓ $(t "已检测到" "Detected"): $cli_label"
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
    python3 - <<'PY'
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
}

resolve_latest_release_tag() {
    python3 - <<'PY'
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
}

download_remote_source() {
    local ref="$1"
    local archive_url=""
    local tarball="$SOURCE_TMP_DIR/source.tar.gz"

    if [ -z "$ref" ]; then
        return 1
    fi

    if [ "$ref" = "main" ]; then
        archive_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/main.tar.gz"
    else
        archive_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/tags/${ref}.tar.gz"
    fi

    echo "$(t "正在下载源码归档" "Downloading source archive"): $archive_url"
    if ! curl --retry 3 --retry-delay 2 --connect-timeout 10 -fsSL "$archive_url" -o "$tarball"; then
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
    python3 - "$VERSION_META_PATH" "$RESOLVED_INSTALL_REF" "$INSTALL_CHANNEL" "$INSTALL_LANG" <<'PY'
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
    python3 - "$CONFIG_PATH" "$INSTALL_LANG" <<'PY'
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
    export NVM_DIR="$REAL_HOME/.nvm"

    if [ -s "$NVM_DIR/nvm.sh" ]; then
        # shellcheck disable=SC1090
        . "$NVM_DIR/nvm.sh"
        if [ "$(nvm version 22)" != "N/A" ]; then
            nvm alias default 22 >/dev/null
            nvm use 22 >/dev/null
            echo "✓ $(t "检测到 nvm 已安装" "Detected existing nvm Node.js installation"): $(node --version)"
            return
        fi
    else
        echo "$(t "未检测到 nvm，开始安装..." "nvm not found, installing...")"
        curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_INSTALL_VERSION}/install.sh" | bash
    fi

    # shellcheck disable=SC1090
    . "$NVM_DIR/nvm.sh"
    nvm install 22
    nvm alias default 22
    nvm use 22 >/dev/null
    echo "✓ $(t "Node.js 已切换到" "Node.js switched to") $(node --version)"
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

install_named_cli() {
    local cli_name="$1"

    case "$cli_name" in
        claude)
            if command -v claude >/dev/null 2>&1; then
                echo "✓ Claude Code"
                return 0
            fi
            run_optional_command "Claude Code" bash -lc 'set -o pipefail; curl -fsSL https://claude.ai/install.sh | sh'
            ;;
        codex)
            ensure_brew_package "codex" "codex" "Codex CLI"
            ;;
        *)
            echo "⚠ $(t "未知 CLI，跳过" "Unknown CLI, skipping"): $cli_name"
            return 1
            ;;
    esac
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

    py_output="$(python3 - "$settings_path" "$hook_event" "$matcher" "$command_to_add" "$@" <<'PY'
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

    py_output="$(python3 - "$settings_path" "$template_path" <<'PY'
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

    merge_claude_settings_template "$REAL_HOME/.claude/settings.json" "$global_template_path" || true
    mkdir -p "$(dirname "$snapshot_path")"
    cp "$global_template_path" "$snapshot_path" 2>/dev/null || true
    merge_claude_settings_template "$HOME/.claude/settings.json" "$session_template_path" || true
}

python_version_string() {
    python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
}

python_meets_min_version() {
    python3 - "$MIN_PYTHON_MAJOR" "$MIN_PYTHON_MINOR" <<'PY'
import sys

major = int(sys.argv[1])
minor = int(sys.argv[2])
sys.exit(0 if sys.version_info >= (major, minor) else 1)
PY
}

ensure_supported_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        echo "❌ $(t "未找到 python3" "python3 not found")"
        if command -v brew >/dev/null 2>&1; then
            echo "   $(t "正在通过 brew 安装..." "Installing via brew...")"
            brew install python3
        else
            echo "   $(t "请先安装 Python 3.11+" "Please install Python 3.11+ first"): https://www.python.org/downloads/"
            exit 1
        fi
    fi

    if ! python_meets_min_version; then
        echo "❌ $(t "MMS 需要 Python 3.11 或更高版本" "MMS requires Python 3.11 or newer")"
        echo "   $(t "当前版本" "Current version"): $(python3 --version 2>/dev/null || python_version_string)"
        if command -v brew >/dev/null 2>&1; then
            echo "   $(t "可尝试" "Try"): brew install python@3.11"
        elif command -v apt-get >/dev/null 2>&1; then
            echo "   $(t "Debian/Ubuntu 可先安装" "On Debian/Ubuntu, install"): sudo apt-get install python3.11 python3.11-venv"
        fi
        exit 1
    fi

    echo "✓ Python3: $(python3 --version)"
}

create_python_venv() {
    local venv_python="$VENV_DIR/bin/python"
    local broken_backup=""

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
        if ! python3 -m venv "$VENV_DIR"; then
            echo "❌ $(t "创建 Python 虚拟环境失败" "Failed to create the Python virtual environment")"
            if command -v apt-get >/dev/null 2>&1; then
                echo "   $(t "Debian/Ubuntu 通常需要先安装 python3-venv 或 python3.11-venv" "On Debian/Ubuntu, install python3-venv or python3.11-venv first"): sudo apt-get install python3-venv"
            fi
            exit 1
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

copy_hooks_dir_safely() {
    local source_hooks="$1"
    local target_hooks="$2"
    local temp_hooks="${target_hooks}.new.$$"
    local backup_hooks="${target_hooks}.bak.$$"

    if [ ! -d "$source_hooks" ]; then
        return 0
    fi

    rm -rf "$temp_hooks" "$backup_hooks"
    if ! cp -R "$source_hooks" "$temp_hooks"; then
        echo "❌ $(t "复制 hooks 目录失败" "Failed to copy the hooks directory")"
        rm -rf "$temp_hooks"
        return 1
    fi

    if [ -e "$target_hooks" ]; then
        if ! mv "$target_hooks" "$backup_hooks"; then
            echo "❌ $(t "备份旧 hooks 目录失败" "Failed to back up the existing hooks directory")"
            rm -rf "$temp_hooks"
            return 1
        fi
    fi

    if mv "$temp_hooks" "$target_hooks"; then
        rm -rf "$backup_hooks"
        return 0
    fi

    echo "❌ $(t "替换 hooks 目录失败，已尝试恢复旧版本" "Failed to replace the hooks directory; attempted to restore the previous version")"
    rm -rf "$temp_hooks" "$target_hooks"
    if [ -e "$backup_hooks" ]; then
        mv "$backup_hooks" "$target_hooks" || true
    fi
    return 1
}

rewrite_shebang() {
    local target="$1"
    local python_path="$2"

    python3 - "$target" "$python_path" <<'PY'
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

run_install_check() {
    local node_label=""
    local installed_ref=""

    print_planned_version
    installed_ref="$(current_installed_ref || true)"
    echo "$(t "当前已安装版本" "Currently installed ref"): ${installed_ref:-none}"

    if command -v python3 >/dev/null 2>&1; then
        if python_meets_min_version; then
            echo "✓ $(t "Python 版本满足要求" "Python version is supported"): $(python3 --version)"
        else
            echo "✗ $(t "Python 版本过低，需要 3.11+" "Python version is too old; 3.11+ is required"): $(python3 --version)"
        fi
    else
        echo "✗ $(t "未检测到 python3" "python3 not found")"
    fi

    node_label="$(node_version_label || true)"
    if [ -n "$node_label" ]; then
        echo "✓ Node.js: $node_label"
    else
        echo "• $(t "未检测到 Node.js（仅影响可选 Map/Node 安装路径）" "Node.js not found (only affects optional Map/Node install paths)")"
    fi

    if [ -x "$VENV_DIR/bin/python" ]; then
        echo "✓ $(t "已存在虚拟环境" "Virtual environment present"): $VENV_DIR"
    else
        echo "• $(t "虚拟环境尚未创建" "Virtual environment not created yet"): $VENV_DIR"
    fi

    if [ -L "$BIN_DIR/mms" ]; then
        echo "✓ $(t "已存在 mms 命令链接" "mms symlink present"): $BIN_DIR/mms"
    else
        echo "• $(t "mms 命令链接尚未创建" "mms symlink not created yet"): $BIN_DIR/mms"
    fi

    if [ -L "$BIN_DIR/ccs" ]; then
        echo "✓ $(t "已存在 ccs 命令链接" "ccs symlink present"): $BIN_DIR/ccs"
    else
        echo "• $(t "ccs 命令链接尚未创建" "ccs symlink not created yet"): $BIN_DIR/ccs"
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

run_mindkeeper_installer() {
    local local_installer=""
    local effective_mindkeeper_ref="${MINDKEEPER_INSTALL_REF:-$MINDKEEPER_DEFAULT_REF}"

    local_installer="$(dirname "$SOURCE_DIR")/mindkeeper/install.sh"
    if [ -f "$local_installer" ]; then
        run_optional_command \
            "$(t "MindKeeper MCP 安装" "MindKeeper MCP install")" \
            env HOME="$REAL_HOME" bash "$local_installer" --ref "$effective_mindkeeper_ref"
        return 0
    fi

    run_optional_command \
        "$(t "MindKeeper MCP 安装" "MindKeeper MCP install")" \
        env HOME="$REAL_HOME" MINDKEEPER_INSTALL_REF="$effective_mindkeeper_ref" bash -lc 'set -o pipefail; curl -fsSL https://raw.githubusercontent.com/CtriXin/mindkeeper/main/install.sh | bash -s -- --ref "$MINDKEEPER_INSTALL_REF"'
}

write_mindkeeper_distill_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/distill.md"
    local marker="Managed by MMS MindKeeper context pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-distill.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
<!-- Managed by MMS MindKeeper context pack -->
# /distill — 上下文蒸馏

蒸馏当前工作状态，保存为 thread 文件，支持跨 session 恢复。

## 执行步骤

1. 回顾本次对话，提取 5 类信息：

   - **decisions** — 关键决策（≤5 条）
   - **changes** — 改了哪些文件
   - **findings** — 踩坑和重要发现
   - **next** — 待续事项
   - **status** — 一句话当前状态

2. 调用 MCP 工具 `brain_checkpoint`，传入提取的信息。

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
- 如果 brain_checkpoint MCP 不可用，写入 `~/.sce/threads/`
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

write_mindkeeper_contextzip_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/contextzip.md"
    local marker="Managed by MMS MindKeeper context pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-contextzip.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
---
name: contextzip
description: '蒸馏当前工作状态并重置 token 计数器。当用户提到 "contextzip"、"cz"、"压缩 context"、"context 满了"、"达到 token 上限" 时使用。也用于手动触发上下文压缩，保存当前进度到 thread 文件。'
---

<!-- Managed by MMS MindKeeper context pack -->
# /contextzip — 蒸馏状态 + 重置计数器

## 执行步骤

1. **调用 `brain_checkpoint`** 蒸馏当前状态：
   - `repo`: 当前工作目录
   - `task`: 当前任务（从对话中提取）
   - `status`: "已压缩 context，准备重置计数器"
   - `decisions`: 提取对话中的关键决策（≤5 条）
   - `changes`: 本次对话修改的文件
   - `findings`: 重要发现/踩坑
   - `next`: 待续事项

2. **调用 `brain_token_reset`** 重置 token 计数器

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

write_mindkeeper_cz_alias_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/cz.md"
    local marker="Managed by MMS MindKeeper context pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-cz.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
---
name: cz
description: '蒸馏当前工作状态并重置 token 计数器；是 /contextzip 的短命令版本。'
---

<!-- Managed by MMS MindKeeper context pack -->
# /cz — 蒸馏状态 + 重置计数器

执行逻辑与 `/contextzip` 相同：

1. 调用 `brain_checkpoint` 蒸馏当前状态
2. 调用 `brain_token_reset` 重置计数器
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

write_mindkeeper_cr_command() {
    local command_dir="$REAL_HOME/.claude/commands"
    local target="$command_dir/cr.md"
    local marker="Managed by MMS MindKeeper context pack"
    local tmp_file=""

    tmp_file="$(mktemp "${TMPDIR:-/tmp}/mms-cr.XXXXXX")"
    cat > "$tmp_file" <<'EOF'
---
name: cr
description: '恢复当前 repo 最近的 thread，或恢复指定 thread id（context restore）。'
argument-hint: [dst-thread-id]
---

<!-- Managed by MMS MindKeeper context pack -->
# /cr — 恢复上次进度

## 执行步骤

1. 先解析当前 repo：
   - 优先运行 `git rev-parse --show-toplevel`
   - 如果失败，再使用当前工作目录

2. 如果 `$ARGUMENTS` 非空：
   - 提取其中的 thread id（如 `dst-0407-gpkzox`）
   - 调用 `brain_bootstrap`，传入：
     - `repo`: 上一步解析出的 repo
     - `task`: `"恢复"`
     - `thread`: 提取到的 id

3. 如果 `$ARGUMENTS` 为空：
   - 调用 `brain_bootstrap`，传入：
     - `repo`: 上一步解析出的 repo
     - `task`: `"恢复"`

4. 直接展示 `brain_bootstrap` 的返回结果，不额外改写。
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

enable_mindkeeper_token_monitor_hook() {
    local hook_source="$REAL_HOME/.local/share/mindkeeper/hooks/token-monitor-hook.sh"
    local claude_dir="$REAL_HOME/.claude"
    local hook_dir="$claude_dir/hooks"
    local hook_target="$hook_dir/token-monitor-hook.sh"
    local py_output=""

    if [ ! -f "$hook_source" ]; then
        echo "⚠ $(t "找不到 token monitor hook 模板，跳过" "Token monitor hook template not found, skipping"): $hook_source"
        return 1
    fi

    mkdir -p "$hook_dir"
    cp "$hook_source" "$hook_target"
    chmod +x "$hook_target"

    py_output="$(python3 - "$claude_dir/settings.json" "$hook_target" <<'PY'
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

enable_mindkeeper_context_restore_hint_hook() {
    local hook_source="$REAL_HOME/.local/share/mindkeeper/hooks/claude-context-restore-hint.sh"
    local claude_dir="$REAL_HOME/.claude"
    local hook_dir="$claude_dir/hooks"
    local hook_target="$hook_dir/claude-context-restore-hint.sh"
    local py_output=""

    if [ ! -f "$hook_source" ]; then
        echo "⚠ $(t "找不到 context restore hint hook 模板，跳过" "Context restore hint hook template not found, skipping"): $hook_source"
        return 1
    fi

    mkdir -p "$hook_dir"
    cp "$hook_source" "$hook_target"
    chmod +x "$hook_target"

    py_output="$(python3 - "$claude_dir/settings.json" "$hook_target" <<'PY'
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

install_optional_mindkeeper_context() {
    echo ""
    echo "$(t "正在安装 MindKeeper context pack..." "Installing MindKeeper context pack...")"

    echo "⚠ $(t "这个可选包会修改 ~/.claude/settings.json、~/.claude/commands/ 和 ~/.claude/hooks/；若缺少 jq 会尝试安装。" "This optional pack updates ~/.claude/settings.json, ~/.claude/commands/, and ~/.claude/hooks/; it also attempts to install jq if missing.")"

    run_mindkeeper_installer || true
    ensure_brew_package "jq" "jq" "jq" || true

    if ! command -v jq >/dev/null 2>&1; then
        echo "⚠ $(t "未检测到 jq，token monitor hook 已安装但会保持静默，直到 jq 可用" "jq not found; the token monitor hook is installed but remains inactive until jq is available")"
    fi

    write_mindkeeper_distill_command || true
    write_mindkeeper_contextzip_command || true
    write_mindkeeper_cz_alias_command || true
    write_mindkeeper_cr_command || true
    enable_mindkeeper_token_monitor_hook || true
    enable_mindkeeper_context_restore_hint_hook || true
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

    python3 - "$template_path" "$target_path" "$REAL_HOME" <<'PY'
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

1. 读取 `~/.config/mms/ops-env-safe.toml`。
2. 如果 `$ARGUMENTS` 非空：
   - 优先匹配 `[paths]` 里的同名 key
   - 输出该条目的绝对路径和用途
3. 如果 `$ARGUMENTS` 为空：
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
        --install-mindkeeper-context)
            INSTALL_MINDKEEPER_CONTEXT=1
            INSTALL_MINDKEEPER_CONTEXT_EXPLICIT=1
            ;;
        --mindkeeper-ref)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ $(t "--mindkeeper-ref 需要一个版本号或分支名" "--mindkeeper-ref requires a tag or branch name")"
                usage
                exit 1
            fi
            MINDKEEPER_INSTALL_REF="$1"
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
        --install-read-once)
            INSTALL_READ_ONCE=1
            INSTALL_READ_ONCE_EXPLICIT=1
            ;;
        --install-ops-env-safe)
            INSTALL_OPS_ENV_SAFE=1
            INSTALL_OPS_ENV_SAFE_EXPLICIT=1
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
    print_planned_version
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

if [ -n "$INSTALL_CLI_LIST" ]; then
    echo "• $(t "附带安装 CLI" "Optional CLI install"): $INSTALL_CLI_LIST"
fi

if [ "$INSTALL_RTK" -eq 1 ]; then
    echo "• $(t "附带安装 RTK rewrite 增强" "Optional RTK rewrite enhancement"): on"
fi

if [ "$INSTALL_MINDKEEPER_CONTEXT" -eq 1 ]; then
    echo "• $(t "附带安装 MindKeeper context pack" "Optional MindKeeper context pack"): on"
    echo "  $(t "会写入 Claude 的 MCP / 命令 / hook 配置，不包含 Hive 能力。" "This writes Claude MCP / command / hook config and does not include Hive features.")"
    echo "  $(t "MindKeeper 版本" "MindKeeper ref"): ${MINDKEEPER_INSTALL_REF:-$MINDKEEPER_DEFAULT_REF}"
fi

if [ "$INSTALL_MAP" -eq 1 ]; then
    echo "• $(t "附带安装 Map auto-index" "Optional Map auto-index"): on"
    echo "  $(t "会安装 Map，并写入 Claude 的 SessionStart hook。" "This installs Map and writes the Claude SessionStart hook.")"
    echo "  $(t "Map 版本" "Map ref"): ${MAP_INSTALL_REF:-$MAP_DEFAULT_REF}"
    echo "  $(t "默认优先复用现有 Node.js 18+；若版本不足则跳过，不会自动改你的默认 Node。" "By default MMS reuses an existing Node.js 18+ and skips Map when unavailable; it does not auto-change your default Node.")"
fi

if [ "$INSTALL_READ_ONCE" -eq 1 ]; then
    echo "• $(t "附带安装 read-once" "Optional read-once"): on"
    echo "  $(t "会写入 Claude 的 Read token saver hooks。" "This writes the Claude Read token saver hooks.")"
fi

if [ "$INSTALL_OPS_ENV_SAFE" -eq 1 ]; then
    echo "• $(t "附带安装 ops-env-safe" "Optional ops-env-safe"): on"
    echo "  $(t "会写入 Codex skill、Claude /ops-env-safe 命令和 path-only 路径映射模板。" "This writes a Codex skill, a Claude /ops-env-safe command, and a path-only path-map template.")"
fi

if [ "$ENSURE_NODE22" -eq 1 ]; then
    echo "⚠ $(t "将优先复用现有 Node.js 22；若不存在则回退到 nvm 安装，这可能更新你的 shell 配置。" "This prefers an existing Node.js 22 and only falls back to nvm when needed; that may update your shell config.")"
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

cp "$SOURCE_DIR"/ccs "$MMS_HOME/ccs"
cp "$SOURCE_DIR"/mms "$MMS_HOME/mms"
cp "$SOURCE_DIR"/mms_core.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_tui.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_launchers.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_installer.py "$MMS_HOME/"
[ -f "$SOURCE_DIR/statusline-command.sh" ] && cp "$SOURCE_DIR"/statusline-command.sh "$MMS_HOME/"
copy_hooks_dir_safely "$SOURCE_DIR/hooks" "$MMS_HOME/hooks"
# 复制所有 mms_*.py 确保完整
for f in "$SOURCE_DIR"/mms_*.py; do
    [ -f "$f" ] && cp "$f" "$MMS_HOME/"
done
[ -f "$SOURCE_DIR/config.example.toml" ] && cp "$SOURCE_DIR/config.example.toml" "$MMS_HOME/"
echo "✓ $(t "文件已复制到" "Files copied to") $MMS_HOME"
write_version_metadata
repair_managed_claude_settings
write_language_config

chmod +x "$MMS_HOME/ccs"
chmod +x "$MMS_HOME/mms"
[ -f "$MMS_HOME/statusline-command.sh" ] && chmod +x "$MMS_HOME/statusline-command.sh"
[ -d "$MMS_HOME/hooks" ] && find "$MMS_HOME/hooks" -type f -name '*.sh' -exec chmod +x {} +

# ── 4. 修正入口的 Python 路径 ──
# 确保 shebang 指向隔离环境中的 python3
PYTHON_PATH="$VENV_DIR/bin/python"
rewrite_shebang "$MMS_HOME/ccs" "$PYTHON_PATH"
rewrite_shebang "$MMS_HOME/mms" "$PYTHON_PATH"

# ── 4.5 可选安装：CLI / RTK ──
install_requested_clis
if [ "$INSTALL_RTK" -eq 1 ]; then
    install_optional_rtk || true
fi
if [ "$INSTALL_MINDKEEPER_CONTEXT" -eq 1 ]; then
    install_optional_mindkeeper_context || true
fi
if [ "$INSTALL_MAP" -eq 1 ]; then
    install_optional_map || true
fi
if [ "$INSTALL_READ_ONCE" -eq 1 ]; then
    install_optional_read_once || true
fi
if [ "$INSTALL_OPS_ENV_SAFE" -eq 1 ]; then
    install_optional_ops_env_safe || true
fi

# ── 5. 建立命令入口 ──
echo ""
mkdir -p "$BIN_DIR"

# 创建 symlink
ln -sf "$MMS_HOME/ccs" "$BIN_DIR/ccs"
ln -sf "$MMS_HOME/mms" "$BIN_DIR/mms"
if [ -e "$MMS_HOME/mmslogs" ]; then
    ln -sf "$MMS_HOME/mmslogs" "$BIN_DIR/mmslogs"
fi
echo "✓ $(t "命令已链接到" "Commands linked to") $BIN_DIR/mms $(t "和" "and") $BIN_DIR/ccs"

# 检查 PATH 是否包含 ~/.local/bin
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

    if [ "$WRITE_SHELL_RC" -eq 1 ]; then
        SHELL_RC=""
        if [ -f "$REAL_HOME/.zshrc" ]; then
            SHELL_RC="$REAL_HOME/.zshrc"
        elif [ -f "$REAL_HOME/.bashrc" ]; then
            SHELL_RC="$REAL_HOME/.bashrc"
        elif [ -f "$REAL_HOME/.bash_profile" ]; then
            SHELL_RC="$REAL_HOME/.bash_profile"
        fi

        MARKER="# Added by MMS"
        if [ -n "$SHELL_RC" ]; then
            if ! grep -q "$MARKER" "$SHELL_RC" 2>/dev/null; then
                echo "" >> "$SHELL_RC"
                echo "$MARKER" >> "$SHELL_RC"
                echo "$PATH_LINE" >> "$SHELL_RC"
                echo "✓ PATH $(t "已写入" "written to") $SHELL_RC"
            fi
        else
            echo "⚠ $(t "未找到 shell 配置文件，请手动添加:" "No shell rc file found. Please add manually:")"
            echo "  $PATH_LINE"
        fi
    else
        echo "⚠ $(t "未修改你的 shell 配置。" "Your shell config was not modified.")"
        echo "  $(t "当前安装不会自动写入 ~/.zshrc / ~/.bashrc。" "This install does not automatically write to ~/.zshrc or ~/.bashrc.")"
        echo "  $(t "如需全局可用，请手动添加:" "To make MMS globally available, add:")"
        echo "    $PATH_LINE"
        echo "  $(t "或重新执行" "Or rerun"): bash install.sh --write-shell-rc"
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

    if [ "$INSTALL_RTK" -eq 1 ]; then
        echo "  $(t "RTK rewrite 已配置到 Claude 的 PreToolUse:Bash。" "RTK rewrite has been wired into Claude PreToolUse:Bash.")"
        echo "  $(t "如果本机已有或本轮装上了 Codex CLI，也会顺手执行 rtk init --codex --global。" "If Codex CLI is already available or gets installed in this run, the installer also runs rtk init --codex --global.")"
        echo "  $(t "后续通过 MMS 启动的 Claude session 会自动继承这个 hook。" "Claude sessions launched through MMS will inherit this hook automatically.")"
        echo ""
    fi

    if [ "$INSTALL_MINDKEEPER_CONTEXT" -eq 1 ]; then
        echo "  $(t "MindKeeper context pack 已安装：Claude /distill、/cz、MindKeeper MCP、token monitor hook。" "MindKeeper context pack installed: Claude /distill, /cz, MindKeeper MCP, and the token monitor hook.")"
        echo "  $(t "这次不包含 Hive compact/restore，也不会自动给 Codex 写入独立 slash command。" "This does not include Hive compact/restore and does not add a separate Codex slash command automatically.")"
        echo ""
    fi

    if [ "$INSTALL_OPS_ENV_SAFE" -eq 1 ]; then
        echo "  $(t "ops-env-safe 已安装：Codex skill、Claude /ops-env-safe 和 path-only 路径映射模板。" "ops-env-safe installed: Codex skill, Claude /ops-env-safe, and a path-only path-map template.")"
        echo "  $(t "如需自定义宿主路径，请编辑 ~/.config/mms/ops-env-safe.toml；它不会注入真实 HOME/XDG。" "To customize host paths, edit ~/.config/mms/ops-env-safe.toml; it will not inject real HOME/XDG.")"
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
