#!/bin/bash
# MMS 一键安装脚本
# 用法: curl -fsSL <url>/install.sh | bash
#   或: bash install.sh [--write-shell-rc] [--run-setup] [--ensure-node22] [--launch-after-install]
#   或: bash install.sh --ref v1.2.0

set -e

REPO_OWNER="CtriXin"
REPO_NAME="multi-model-switch"
MMS_HOME="$HOME/.mms"
BIN_DIR="$HOME/.local/bin"
VENV_DIR="$MMS_HOME/.venv"
CREDENTIALS_PATH="$HOME/.config/mms/credentials.sh"
CONFIG_PATH="$HOME/.config/mms/config.toml"
VERSION_META_PATH="$HOME/.config/mms/version.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" 2>/dev/null)" && pwd 2>/dev/null || echo "")"
SOURCE_DIR=""
SOURCE_TMP_DIR=""
INSTALL_REF=""
RESOLVED_INSTALL_REF=""
INSTALL_CHANNEL="latest-tag"
INSTALL_LANG="zh"
INSTALL_LANG_EXPLICIT=0
WRITE_SHELL_RC=0
RUN_SETUP=0
ENSURE_NODE22=0
LAUNCH_AFTER_INSTALL=0
INSTALL_RTK=0
INSTALL_RTK_EXPLICIT=0
INSTALL_CLI_LIST=""
INSTALL_CLI_EXPLICIT=0

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
  bash install.sh [--write-shell-rc] [--run-setup] [--ensure-node22] [--launch-after-install] [--lang zh|en] [--install-rtk] [--install-cli name[,name2]]
  bash install.sh --ref <tag-or-branch>
  bash install.sh --main
  bash install.sh --latest-tag
  bash install.sh --latest-release

$(t "说明:" "Notes:")
  - $(t "默认远程安装/升级使用最新 semver tag" "By default, remote install/upgrade uses the latest semver tag")
  - $(t "--ref 可指定版本号或分支，例如 v1.2.0 / main" "--ref can pin a specific version or branch, for example v1.2.0 / main")
  - $(t "--lang 可设置默认 UI 语言（zh / en）" "--lang sets the default UI language (zh / en)")
  - $(t "--install-rtk 会额外安装 jq + rtk，并把 Claude 的 RTK rewrite hook 配好" "--install-rtk installs jq + rtk and enables the Claude RTK rewrite hook")
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
        if [ "$INSTALL_LANG" = "en" ]; then
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
    curl -fsSL "$archive_url" -o "$tarball"
    tar -xzf "$tarball" -C "$SOURCE_TMP_DIR"

    SOURCE_DIR="$(find "$SOURCE_TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    if [ -z "$SOURCE_DIR" ] || [ ! -f "$SOURCE_DIR/mms_core.py" ]; then
        echo "❌ $(t "远程源码解压失败" "Failed to extract downloaded source archive")"
        return 1
    fi
    echo "✓ $(t "已获取源码" "Source prepared"): $SOURCE_DIR"
}

write_version_metadata() {
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
    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/mms_core.py" ]; then
        SOURCE_DIR="$SCRIPT_DIR"
        echo "✓ $(t "使用本地源码" "Using local source tree"): $SOURCE_DIR"
        return
    fi

    SOURCE_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mms-install.XXXXXX")"

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

    download_remote_source "$ref"
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

ensure_node22() {
    local major
    major="$(detect_node_major || true)"
    if [[ -n "$major" ]] && [[ "$major" -ge 22 ]]; then
        echo "✓ Node.js: v$(node --version | sed 's/^v//')"
        return
    fi

    echo ""
    echo "$(t "正在准备 Node.js 22（通过 nvm）..." "Preparing Node.js 22 (via nvm)...")"
    export NVM_DIR="$HOME/.nvm"

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
        curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
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
    local cmd="$2"
    local status=0

    echo ""
    echo "→ $(t "正在处理" "Processing") $label"
    echo "  $cmd"

    set +e
    eval "$cmd"
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

    run_optional_command "$label" "brew install $package_name"
}

install_named_cli() {
    local cli_name="$1"

    case "$cli_name" in
        claude)
            if command -v claude >/dev/null 2>&1; then
                echo "✓ Claude Code"
                return 0
            fi
            run_optional_command "Claude Code" "curl -fsSL https://claude.ai/install.sh | sh"
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

enable_rtk_rewrite_hook() {
    local hook_source="$SOURCE_DIR/hooks/rtk-rewrite.sh"
    local claude_dir="$HOME/.claude"
    local hook_dir="$claude_dir/hooks"
    local hook_target="$hook_dir/rtk-rewrite.sh"
    local py_output=""

    if [ ! -f "$hook_source" ]; then
        echo "⚠ $(t "找不到 RTK hook 模板，跳过" "RTK hook template not found, skipping"): $hook_source"
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

pre = hooks.get("PreToolUse")
if not isinstance(pre, list):
    pre = []

exists = False
for entry in pre:
    if not isinstance(entry, dict):
        continue
    matcher = str(entry.get("matcher") or "")
    hook_items = entry.get("hooks")
    if matcher != "Bash" or not isinstance(hook_items, list):
        continue
    for hook in hook_items:
        if not isinstance(hook, dict):
            continue
        if str(hook.get("command") or "").strip() == hook_path:
            exists = True
            break
    if exists:
        break

if not exists:
    pre.append(
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": hook_path,
                }
            ],
        }
    )

hooks["PreToolUse"] = pre
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
        "rtk init --codex --global"
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

if [ "$ENSURE_NODE22" -eq 1 ]; then
    echo "⚠ $(t "将检查并安装 nvm / Node.js 22，这可能更新你的 shell 配置。" "This will check and install nvm / Node.js 22 and may update your shell config.")"
fi

# ── 1. 检查 Python3 ──
if ! command -v python3 &>/dev/null; then
    echo "❌ $(t "未找到 python3" "python3 not found")"
    if command -v brew &>/dev/null; then
        echo "   $(t "正在通过 brew 安装..." "Installing via brew...")"
        brew install python3
    else
        echo "   $(t "请先安装 Python 3" "Please install Python 3 first"): https://www.python.org/downloads/"
        exit 1
    fi
fi
echo "✓ Python3: $(python3 --version)"

if [ "$ENSURE_NODE22" -eq 1 ]; then
    ensure_node22
fi

# ── 2. 创建隔离的 Python 环境 ──
echo ""
echo "$(t "正在创建隔离环境..." "Creating isolated environment...")"
mkdir -p "$MMS_HOME"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet rich httpx tomli-w
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
# 复制所有 mms_*.py 确保完整
for f in "$SOURCE_DIR"/mms_*.py; do
    [ -f "$f" ] && cp "$f" "$MMS_HOME/"
done
[ -f "$SOURCE_DIR/config.example.toml" ] && cp "$SOURCE_DIR/config.example.toml" "$MMS_HOME/"
echo "✓ $(t "文件已复制到" "Files copied to") $MMS_HOME"
write_version_metadata
write_language_config

chmod +x "$MMS_HOME/ccs"
chmod +x "$MMS_HOME/mms"
[ -f "$MMS_HOME/statusline-command.sh" ] && chmod +x "$MMS_HOME/statusline-command.sh"

# ── 4. 修正入口的 Python 路径 ──
# 确保 shebang 指向隔离环境中的 python3
PYTHON_PATH="$VENV_DIR/bin/python"
sed -i.bak "1s|^#!.*|#!${PYTHON_PATH}|" "$MMS_HOME/ccs" && rm -f "$MMS_HOME/ccs.bak"
sed -i.bak "1s|^#!.*|#!${PYTHON_PATH}|" "$MMS_HOME/mms" && rm -f "$MMS_HOME/mms.bak"

# ── 4.5 可选安装：CLI / RTK ──
install_requested_clis
if [ "$INSTALL_RTK" -eq 1 ]; then
    install_optional_rtk || true
fi

# ── 5. 建立命令入口 ──
echo ""
mkdir -p "$BIN_DIR"

# 创建 symlink
ln -sf "$MMS_HOME/ccs" "$BIN_DIR/ccs"
ln -sf "$MMS_HOME/mms" "$BIN_DIR/mms"
echo "✓ $(t "命令已链接到" "Commands linked to") $BIN_DIR/mms $(t "和" "and") $BIN_DIR/ccs"

# 检查 PATH 是否包含 ~/.local/bin
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

    if [ "$WRITE_SHELL_RC" -eq 1 ]; then
        SHELL_RC=""
        if [ -f "$HOME/.zshrc" ]; then
            SHELL_RC="$HOME/.zshrc"
        elif [ -f "$HOME/.bashrc" ]; then
            SHELL_RC="$HOME/.bashrc"
        elif [ -f "$HOME/.bash_profile" ]; then
            SHELL_RC="$HOME/.bash_profile"
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

    if [ "$INSTALL_RTK" -eq 1 ]; then
        echo "  $(t "RTK rewrite 已配置到 Claude 的 PreToolUse:Bash。" "RTK rewrite has been wired into Claude PreToolUse:Bash.")"
        echo "  $(t "如果本机已有或本轮装上了 Codex CLI，也会顺手执行 rtk init --codex --global。" "If Codex CLI is already available or gets installed in this run, the installer also runs rtk init --codex --global.")"
        echo "  $(t "后续通过 MMS 启动的 Claude session 会自动继承这个 hook。" "Claude sessions launched through MMS will inherit this hook automatically.")"
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

    if [ "$LAUNCH_AFTER_INSTALL" -eq 1 ] && [ "$DID_LAUNCH" -eq 0 ]; then
        echo ""
        echo "$(t "启动 MMS..." "Launching MMS...")"
        "$BIN_DIR/mms" || true
    fi
else
    echo "❌ $(t "安装似乎失败了，请检查上面的错误信息" "Install appears to have failed. Please review the errors above")"
    exit 1
fi
