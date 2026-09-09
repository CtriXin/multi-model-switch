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
INSTALL_CHANNEL="stable"
REQUESTED_INSTALL_CHANNEL=""
LATEST_TAG_CACHE=""
LATEST_RELEASE_TAG_CACHE=""
DEV_CHANNEL_REF="${MMS_INSTALL_DEV_REF:-dev}"
CANARY_CHANNEL_REF="${MMS_INSTALL_CANARY_REF:-canary}"
DEFAULT_INSTALL_FALLBACK_TAG="${MMS_INSTALL_FALLBACK_TAG:-v3.3.1}"
CLAUDE_CLI_PACKAGE_SPEC="${CLAUDE_CLI_PACKAGE_SPEC:-@anthropic-ai/claude-code@latest}"
CODEX_CLI_PACKAGE_SPEC="${CODEX_CLI_PACKAGE_SPEC:-@openai/codex@latest}"
OPENCODE_CLI_PACKAGE_SPEC="${OPENCODE_CLI_PACKAGE_SPEC:-opencode-ai@latest}"
PI_CLI_PACKAGE_SPEC="${PI_CLI_PACKAGE_SPEC:-@earendil-works/pi-coding-agent@0.85.1}"
NVM_INSTALL_VERSION="${NVM_INSTALL_VERSION:-v0.40.3}"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11
BOOTSTRAP_PYTHON_VERSION="${MMS_BOOTSTRAP_PYTHON_VERSION:-3.13}"
PYTHON_CMD="${MMS_INSTALL_PYTHON:-${MMS_PYTHON:-}}"
INSTALL_LANG="zh"
WRITE_SHELL_RC=1
INSTALL_CODING_FONTS=1
RUN_SETUP=0
ENSURE_NODE22=0
LAUNCH_AFTER_INSTALL=0
INSTALL_CLI_LIST=""
INSTALL_CLI_EXPLICIT=0
CHECK_ONLY=0
CLEANUP_ONLY=0
LAUNCH_WEB_MODE="ask"
PRINT_ONLY_VERSION=0
DRY_RUN=0

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

release_track_id() {
    case "${REQUESTED_INSTALL_CHANNEL:-$INSTALL_CHANNEL}" in
        canary) printf "canary" ;;
        dev) printf "dev" ;;
        *)
            case "${INSTALL_REF:-$RESOLVED_INSTALL_REF}" in
                canary) printf "canary" ;;
                dev) printf "dev" ;;
                *) printf "stable" ;;
            esac
            ;;
    esac
}

release_track_version() {
    case "$(release_track_id)" in
        canary) printf "4.0.0-canary" ;;
        dev) printf "4.0.0-dev" ;;
        *)
            local ref="${INSTALL_REF:-$RESOLVED_INSTALL_REF}"
            if [[ "$ref" =~ ^v(4\.[0-9]+\.[0-9]+)$ ]]; then
                printf "%s" "${BASH_REMATCH[1]}"
            else
                printf "3.x-stable"
            fi
            ;;
    esac
}

release_track_label() {
    case "$(release_track_id)" in
        canary) printf "4.0 Canary Preview" ;;
        dev) printf "4.0 Dev Preview" ;;
        *)
            if [ "$(release_track_version)" = "3.x-stable" ]; then
                printf "3.x Stable"
            else
                printf "4.x Stable"
            fi
            ;;
    esac
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

bundled_session_asset_present() {
    local asset="$1"
    local assets_root="$MMS_HOME/assets/session-assets"
    case "$asset" in
        caveman)
            [ -f "$assets_root/packs/caveman/skills/caveman/SKILL.md" ] \
                && [ -f "$assets_root/packs/caveman/hooks/caveman-activate.js" ] \
                && [ -f "$assets_root/packs/caveman/hooks/caveman-mode-tracker.js" ]
            ;;
        token-saver)
            [ -f "$assets_root/skills/token-saver/SKILL.md" ]
            ;;
        toon)
            [ -f "$assets_root/skills/toon/SKILL.md" ]
            ;;
        web-access)
            [ -f "$assets_root/skills/web-access/SKILL.md" ]
            ;;
        weber)
            [ -f "$assets_root/skills/weber/SKILL.md" ]
            ;;
        agent-browser)
            [ -f "$assets_root/skills/agent-browser/SKILL.md" ]
            ;;
        nsr)
            [ -f "$MMS_HOME/hooks/nsr-builtin-hook.py" ] \
                && [ -f "$MMS_HOME/hooks/nsr-loop-hook.py" ] \
                && [ -f "$MMS_HOME/hooks/nsr-stop-wrapper.py" ] \
                && [ -f "$MMS_HOME/hooks/nsr-commit-gate.py" ] \
                && [ -f "$MMS_HOME/hooks/nsrctl.py" ] \
                && [ -f "$MMS_HOME/hooks/nsr-claude-hook.sh" ] \
                && [ -f "$MMS_HOME/hooks/nsr-codex-hook.sh" ]
            ;;
        *)
            return 1
            ;;
    esac
}

print_bundled_session_asset_status() {
    local asset label path mode
    local assets_root="$MMS_HOME/assets/session-assets"
    echo "$(t "内建 session assets" "Bundled session assets")"
    for asset in caveman token-saver toon web-access weber agent-browser nsr; do
        case "$asset" in
            caveman) label="Caveman"; path="$assets_root/packs/caveman"; mode="$(t "按 session 注入；默认随偏好/确认页启用" "session-local; enabled by preference/confirm screen")" ;;
            token-saver) label="token-saver"; path="$assets_root/skills/token-saver"; mode="$(t "默认可用" "available by default")" ;;
            toon) label="TOON"; path="$assets_root/skills/toon"; mode="$(t "默认可用" "available by default")" ;;
            web-access) label="web-access"; path="$assets_root/skills/web-access"; mode="$(t "默认可用" "available by default")" ;;
            weber) label="weber"; path="$assets_root/skills/weber"; mode="$(t "默认可用" "available by default")" ;;
            agent-browser) label="agent-browser"; path="$assets_root/skills/agent-browser"; mode="$(t "Codex/Antigravity 默认可用" "available by default for Codex/Antigravity")" ;;
            nsr) label="NSR"; path="$MMS_HOME/hooks/nsr-stop-wrapper.py"; mode="$(t "显式 /nsr 手动工作；自动 hook 已退休" "explicit /nsr manual work; automatic hooks retired")" ;;
        esac
        if bundled_session_asset_present "$asset"; then
            echo "✓ $label: $path ($mode)"
        else
            echo "• $(t "缺少内建 asset" "Bundled asset missing"): $label ($path)"
        fi
    done
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
  bash install.sh [--channel stable|dev|canary] [--dry-run] [--no-shell-rc] [--no-launch-web] [--launch-web] [--run-setup] [--ensure-node22] [--lang zh|en] [--install-cli name[,name2]]
  bash install.sh --ref <tag-or-branch>
  bash install.sh --stable
  bash install.sh --dev
  bash install.sh --canary
  bash install.sh --main
  bash install.sh --latest-tag
  bash install.sh --latest-release
  bash install.sh --version
  bash install.sh --check
  bash install.sh --cleanup-retired-packs

$(t "说明:" "Notes:")
  - $(t "不带参数就是给普通用户的正确安装：stable 通道、写入 shell PATH、装完询问是否打开 MMS Web" "Running it with no arguments is the right install for most people: the stable channel, PATH written to your shell, and a final question offering to open MMS Web")
  - $(t "--stable / --dev / --canary 是 --channel stable|dev|canary 的短别名" "--stable / --dev / --canary are short aliases for --channel stable|dev|canary")
  - $(t "--ref 可指定版本号或分支，例如 v1.2.0 / main / dev / canary" "--ref can pin a specific version or branch, for example v1.2.0 / main / dev / canary")
  - $(t "--version 仅显示当前脚本将安装的版本，不执行安装" "--version prints the version/ref this script would install without installing")
  - $(t "--check 仅检查当前环境与已安装状态，不执行安装" "--check inspects the current environment and installed state without installing")
  - $(t "--cleanup-retired-packs 只清理已退休可选包留下的 MMS 条目，不安装、不升级；每次正常安装也会自动做这件事" "--cleanup-retired-packs only removes MMS-written leftovers from retired optional packs without installing or upgrading; a normal install does this automatically too")
  - $(t "--dry-run 只显示本次会写入/安装/初始化什么，不创建 venv、不复制文件、不运行 setup" "--dry-run only prints what would be written/installed/initialized; it does not create a venv, copy files, or run setup")
  - $(t "--lang 可设置默认 UI 语言（zh / en）" "--lang sets the default UI language (zh / en)")
  - $(t "安装过程零交互：不询问可选包，也不询问 UI 语言；唯一的提问是装完之后要不要打开 MMS Web" "The install is non-interactive: no optional-pack questions and no UI language prompt; the only question comes after everything is installed and just offers to open MMS Web")
  - $(t "--launch-web 跳过提问直接打开，--no-launch-web 完全不打开；没有终端时不提问，只打印命令" "--launch-web opens it without asking, --no-launch-web never opens it; with no terminal available nothing is asked and the command is printed instead")
  - $(t "MMS Web 在后台运行，安装进程随即退出；PATH 默认写入 shell 配置，--no-shell-rc 可关闭" "MMS Web runs in the background and the installer exits right after; PATH is written to your shell config by default and --no-shell-rc turns that off")
  - $(t "pi 是必装项，pilot web 端依赖它；缺失的 claude/codex/opencode 会自动补装，已安装的不会被改动" "pi is mandatory because the pilot web app depends on it; missing claude/codex/opencode are installed automatically while existing ones are left untouched")
  - $(t "内建能力（网页访问、浏览器自动化、省 token 工具、Caveman、NSR）随 MMS 一起安装，只在 MMS 启动的会话里生效" "Built-in tools (web access, browser automation, token savers, Caveman, NSR) ship with MMS and only apply inside sessions MMS starts")
  - $(t "--install-cli 可显式指定要补装的 CLI：claude/codex/opencode/pi（逗号分隔）；能用 npm 的 CLI 均走 npm package" "--install-cli explicitly selects which CLIs to install: claude/codex/opencode/pi (comma-separated); CLIs with npm packages are installed through npm")
  - $(t "默认安装 Fira Code 与 JetBrains Mono 到用户字体目录，供 Web 字体选择使用；已装则跳过，--no-coding-fonts 可关闭" "Fira Code and JetBrains Mono are installed into the user font directory for the Web font picker; already-installed families are skipped, and --no-coding-fonts turns this off")
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
            claude|codex|opencode|pi)
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

    case "$ref" in
        v[0-9]*.[0-9]*.[0-9]*)
            archive_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/tags/${ref}.tar.gz"
            ;;
        *)
            archive_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${ref}.tar.gz"
            ;;
    esac

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
    local track_id
    local track_version
    local track_label
    track_id="$(release_track_id)"
    track_version="$(release_track_version)"
    track_label="$(release_track_label)"
    mkdir -p "$(dirname "$VERSION_META_PATH")"
    "$(_python_bin)" - "$VERSION_META_PATH" "$RESOLVED_INSTALL_REF" "$INSTALL_CHANNEL" "$INSTALL_LANG" "$track_id" "$track_version" "$track_label" <<'PY'
import json
import re
import sys
from datetime import datetime, timezone

path, resolved_ref, install_channel, preferred_language, track_id, track_version, track_label = sys.argv[1:8]
resolved_ref = str(resolved_ref or "").strip()
installed_version = resolved_ref if re.fullmatch(r"v\d+\.\d+\.\d+", resolved_ref) else ""
preferred_language = "en" if str(preferred_language).strip().lower().startswith("en") else "zh"

payload = {
    "installed_ref": resolved_ref,
    "installed_version": installed_version,
    "install_channel": install_channel,
    "release_track": track_id,
    "release_track_version": track_version,
    "release_track_label": track_label,
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
    if [ -z "$ref" ] && { [ "$INSTALL_CHANNEL" = "stable" ] || [ "$INSTALL_CHANNEL" = "latest-release" ]; }; then
        ref="$(resolve_latest_release_tag || true)"
        if [ -n "$ref" ]; then
            echo "✓ stable release: $ref"
        else
            echo "⚠ $(t "获取 stable/latest release 失败，回退到最新 tag" "Failed to fetch stable/latest release, falling back to latest tag")"
            INSTALL_CHANNEL="latest-tag"
        fi
    fi
    if [ -z "$ref" ] && [ "$INSTALL_CHANNEL" = "dev" ]; then
        ref="$DEV_CHANNEL_REF"
    fi
    if [ -z "$ref" ] && [ "$INSTALL_CHANNEL" = "canary" ]; then
        ref="$CANARY_CHANNEL_REF"
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

install_named_cli() {
    local cli_name="$1"
    local cli_path=""
    local command_name=""
    local label=""
    local package_spec=""

    case "$cli_name" in
        pi)
            command_name="pi"
            label="Pi coding agent"
            package_spec="$PI_CLI_PACKAGE_SPEC"
            if ! command -v node >/dev/null 2>&1 || ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=19)?0:1)' >/dev/null 2>&1; then
                ensure_nvm_node22 || return 1
            fi
            ;;
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

# Coding faces the Web UI offers in its font picker. Both are SIL OFL, so they
# can be redistributed; the picker only lists families that are actually
# installed, so without these the options simply never appear.
CODING_FONT_SPECS=(
    "Fira Code|FiraCode-Regular|https://github.com/tonsky/FiraCode/releases/download/6.2/Fira_Code_v6.2.zip|ttf/FiraCode-*.ttf"
    "JetBrains Mono|JetBrainsMono-Regular|https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip|fonts/ttf/JetBrainsMono-*.ttf"
)

user_font_dir() {
    if [ "$(uname -s)" = "Darwin" ]; then
        printf "%s/Library/Fonts" "$REAL_HOME"
    else
        printf "%s/.local/share/fonts" "$REAL_HOME"
    fi
}

install_coding_fonts() {
    local font_dir="" spec="" label="" probe="" url="" glob="" tmp="" archive=""
    local installed=0 failed=0

    if [ "$INSTALL_CODING_FONTS" != "1" ]; then
        return 0
    fi
    font_dir="$(user_font_dir)"

    for spec in "${CODING_FONT_SPECS[@]}"; do
        IFS='|' read -r label probe url glob <<< "$spec"
        # Already present, from this installer or from anywhere else.
        if compgen -G "$font_dir/$probe*.ttf" > /dev/null 2>&1; then
            continue
        fi
        if [ "$DRY_RUN" = "1" ]; then
            echo "• $(t "将安装编程字体" "would install coding font"): $label -> $font_dir"
            continue
        fi
        tmp="$(mktemp -d)" || { failed=$((failed + 1)); continue; }
        archive="$tmp/font.zip"
        if curl -fsSL --max-time 120 "$url" -o "$archive" \
            && unzip -qo "$archive" -d "$tmp" > /dev/null 2>&1; then
            mkdir -p "$font_dir"
            # shellcheck disable=SC2086
            if cp $tmp/$glob "$font_dir/" 2>/dev/null; then
                # Keep upstream font license notices alongside the installed fonts.
                local license_file
                for license_file in "$tmp/OFL.txt" "$tmp/OFL.md" "$tmp/LICENSE" "$tmp/LICENSE.txt"; do
                    [ ! -f "$license_file" ] || cp "$license_file" "$font_dir/$probe-LICENSE.txt"
                done
                installed=$((installed + 1))
            else
                failed=$((failed + 1))
            fi
        else
            failed=$((failed + 1))
        fi
        rm -rf "$tmp"
    done

    if [ "$installed" -gt 0 ]; then
        command -v fc-cache > /dev/null 2>&1 && fc-cache -f > /dev/null 2>&1
        echo "✓ $(t "已安装 $installed 组编程字体到 $font_dir" "installed $installed coding font families into $font_dir")"
    fi
    if [ "$failed" -gt 0 ]; then
        echo "⚠ $(t "$failed 组编程字体未安装完成；不影响 MMS，可稍后重试或手动安装。" "$failed coding font families did not install; MMS is unaffected, retry or install them by hand later.")"
    fi
    return 0
}

install_requested_clis() {
    local cli_name=""

    if [ -z "$INSTALL_CLI_LIST" ]; then
        return 0
    fi

    echo ""
    echo "$(t "正在安装所需 CLI..." "Installing required CLIs...")"

    IFS=',' read -r -a _requested_cli_items <<< "$INSTALL_CLI_LIST"
    for cli_name in "${_requested_cli_items[@]}"; do
        install_named_cli "$cli_name" || true
    done
}

cli_label_for() {
    case "$1" in
        claude) printf "Claude Code" ;;
        codex) printf "Codex CLI" ;;
        opencode) printf "OpenCode CLI" ;;
        pi) printf "Pi coding agent" ;;
        *) printf "%s" "$1" ;;
    esac
}

# Non-interactive default: pi is required by the pilot web app, and any missing
# claude/codex/opencode is filled in. Already-installed CLIs are left untouched.
resolve_default_cli_installs() {
    local cli_name=""
    local cli_path=""

    echo ""
    echo "$(t "检查所需 CLI..." "Checking required CLIs...")"

    for cli_name in pi claude codex opencode; do
        if cli_path="$(find_cli_binary "$cli_name" 2>/dev/null)"; then
            echo "  ✓ $(t "已检测到" "Detected"): $(cli_label_for "$cli_name") ($cli_path)"
            continue
        fi
        if [ "$cli_name" != "pi" ] && [ "$INSTALL_CLI_EXPLICIT" -eq 1 ]; then
            echo "  • $(t "未安装，本次按 --install-cli 跳过" "Not installed; skipped because --install-cli was given"): $(cli_label_for "$cli_name")"
            continue
        fi
        echo "  • $(t "未检测到，将自动安装" "Not found, will install"): $(cli_label_for "$cli_name")"
        append_csv_item "$cli_name"
    done
}

print_cli_install_status() {
    local cli_name=""
    local cli_path=""

    for cli_name in pi claude codex opencode; do
        if cli_path="$(find_cli_binary "$cli_name" 2>/dev/null)"; then
            echo "✓ $(cli_label_for "$cli_name") $(t "已安装" "installed"): $cli_path"
        elif [ "$cli_name" = "pi" ]; then
            echo "• $(cli_label_for "$cli_name") $(t "未安装；pilot web 端需要它，重跑安装器即可补装" "not installed; the pilot web app needs it, rerun the installer to add it")"
        else
            echo "• $(cli_label_for "$cli_name") $(t "未安装；重跑安装器会自动补装" "not installed; rerunning the installer adds it")"
        fi
    done
}

# Pi runs through scripts/pi-cli-wrapper.sh, which resolves the agent from a
# local npx cache. Warm that cache with the same pinned spec used for the global
# install so the first pilot launch is not blocked on a download.
warm_pi_runtime_cache() {
    local cache_dir="${MMS_PI_NPX_CACHE:-$MMS_HOME/.ai/cache/pi-npx}"

    if [ ! -x "$MMS_HOME/scripts/pi-cli-wrapper.sh" ]; then
        echo "⚠ $(t "找不到 pi wrapper，跳过运行时预热" "pi wrapper not found, skipping runtime warmup"): $MMS_HOME/scripts/pi-cli-wrapper.sh"
        return 0
    fi

    if ! command -v npx >/dev/null 2>&1; then
        echo "⚠ $(t "缺少 npx，跳过 pi 运行时预热；pilot 首次启动时会自行下载" "npx is missing, skipping pi runtime warmup; the first pilot launch will download it")"
        return 0
    fi

    echo ""
    echo "$(t "正在准备 pi 运行环境，第一次会下载，请稍候..." "Preparing the pi runtime; the first run downloads it, please wait...")"
    mkdir -p "$cache_dir"
    if NPM_CONFIG_UPDATE_NOTIFIER=false npx -y --cache "$cache_dir" "$PI_CLI_PACKAGE_SPEC" --version >/dev/null 2>&1; then
        echo "✓ $(t "pi 运行时 cache 已就绪" "pi runtime cache ready"): $cache_dir"
        return 0
    fi

    echo "⚠ $(t "pi 运行时预热未成功；pilot 首次启动时会重试下载" "pi runtime warmup did not succeed; the first pilot launch retries the download")"
    return 0
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

raw_entries = hooks.get(hook_event)
entries = raw_entries if isinstance(raw_entries, list) else []
cleaned_entries = []
for entry in entries:
    if not isinstance(entry, dict):
        cleaned_entries.append(entry)
        continue
    hook_items = entry.get("hooks")
    if not isinstance(hook_items, list):
        cleaned_entries.append(entry)
        continue
    kept_hooks = []
    for hook in hook_items:
        if not isinstance(hook, dict):
            kept_hooks.append(hook)
            continue
        command = normalize(hook.get("command"))
        if command in dedupe_commands:
            continue
        kept_hooks.append(hook)
    if kept_hooks:
        cleaned_entry = dict(entry)
        cleaned_entry["hooks"] = kept_hooks
        cleaned_entries.append(cleaned_entry)

cleaned_entries.append(
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

hooks[hook_event] = cleaned_entries
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

cleanup_legacy_global_session_hooks() {
    # Read-only plan. Global registration changes require explicit review/CAS.
    "$(_python_bin)" "$SOURCE_DIR/mms_hook_retirement.py" \
        --file "$REAL_HOME/.claude/settings.json" \
        --file "$REAL_HOME/.codex/hooks.json" || {
        echo "Optional retired-hook cleanup plan unavailable; settings left unchanged." >&2
        return 0
    }
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

# An explicit --ref pins a version outright, so reporting a channel there would
# contradict the pinned ref.
install_channel_label() {
    if [ -n "$INSTALL_REF" ]; then
        printf "pinned-ref"
    else
        printf "%s" "$INSTALL_CHANNEL"
    fi
}

print_planned_version() {
    ensure_install_ref_resolved
    echo "$(t "计划安装版本" "Planned install ref"): ${RESOLVED_INSTALL_REF:-local-source}"
    echo "$(t "安装通道" "Install channel"): $(install_channel_label)"
}

# A newcomer running the plain command does not need the channel/ref matrix;
# one line saying what is being installed is enough. The full overview stays for
# --version, --check, and anyone who picked a channel or ref explicitly.
print_install_headline() {
    local installed_ref=""

    if [ -n "$REQUESTED_INSTALL_CHANNEL" ] || [ -n "$INSTALL_REF" ]; then
        print_version_overview
        return 0
    fi

    ensure_install_ref_resolved
    installed_ref="$(current_installed_ref || true)"
    if [ -z "$installed_ref" ]; then
        echo "$(t "安装最新版本" "Installing the latest version"): ${RESOLVED_INSTALL_REF:-local-source}"
    elif [ "$installed_ref" = "${RESOLVED_INSTALL_REF:-}" ]; then
        echo "$(t "已经是最新版本，将重新安装" "Already on the latest version, reinstalling it"): ${installed_ref}"
    else
        echo "$(t "升级到最新版本" "Upgrading to the latest version"): ${installed_ref} → ${RESOLVED_INSTALL_REF:-local-source}"
    fi
    return 0
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
    echo "  $(t "稳定版（Stable/latest release）" "Stable release (latest release)"): ${stable_ref:-$(t "未获取" "unavailable")}"
    echo "  $(t "Dev ref" "Dev ref"): $DEV_CHANNEL_REF"
    echo "  $(t "Canary ref" "Canary ref"): $CANARY_CHANNEL_REF"
    echo "  $(t "版本轨道" "Version track"): $(release_track_label) ($(release_track_version))"
    echo "  $(t "线上最新（latest tag）" "Latest upstream tag (latest tag)"): ${latest_tag_ref:-$(t "未获取" "unavailable")}"
    echo "  $(t "本次准备安装" "Planned install ref"): ${RESOLVED_INSTALL_REF:-local-source}"
    echo "  $(t "安装通道" "Install channel"): $(install_channel_label)"
}

legacy_config_has_route_candidates() {
    "$(_python_bin)" - "$REAL_HOME/.config/mms" <<'PY' >/dev/null 2>&1
import sys
import tomllib
from pathlib import Path

root = Path(sys.argv[1]).expanduser()
config_path = root / "config.toml"
if not config_path.exists():
    raise SystemExit(1)
try:
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)

providers = config.get("providers")
if not isinstance(providers, list):
    raise SystemExit(1)

for provider in providers:
    if not isinstance(provider, dict) or provider.get("enabled") is False:
        continue
    for key in ("fallback_models", "extra_models"):
        models = provider.get(key)
        if isinstance(models, list) and any(str(item).strip() for item in models):
            raise SystemExit(0)
raise SystemExit(1)
PY
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
    if [ -L "$BIN_DIR/mmf" ]; then
        echo "✓ $(t "已存在 mmf preview 命令链接" "mmf preview symlink present"): $BIN_DIR/mmf"
    else
        echo "• $(t "mmf preview 命令链接尚未创建" "mmf preview symlink not created yet"): $BIN_DIR/mmf"
    fi
    if [ -L "$BIN_DIR/mmc" ]; then
        echo "• $(t "检测到 retired mmc 命令链接；下次安装会移除 MMS-owned 链接" "Retired mmc command link detected; the next install removes MMS-owned links"): $BIN_DIR/mmc"
    fi
    if [ -L "$BIN_DIR/mmslogs" ]; then
        echo "✓ $(t "已存在 mmslogs 命令链接" "mmslogs symlink present"): $BIN_DIR/mmslogs"
    else
        echo "• $(t "mmslogs 命令链接尚未创建" "mmslogs symlink not created yet"): $BIN_DIR/mmslogs"
    fi


    print_cli_install_status

    print_bundled_session_asset_status
}


print_dry_run_plan() {
    echo ""
    echo "===================================="
    echo "  $(t "DRY RUN：不会写入任何文件" "DRY RUN: no files will be written")"
    echo "===================================="
    echo "• $(t "MMS 安装目录" "MMS install dir"): $MMS_HOME"
    echo "• $(t "命令目录" "command dir"): $BIN_DIR"
    echo "• $(t "虚拟环境" "virtualenv"): $VENV_DIR"
    echo "• $(t "配置目录" "config dir"): $REAL_HOME/.config/mms"
    echo "• $(t "会安装内建能力：网页访问、浏览器自动化、省 token 工具、Caveman、NSR" "would install the built-in tools: web access, browser automation, token savers, Caveman, NSR")"

    if [ -n "$INSTALL_CLI_LIST" ]; then
        echo "• $(t "会安装 CLI" "would install CLI"): $INSTALL_CLI_LIST"
    fi
    echo "• $(t "会预热 pi 运行时 cache" "would warm the pi runtime cache"): $MMS_HOME/.ai/cache/pi-npx"
    if [ "$WRITE_SHELL_RC" -eq 1 ]; then
        echo "• $(t "会把 ~/.local/bin 写入 shell PATH 配置" "would add ~/.local/bin to your shell PATH config")"
    fi
    case "$LAUNCH_WEB_MODE" in
        always) echo "• $(t "会直接后台启动 MMS Web 并打开浏览器" "would start MMS Web in the background and open the browser")" ;;
        never) echo "• $(t "不会启动 MMS Web" "would not start MMS Web")" ;;
        *) echo "• $(t "装完会询问是否打开 MMS Web；同意则后台启动并打开浏览器" "would ask whether to open MMS Web and, if accepted, start it in the background and open the browser")" ;;
    esac
    echo "• $(t "会清理旧版本装过的可选包，以及写进各 agent 目录的 offduty/onduty/nsr" "would clean up the optional packs older versions installed, plus the offduty/onduty/nsr entries written into each agent home")"
    echo "  $(t "仅备份移走有 MMS 来源凭据的条目，同名自定义内容和全局配置保留" "Only verified MMS entries are archived; same-name custom content and global settings are preserved")"
    if [ "$INSTALL_CODING_FONTS" = "1" ]; then
        echo "• $(t "会把 Fira Code 与 JetBrains Mono 安装到 $(user_font_dir)（已装则跳过，--no-coding-fonts 关闭）" "would install Fira Code and JetBrains Mono into $(user_font_dir); already-installed families are skipped, --no-coding-fonts turns this off")"
    fi

    echo ""
    echo "✓ $(t "dry-run 完成：未创建 venv，未复制文件，未安装任何 CLI。" "dry-run complete: no venv created, no files copied, no CLI installed.")"
}

# ── MMS Web launch ──
# The installer ends by offering to open MMS Web. The server is started
# detached so the install process exits immediately; the browser is opened by
# the server itself. This is the only question the installer ever asks, it is
# asked after everything is installed, and it never changes what gets installed.
MMS_WEB_DEFAULT_PORT="${MMS_WEB_PORT_BASE:-8765}"
MMS_WEB_PORT_SEARCH_LIMIT=20

# `curl | bash` leaves stdin pointing at the script, so the prompt has to talk
# to the terminal directly. No terminal means no question: we just print how to
# start MMS Web later.
web_prompt_available() {
    [ -r /dev/tty ] && [ -w /dev/tty ] || return 1
    { : < /dev/tty > /dev/tty; } 2>/dev/null
}

confirm_open_web() {
    local answer=""

    web_prompt_available || return 1
    printf "%s" "$(t "现在打开 MMS Web 吗？[Y/n]: " "Open MMS Web now? [Y/n]: ")" > /dev/tty
    IFS= read -r answer < /dev/tty || return 1
    answer="$(printf "%s" "$answer" | tr '[:upper:]' '[:lower:]' | xargs)"
    case "$answer" in
        n|no) return 1 ;;
        *) return 0 ;;
    esac
}

# Report the port of an MMS Web instance that is already serving, if any.
running_mms_web_port() {
    "$(_python_bin)" - "$MMS_WEB_DEFAULT_PORT" "$MMS_WEB_PORT_SEARCH_LIMIT" "$MMS_HOME" "${XDG_DATA_HOME:-$REAL_HOME/.local/share}/mms-web/config" <<'PY'
import hashlib
import re
from pathlib import Path
import http.client
import sys

start = int(sys.argv[1])
limit = int(sys.argv[2])
root, config = (Path(p).resolve() for p in sys.argv[3:5])
version_file = root / "mms_version.py"
match = re.search(r'VERSION = "([^"]+)"', version_file.read_text()) if version_file.exists() else None
version = match.group(1) if match else ""
identity = hashlib.sha256(f"{root}|{config}|{version}".encode()).hexdigest()
for port in range(start, start + limit):
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.4)
        conn.request("HEAD", "/")
        response = conn.getresponse()
    except Exception:
        continue
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if response.status == 200 and response.getheader("X-MMS-Web-Identity") == identity:
        print(port)
        break
PY
}

# mms-web binds a fixed port and fails hard when it is taken, so the installer
# picks a free one instead of letting the last install step die on an OSError.
find_free_web_port() {
    "$(_python_bin)" - "$MMS_WEB_DEFAULT_PORT" "$MMS_WEB_PORT_SEARCH_LIMIT" <<'PY'
import socket
import sys

start = int(sys.argv[1])
limit = int(sys.argv[2])
for port in range(start, start + limit):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            continue
    print(port)
    break
PY
}

open_url_in_browser() {
    "$(_python_bin)" - "$1" <<'PY'
import sys
import webbrowser

webbrowser.open(sys.argv[1])
PY
}

wait_for_mms_web() {
    local port="$1"

    "$(_python_bin)" - "$port" <<'PY'
import http.client
import sys
import time

port = int(sys.argv[1])
deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
        conn.request("HEAD", "/")
        response = conn.getresponse()
        healthy = response.status == 200 and str(response.getheader("Server") or "").startswith("MMSWeb")
        conn.close()
        if not healthy:
            time.sleep(0.4)
            continue
    except Exception:
        time.sleep(0.4)
        continue
    raise SystemExit(0)
raise SystemExit(1)
PY
}

start_mms_web_detached() {
    local state_root="${XDG_DATA_HOME:-$REAL_HOME/.local/share}/mms-web"
    local log_file="$MMS_HOME/logs/mms-web.log"
    local port=""
    local running=""

    if [ ! -x "$BIN_DIR/mms-web" ]; then
        echo "⚠ $(t "找不到 mms-web 命令，跳过打开" "mms-web command not found, skipping launch"): $BIN_DIR/mms-web"
        return 1
    fi

    running="$(running_mms_web_port || true)"
    if [ -n "$running" ]; then
        echo "✓ $(t "MMS Web 已在运行，直接打开" "MMS Web is already running, opening it"): http://127.0.0.1:$running"
        open_url_in_browser "http://127.0.0.1:$running" || true
        return 0
    fi

    port="$(find_free_web_port || true)"
    if [ -z "$port" ]; then
        echo "⚠ $(t "找不到可用端口，跳过打开；稍后可手动运行" "No free port found, skipping launch; run it manually later"): mms-web --open"
        return 1
    fi

    mkdir -p "$state_root" "$(dirname "$log_file")"
    nohup "$BIN_DIR/mms-web" \
        --state-root "$state_root" \
        --port "$port" \
        --open \
        >"$log_file" 2>&1 &
    local web_pid=$!
    disown 2>/dev/null || true

    if wait_for_mms_web "$port"; then
        echo "✓ $(t "MMS Web 已启动" "MMS Web is running"): http://127.0.0.1:$port"
        echo "  $(t "它在后台运行，安装进程已结束。浏览器没自动打开时手动访问上面的地址。" "It runs in the background and the installer is done. Open the address above manually if the browser did not.")"
        echo "  $(t "停止:" "Stop it with:") kill $web_pid"
        return 0
    fi

    echo "⚠ $(t "MMS Web 启动超时，日志在" "MMS Web did not come up in time, log at"): $log_file"
    echo "  $(t "可手动运行:" "Run it manually:") mms-web --open"
    return 1
}

offer_mms_web() {
    case "$LAUNCH_WEB_MODE" in
        never)
            return 0
            ;;
        always)
            start_mms_web_detached || true
            return 0
            ;;
    esac

    if ! web_prompt_available; then
        echo "  $(t "打开 Web 端:" "Open the web app:") mms-web --open"
        return 0
    fi

    echo ""
    if confirm_open_web; then
        start_mms_web_detached || true
    else
        echo "  $(t "以后随时可以运行:" "You can run this any time:") mms-web --open"
    fi
    return 0
}

# ── Retired optional packs ──
# RTK / BrainKeeper / Map / CodeGraph / global token-saver / global TOON /
# ops-env-safe / ECC / OMC were removed from the installer. Every install
# unbinds what MMS itself wrote for them, so machines upgrading from an older
# version stop carrying them. This never touches third-party binaries (rtk,
# codegraph, brainkeeper, node, jq) and never deletes a file MMS did not write:
# every target is verified by an MMS marker, an MMS-owned symlink target, or an
# MMS-owned directory.
RETIRED_PACK_CLEANUP_COUNT=0
RETIRED_PACK_BACKUP=""

archive_retired_entry() {
    local target="$1"
    [ -n "$RETIRED_PACK_BACKUP" ] || RETIRED_PACK_BACKUP="$(mktemp -d "$MMS_HOME/retired-backup.XXXXXX")"
    local relative="${target#"$REAL_HOME"/}"
    mkdir -p "$RETIRED_PACK_BACKUP/$(dirname "$relative")"
    mv "$target" "$RETIRED_PACK_BACKUP/$relative"
}

_note_retired_removal() {
    RETIRED_PACK_CLEANUP_COUNT=$((RETIRED_PACK_CLEANUP_COUNT + 1))
    echo "  - $(t "已移除" "Removed"): $1"
}

# Delete a file only when it carries one of the given MMS markers.
remove_retired_marked_file() {
    local target="$1"
    shift
    local marker=""

    [ -f "$target" ] || return 0
    for marker in "$@"; do
        if grep -Fq "$marker" "$target" 2>/dev/null; then
            archive_retired_entry "$target"
            _note_retired_removal "$target"
            return 0
        fi
    done
    echo "  • $(t "检测到自定义内容，保留不动" "Custom content detected, left unchanged"): $target"
    return 0
}

# Delete a skill entry that is either an MMS-owned symlink or a directory whose
# SKILL.md carries the MMS-managed marker.
remove_retired_skill_entry() {
    local target="$1"
    local vendor_suffix="$2"
    local marker="$3"
    local link_target=""

    if [ -L "$target" ]; then
        link_target="$(readlink "$target" 2>/dev/null || true)"
        case "$link_target" in
            "$MMS_HOME/vendor/$vendor_suffix"|"$MMS_HOME/vendor/$vendor_suffix/")
                archive_retired_entry "$target"
                _note_retired_removal "$target"
                ;;
            *)
                echo "  • $(t "非 MMS 链接，保留不动" "Not an MMS link, left unchanged"): $target"
                ;;
        esac
        return 0
    fi

    [ -d "$target" ] || return 0
    if [ -f "$target/SKILL.md" ] && grep -Fq "Managed by MMS optional $vendor_suffix pack" "$target/SKILL.md" 2>/dev/null; then
        archive_retired_entry "$target"
        _note_retired_removal "$target"
        return 0
    fi
    echo "  • $(t "检测到自定义 skill，保留不动" "Custom skill detected, left unchanged"): $target"
    return 0
}

# Archive only the exact skill link written by the retired installer.
# A custom target under MMS_HOME is not proof of ownership.
remove_retired_mms_symlink() {
    local target="$1"
    local link_target=""
    local expected="$MMS_HOME/vendor/handover"
    case "${target##*/}" in
        offduty|onduty) expected="$expected/aliases/${target##*/}" ;;
        handover) ;;
        *) return 0 ;;
    esac

    [ -L "$target" ] || return 0
    link_target="$(readlink "$target" 2>/dev/null || true)"
    case "$link_target" in
        "$expected")
            archive_retired_entry "$target"
            _note_retired_removal "$target"
            ;;
        *)
            echo "  • $(t "非 MMS 链接，保留不动" "Not an MMS link, left unchanged"): $target"
            ;;
    esac
    return 0
}

# Delete a directory MMS created inside its own install root.
remove_retired_mms_dir() {
    local target="$1"

    [ -d "$target" ] || return 0
    case "$target" in
        "$MMS_HOME"/*)
            archive_retired_entry "$target"
            _note_retired_removal "$target"
            ;;
        *)
            echo "  • $(t "目录不在 MMS 安装根下，保留不动" "Directory is outside the MMS install root, left unchanged"): $target"
            ;;
    esac
    return 0
}

# A generic hook filename, MCP key or Skill name does not establish MMS ownership.
# Leave global settings/hooks and the real config tree for the user's own review.
cleanup_retired_optional_packs() {
    local command_dir="$REAL_HOME/.claude/commands"
    local hook_dir="$REAL_HOME/.claude/hooks"
    local mirror_dir="$REAL_HOME/auto-skills/installed-skills"
    local wrapper=""
    local agent_dir=""
    local skill=""

    RETIRED_PACK_CLEANUP_COUNT=0
    mkdir -p "$MMS_HOME"
    echo ""
    echo "$(t "正在清理旧版本装过、现在已经不再需要的东西..." "Cleaning up things older versions installed that are no longer needed...")"

    # ~/.local/bin wrappers written by the token-saver / TOON / BrainKeeper packs
    for wrapper in token-saver mms-context token-gain mms-gain mms-toon; do
        remove_retired_marked_file "$BIN_DIR/$wrapper" \
            "Managed by MMS optional script wrapper" \
            "Managed by MMS optional token-saver pack"
    done
    for wrapper in bk brainkeeper; do
        remove_retired_marked_file "$BIN_DIR/$wrapper" \
            "Managed by MMS BrainKeeper context pack"
    done

    # Claude slash commands written by the BrainKeeper / ops-env-safe packs
    for wrapper in distill contextzip cz cr; do
        remove_retired_marked_file "$command_dir/$wrapper.md" \
            "Managed by MMS BrainKeeper context pack"
    done
    remove_retired_marked_file "$command_dir/ops-env-safe.md" \
        "Managed by MMS optional ops-env-safe pack"

    # Global skill links for the packs that are now bundled session assets only
    remove_retired_skill_entry "$REAL_HOME/.codex/skills/token-saver" "token-saver" "name: token-saver"
    remove_retired_skill_entry "$REAL_HOME/.claude/skills/token-saver" "token-saver" "name: token-saver"
    remove_retired_skill_entry "$mirror_dir/token-saver" "token-saver" "name: token-saver"
    remove_retired_skill_entry "$REAL_HOME/.codex/skills/toon" "toon" "name: toon"
    remove_retired_skill_entry "$REAL_HOME/.claude/skills/toon" "toon" "name: toon"
    remove_retired_skill_entry "$mirror_dir/toon" "toon" "name: toon"
    remove_retired_skill_entry "$REAL_HOME/.codex/skills/ops-env-safe" "ops-env-safe" "name: ops-env-safe"

    # MMS-managed Claude agent packs
    remove_retired_mms_dir "$MMS_HOME/agent-packs/everything-claude-code"
    remove_retired_mms_dir "$MMS_HOME/agent-packs/oh-my-claudecode"
    if [ -d "$MMS_HOME/agent-packs" ] && [ -z "$(ls -A "$MMS_HOME/agent-packs" 2>/dev/null)" ]; then
        rmdir "$MMS_HOME/agent-packs" 2>/dev/null || true
    fi

    # offduty / onduty / handover and the /nsr command used to be written into
    # every agent host's global directory. They are no longer installed, so an
    # install also takes back what MMS itself wrote there.
    for agent_dir in \
        "$REAL_HOME/.agents" \
        "$REAL_HOME/.claude" \
        "$REAL_HOME/.codex" \
        "$REAL_HOME/.config/opencode" \
        "$REAL_HOME/.opencode"; do
        for skill in handover offduty onduty; do
            remove_retired_mms_symlink "$agent_dir/skills/$skill"
        done
        remove_retired_marked_file "$agent_dir/commands/nsr.md" \
            "Managed by MMS builtin NSR"
    done

    if [ -n "$RETIRED_PACK_BACKUP" ]; then
        echo "  $(t "原文件已备份到" "Original entries backed up to"): $RETIRED_PACK_BACKUP"
    fi
    echo "  $(t "全局 hooks、MCP 设置及真实配置目录保留，请按需手动检查。" "Global hooks, MCP settings and the real config tree are preserved for manual review.")"

    if [ "$RETIRED_PACK_CLEANUP_COUNT" -eq 0 ]; then
        echo "✓ $(t "没有需要清理的旧可选包" "No retired optional packs to clean up")"
    else
        echo "✓ $(t "已清理旧可选包条目数" "Retired optional pack entries cleaned"): $RETIRED_PACK_CLEANUP_COUNT"
        echo "  $(t "第三方二进制（rtk / codegraph / brainkeeper / node / jq）未被卸载。" "Third-party binaries (rtk / codegraph / brainkeeper / node / jq) were not uninstalled.")"
    fi

    return 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --write-shell-rc)
            WRITE_SHELL_RC=1
            ;;
        --no-coding-fonts)
            INSTALL_CODING_FONTS=0
            ;;
        --no-shell-rc)
            WRITE_SHELL_RC=0
            ;;
        --launch-web)
            LAUNCH_WEB_MODE="always"
            ;;
        --no-launch-web)
            LAUNCH_WEB_MODE="never"
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
        --install-rtk|--install-brainkeeper-context|--install-mindkeeper-context|--install-map|--install-codegraph|--install-token-saver|--install-toon|--install-ops-env-safe|--install-ecc|--install-omc|--install-agent-packs)
            echo "⚠ $(t "该可选包已从安装器移除，本次忽略" "This optional pack was removed from the installer and is ignored"): $1"
            ;;
        --brainkeeper-ref|--mindkeeper-ref|--map-ref|--codegraph-package|--ecc-ref|--omc-ref)
            echo "⚠ $(t "该可选包参数已从安装器移除，本次忽略" "This optional-pack argument was removed from the installer and is ignored"): $1"
            shift || true
            ;;
        --install-cli)
            shift
            parse_install_cli_arg "${1:-}"
            INSTALL_CLI_EXPLICIT=1
            ;;
        --channel)
            shift
            if [[ -z "${1:-}" ]] || [[ "$1" != "stable" && "$1" != "dev" && "$1" != "canary" ]]; then
                echo "❌ $(t "--channel 只支持 stable / dev / canary" "--channel only supports stable / dev / canary")"
                usage
                exit 1
            fi
            INSTALL_REF=""
            INSTALL_CHANNEL="$1"
            REQUESTED_INSTALL_CHANNEL="$1"
            ;;
        --stable)
            INSTALL_REF=""
            INSTALL_CHANNEL="stable"
            REQUESTED_INSTALL_CHANNEL="stable"
            ;;
        --dev)
            INSTALL_REF=""
            INSTALL_CHANNEL="dev"
            REQUESTED_INSTALL_CHANNEL="dev"
            ;;
        --canary)
            INSTALL_REF=""
            INSTALL_CHANNEL="canary"
            REQUESTED_INSTALL_CHANNEL="canary"
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
        --cleanup-retired-packs)
            CLEANUP_ONLY=1
            ;;
        --dry-run)
            DRY_RUN=1
            ;;
        --lang)
            shift
            if [[ -z "${1:-}" ]] || [[ "$1" != "zh" && "$1" != "en" ]]; then
                echo "❌ $(t "--lang 只支持 zh 或 en" "--lang only supports zh or en")"
                usage
                exit 1
            fi
            INSTALL_LANG="$1"
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

if [ "$CLEANUP_ONLY" -eq 1 ]; then
    cleanup_retired_optional_packs
    exit 0
fi

resolve_default_cli_installs

echo "===================================="
echo "  $(t "MMS 一键安装" "MMS one-line installer")"
echo "===================================="
echo ""
print_install_headline
echo ""

if [ -n "$INSTALL_CLI_LIST" ]; then
    echo "• $(t "附带安装 CLI" "Optional CLI install"): $INSTALL_CLI_LIST"
fi

echo "• $(t "内建能力" "Built-in tools"): $(t "网页访问、浏览器自动化、省 token 工具等随 MMS 一起安装" "web access, browser automation, token-saving tools and more come with MMS")"
echo "  $(t "它们只在 MMS 启动的会话里生效，不会改动你已有的全局配置。" "They only apply inside sessions MMS starts, and none of your existing global config is modified.")"

if [ "$ENSURE_NODE22" -eq 1 ]; then
        echo "⚠ $(t "将优先复用现有 Node.js 22；若不存在则回退到 nvm 安装，但不会切默认 Node 或写 shell rc。" "This prefers an existing Node.js 22 and only falls back to nvm when needed; it will not switch default Node or write shell rc.")"
fi

if [ "$DRY_RUN" -eq 1 ]; then
    print_dry_run_plan
    exit 0
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
[ -f "$SOURCE_DIR/mms-web" ] && cp "$SOURCE_DIR/mms-web" "$MMS_HOME/"
[ -f "$SOURCE_DIR/MMS Pilot.command" ] && cp "$SOURCE_DIR/MMS Pilot.command" "$MMS_HOME/"
# The Finder shortcut was named "MMS Web.command" before the client was named
# MMS Pilot. Leaving both would put two identical launchers in ~/.mms.
rm -f "$MMS_HOME/MMS Web.command"
copy_dir_safely "$SOURCE_DIR/mms_web" "$MMS_HOME/mms_web" "MMS Pilot 服务" "MMS Pilot service"
copy_dir_safely "$SOURCE_DIR/mms_web_static" "$MMS_HOME/mms_web_static" "MMS Pilot 页面" "MMS Pilot client"
mkdir -p "$MMS_HOME/docs/reference/model-capability-calibration"
if [ -f "$SOURCE_DIR/docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json" ]; then
    cp "$SOURCE_DIR/docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json" "$MMS_HOME/docs/reference/model-capability-calibration/"
fi
copy_dir_safely "$SOURCE_DIR/docs/mms-web" "$MMS_HOME/docs/mms-web" "MMS Pilot 使用文档" "MMS Pilot documentation"
[ -f "$SOURCE_DIR/mmf" ] && cp "$SOURCE_DIR"/mmf "$MMS_HOME/"
[ -f "$SOURCE_DIR/mmslogs" ] && cp "$SOURCE_DIR"/mmslogs "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_core.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_tui.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_launchers.py "$MMS_HOME/"
cp "$SOURCE_DIR"/mms_installer.py "$MMS_HOME/"
[ -f "$SOURCE_DIR/statusline-command.sh" ] && cp "$SOURCE_DIR"/statusline-command.sh "$MMS_HOME/"
copy_hooks_dir_safely "$SOURCE_DIR/hooks" "$MMS_HOME/hooks"
copy_dir_safely "$SOURCE_DIR/assets" "$MMS_HOME/assets" "assets 目录" "assets directory"
copy_dir_safely "$SOURCE_DIR/config" "$MMS_HOME/config" "config 目录" "config directory"
copy_dir_safely "$SOURCE_DIR/mms_config_web_static" "$MMS_HOME/mms_config_web_static" "WebUI 静态资源目录" "WebUI static assets directory"
copy_dir_safely "$SOURCE_DIR/vendor" "$MMS_HOME/vendor" "vendor 目录" "vendor directory"
copy_dir_safely "$SOURCE_DIR/scripts" "$MMS_HOME/scripts" "scripts 目录" "scripts directory"
if [ -f "$SOURCE_DIR/docs/LLM_OPERATION_GUIDE.md" ]; then
    mkdir -p "$MMS_HOME/docs"
    cp "$SOURCE_DIR/docs/LLM_OPERATION_GUIDE.md" "$MMS_HOME/docs/"
fi
# 复制所有 mms_*.py 确保完整
for f in "$SOURCE_DIR"/mms_*.py; do
    [ -f "$f" ] && cp "$f" "$MMS_HOME/"
done
[ -f "$SOURCE_DIR/config.example.toml" ] && cp "$SOURCE_DIR/config.example.toml" "$MMS_HOME/"
echo "✓ $(t "文件已复制到" "Files copied to") $MMS_HOME"
write_version_metadata
repair_managed_claude_settings
cleanup_legacy_global_session_hooks
write_language_config

# ── 清理已退休的可选包（从旧版本升级的机器）──
cleanup_retired_optional_packs || true

chmod +x "$MMS_HOME/mms"
[ -f "$MMS_HOME/mms-web" ] && chmod +x "$MMS_HOME/mms-web"
[ -f "$MMS_HOME/MMS Pilot.command" ] && chmod +x "$MMS_HOME/MMS Pilot.command"
[ -f "$MMS_HOME/mmf" ] && chmod +x "$MMS_HOME/mmf"
[ -f "$MMS_HOME/mmslogs" ] && chmod +x "$MMS_HOME/mmslogs"
[ -f "$MMS_HOME/statusline-command.sh" ] && chmod +x "$MMS_HOME/statusline-command.sh"
[ -d "$MMS_HOME/hooks" ] && find "$MMS_HOME/hooks" -type f -name '*.sh' -exec chmod +x {} +
[ -d "$MMS_HOME/scripts" ] && find "$MMS_HOME/scripts" -type f -exec chmod +x {} +

# ── 4. 修正入口的 Python 路径 ──
# 确保 shebang 指向隔离环境中的 python3
PYTHON_PATH="$VENV_DIR/bin/python"
rewrite_shebang "$MMS_HOME/mms" "$PYTHON_PATH"
[ -f "$MMS_HOME/mms-web" ] && rewrite_shebang "$MMS_HOME/mms-web" "$PYTHON_PATH"
[ -f "$MMS_HOME/mmf" ] && rewrite_shebang "$MMS_HOME/mmf" "$PYTHON_PATH"
[ -f "$MMS_HOME/mmslogs" ] && rewrite_shebang "$MMS_HOME/mmslogs" "$PYTHON_PATH"

# ── 4.5 安装必需 CLI（pi 必装，缺失的 claude/codex/opencode 自动补装）──
install_coding_fonts || echo "⚠ Coding fonts unavailable; continuing MMS installation."
install_requested_clis
warm_pi_runtime_cache || true

# ── 5. 建立命令入口 ──
echo ""
mkdir -p "$BIN_DIR"

# 创建 primary symlink；legacy ccs / mmc 已下线，仅保留 mms / mmf / mmslogs 入口。
ln -sf "$MMS_HOME/mms" "$BIN_DIR/mms"
[ -f "$MMS_HOME/mms-web" ] && ln -sf "$MMS_HOME/mms-web" "$BIN_DIR/mms-web"
[ -f "$MMS_HOME/mmf" ] && ln -sf "$MMS_HOME/mmf" "$BIN_DIR/mmf"
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
if [ -f "$MMS_HOME/mmf" ]; then
    echo "✓ $(t "命令已链接到" "Commands linked to") $BIN_DIR/mms, $BIN_DIR/mmf"
else
    echo "✓ $(t "命令已链接到" "Command linked to") $BIN_DIR/mms"
fi

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
    PREVIEW_CHANNEL_INSTALL=0
    if [ "$INSTALL_CHANNEL" = "dev" ] || [ "$INSTALL_CHANNEL" = "canary" ]; then
        PREVIEW_CHANNEL_INSTALL=1
    fi
    NEXT_MMF_CMD="mmf"
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        NEXT_MMF_CMD="$BIN_DIR/mmf"
    fi

    echo "===================================="
    echo "  ✅ $(t "MMS 安装完成" "MMS install completed")"
    echo "===================================="
    echo ""
    if [ "$PREVIEW_CHANNEL_INSTALL" -eq 1 ]; then
        echo "  $(t "本次安装的是预览通道；后续用 mmf 进入 preview root。" "This installed a preview channel; use mmf for the preview root.")"
    else
        echo "  $(t "运行" "Run") $BIN_DIR/mms $(t "开始使用 / 升级后继续使用" "to start using MMS / keep using it after upgrades")"
        if [[ ":$PATH:" = *":$BIN_DIR:"* ]]; then
            echo "  $(t "当前 shell 已可直接运行:" "Current shell can run directly:") mms"
        else
            echo "  $(t "当前 shell 还未加载 ~/.local/bin；可先运行绝对路径，或重开 Ghostty/iTerm/Terminal tab 后输入 mms。" "Current shell has not loaded ~/.local/bin yet; run the absolute path now, or reopen your Ghostty/iTerm/Terminal tab and type mms.")"
        fi
    fi
    echo ""

    if [ "$PREVIEW_CHANNEL_INSTALL" -eq 1 ]; then
        echo ""
        if legacy_config_has_route_candidates; then
            echo "  $(t "下一步（首次 preview/mmf 只做这两行）:" "Next step (first preview/mmf run: only do these two lines):")"
            echo "    $NEXT_MMF_CMD preview prepare"
            echo "    $NEXT_MMF_CMD"
            echo "  $(t "说明：prepare 只读取 ~/.config/mms，并写入 ~/.config/mms-next；不会改 stable 配置。" "Note: prepare only reads ~/.config/mms and writes ~/.config/mms-next; stable config is not modified.")"
        else
            echo "  $(t "下一步（全新机器先配通道）:" "Next step (fresh machine: configure providers first):")"
            echo "    $NEXT_MMF_CMD config web"
            echo "    $NEXT_MMF_CMD"
            echo "  $(t "说明：没有检测到可迁移的旧模型路由，先在 WebUI 添加 provider/API Key 并保存。" "Note: no migratable legacy model routes were detected; add providers/API keys in the WebUI first.")"
        fi
        echo ""
        echo "  $(t "以后需要排查时再运行:" "Only run this later when debugging:") $NEXT_MMF_CMD config doctor"
    fi

    if [ "$PREVIEW_CHANNEL_INSTALL" -eq 0 ] && [ "$RUN_SETUP" -eq 1 ] && { [ ! -f "$CONFIG_PATH" ] || [ ! -f "$CREDENTIALS_PATH" ]; }; then
        echo "$(t "检测到首次使用，启动配置向导..." "First-time setup detected, launching setup wizard...")"
        echo ""
        "$BIN_DIR/mms" || true
        DID_LAUNCH=1
    fi

    if [ "$PREVIEW_CHANNEL_INSTALL" -eq 0 ] && [ "$DID_LAUNCH" -eq 0 ] && [ "$LAUNCH_AFTER_INSTALL" -eq 0 ]; then
        echo "  $(t "在 MMS Web 里添加 provider 和 API Key，就可以开始对话。" "Add a provider and API key in MMS Web, then start a conversation.")"
        echo "  $(t "排查安装问题:" "To diagnose the install:") bash install.sh --check"
        offer_mms_web
    fi

    if [ "$LAUNCH_AFTER_INSTALL" -eq 1 ] && [ "$DID_LAUNCH" -eq 0 ]; then
        echo ""
        echo "$(t "启动 MMS..." "Launching MMS...")"
        if [ "$PREVIEW_CHANNEL_INSTALL" -eq 1 ] && [ -x "$BIN_DIR/mmf" ]; then
            "$BIN_DIR/mmf" || true
        else
            "$BIN_DIR/mms" || true
        fi
    fi
else
    echo "❌ $(t "安装似乎失败了，请检查上面的错误信息" "Install appears to have failed. Please review the errors above")"
    exit 1
fi
