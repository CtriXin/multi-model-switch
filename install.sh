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
WRITE_SHELL_RC=0
RUN_SETUP=0
ENSURE_NODE22=0
LAUNCH_AFTER_INSTALL=0

cleanup() {
    if [ -n "$SOURCE_TMP_DIR" ] && [ -d "$SOURCE_TMP_DIR" ]; then
        rm -rf "$SOURCE_TMP_DIR"
    fi
}

trap cleanup EXIT

usage() {
    cat <<EOF
用法:
  bash install.sh [--write-shell-rc] [--run-setup] [--ensure-node22] [--launch-after-install]
  bash install.sh --ref <tag-or-branch>
  bash install.sh --main
  bash install.sh --latest-tag
  bash install.sh --latest-release

说明:
  - 默认远程安装/升级使用最新 semver tag
  - --ref 可指定版本号或分支，例如 v1.2.0 / main
  - 同一条命令可重复执行，用于升级
EOF
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

    echo "正在下载源码归档: $archive_url"
    curl -fsSL "$archive_url" -o "$tarball"
    tar -xzf "$tarball" -C "$SOURCE_TMP_DIR"

    SOURCE_DIR="$(find "$SOURCE_TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    if [ -z "$SOURCE_DIR" ] || [ ! -f "$SOURCE_DIR/mms_core.py" ]; then
        echo "❌ 远程源码解压失败"
        return 1
    fi
    echo "✓ 已获取源码: $SOURCE_DIR"
}

write_version_metadata() {
    mkdir -p "$(dirname "$VERSION_META_PATH")"
    python3 - "$VERSION_META_PATH" "$RESOLVED_INSTALL_REF" "$INSTALL_CHANNEL" <<'PY'
import json
import re
import sys
from datetime import datetime, timezone

path, resolved_ref, install_channel = sys.argv[1:4]
resolved_ref = str(resolved_ref or "").strip()
installed_version = resolved_ref if re.fullmatch(r"v\d+\.\d+\.\d+", resolved_ref) else ""

payload = {
    "installed_ref": resolved_ref,
    "installed_version": installed_version,
    "install_channel": install_channel,
    "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "source": "install.sh",
}

with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
    chmod 600 "$VERSION_META_PATH"
    if [ -n "$RESOLVED_INSTALL_REF" ]; then
        echo "✓ 已记录安装版本: $RESOLVED_INSTALL_REF"
    fi
}

prepare_source_dir() {
    if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/mms_core.py" ]; then
        SOURCE_DIR="$SCRIPT_DIR"
        echo "✓ 使用本地源码: $SOURCE_DIR"
        return
    fi

    SOURCE_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mms-install.XXXXXX")"

    local ref="$INSTALL_REF"
    if [ -z "$ref" ] && [ "$INSTALL_CHANNEL" = "latest-release" ]; then
        ref="$(resolve_latest_release_tag || true)"
        if [ -n "$ref" ]; then
            echo "✓ latest release: $ref"
        else
            echo "⚠ 获取 latest release 失败，回退到最新 tag"
            INSTALL_CHANNEL="latest-tag"
        fi
    fi
    if [ -z "$ref" ] && [ "$INSTALL_CHANNEL" = "latest-tag" ]; then
        ref="$(resolve_latest_tag || true)"
        if [ -n "$ref" ]; then
            echo "✓ latest tag: $ref"
        else
            echo "⚠ 获取最新 tag 失败，回退到 main"
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
    echo "正在准备 Node.js 22（通过 nvm）..."
    export NVM_DIR="$HOME/.nvm"

    if [ -s "$NVM_DIR/nvm.sh" ]; then
        # shellcheck disable=SC1090
        . "$NVM_DIR/nvm.sh"
        if [ "$(nvm version 22)" != "N/A" ]; then
            nvm alias default 22 >/dev/null
            nvm use 22 >/dev/null
            echo "✓ 检测到 nvm 已安装 Node.js $(node --version)，跳过安装"
            return
        fi
    else
        echo "未检测到 nvm，开始安装..."
        curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
    fi

    # shellcheck disable=SC1090
    . "$NVM_DIR/nvm.sh"
    nvm install 22
    nvm alias default 22
    nvm use 22 >/dev/null
    echo "✓ Node.js 已切换到 $(node --version)"
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
        --ref)
            shift
            if [[ -z "${1:-}" ]]; then
                echo "❌ --ref 需要一个版本号或分支名"
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
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

echo "===================================="
echo "  MMS 一键安装"
echo "===================================="
echo ""

if [ "$ENSURE_NODE22" -eq 1 ]; then
    echo "⚠ 将检查并安装 nvm / Node.js 22，这可能更新你的 shell 配置。"
fi

# ── 1. 检查 Python3 ──
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3"
    if command -v brew &>/dev/null; then
        echo "   正在通过 brew 安装..."
        brew install python3
    else
        echo "   请先安装 Python 3: https://www.python.org/downloads/"
        exit 1
    fi
fi
echo "✓ Python3: $(python3 --version)"

if [ "$ENSURE_NODE22" -eq 1 ]; then
    ensure_node22
fi

# ── 2. 创建隔离的 Python 环境 ──
echo ""
echo "正在创建隔离环境..."
mkdir -p "$MMS_HOME"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet rich httpx tomli-w
echo "✓ 依赖已安装到 $VENV_DIR"

# ── 3. 复制文件到 ~/.mms ──
echo ""

prepare_source_dir

if [ -z "$SOURCE_DIR" ] || [ ! -f "$SOURCE_DIR/mms_core.py" ]; then
    echo "❌ 找不到 MMS 源文件"
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
echo "✓ 文件已复制到 $MMS_HOME"
write_version_metadata

chmod +x "$MMS_HOME/ccs"
chmod +x "$MMS_HOME/mms"
[ -f "$MMS_HOME/statusline-command.sh" ] && chmod +x "$MMS_HOME/statusline-command.sh"

# ── 4. 修正入口的 Python 路径 ──
# 确保 shebang 指向隔离环境中的 python3
PYTHON_PATH="$VENV_DIR/bin/python"
sed -i.bak "1s|^#!.*|#!${PYTHON_PATH}|" "$MMS_HOME/ccs" && rm -f "$MMS_HOME/ccs.bak"
sed -i.bak "1s|^#!.*|#!${PYTHON_PATH}|" "$MMS_HOME/mms" && rm -f "$MMS_HOME/mms.bak"

# ── 5. 建立命令入口 ──
echo ""
mkdir -p "$BIN_DIR"

# 创建 symlink
ln -sf "$MMS_HOME/ccs" "$BIN_DIR/ccs"
ln -sf "$MMS_HOME/mms" "$BIN_DIR/mms"
echo "✓ 命令已链接到 $BIN_DIR/mms 和 $BIN_DIR/ccs"

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
                echo "✓ PATH 已写入 $SHELL_RC"
            fi
        else
            echo "⚠ 未找到 shell 配置文件，请手动添加:"
            echo "  $PATH_LINE"
        fi
    else
        echo "⚠ 未修改你的 shell 配置。"
        echo "  当前安装不会自动写入 ~/.zshrc / ~/.bashrc。"
        echo "  如需全局可用，请手动添加:"
        echo "    $PATH_LINE"
        echo "  或重新执行: bash install.sh --write-shell-rc"
    fi
fi

# ── 6. 验证 ──
echo ""
if [ -x "$BIN_DIR/mms" ]; then
    DID_LAUNCH=0
    echo "===================================="
    echo "  ✅ MMS 安装完成"
    echo "===================================="
    echo ""
    echo "  运行 $BIN_DIR/mms 开始使用 / 升级后继续使用"
    echo ""
    echo "  常用命令:"
    echo "    mms              交互选择场景"
    echo "    mms 1            快速启动场景 1"
    echo "    mms --preset coding  使用预设"
    echo "    mms config       查看/修改配置"
    echo "    mms --export claude  导出环境变量"
    echo ""

    if [ "$RUN_SETUP" -eq 1 ] && { [ ! -f "$CONFIG_PATH" ] || [ ! -f "$CREDENTIALS_PATH" ]; }; then
        echo "检测到首次使用，启动配置向导..."
        echo ""
        "$BIN_DIR/mms" || true
        DID_LAUNCH=1
    elif [ ! -f "$CONFIG_PATH" ] || [ ! -f "$CREDENTIALS_PATH" ]; then
        echo "  首次配置请运行:"
        echo "    $BIN_DIR/mms"
        echo ""
        echo "  如需安装完成后立即进入配置向导，可执行:"
        echo "    bash install.sh --run-setup"
    fi

    if [ "$LAUNCH_AFTER_INSTALL" -eq 1 ] && [ "$DID_LAUNCH" -eq 0 ]; then
        echo ""
        echo "启动 MMS..."
        "$BIN_DIR/mms" || true
    fi
else
    echo "❌ 安装似乎失败了，请检查上面的错误信息"
    exit 1
fi
