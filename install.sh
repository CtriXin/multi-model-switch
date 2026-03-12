#!/bin/bash
# CCS 一键安装脚本
# 用法: curl -fsSL <url>/install.sh | bash
#   或: bash install.sh [--write-shell-rc] [--run-setup] [--ensure-node22] [--launch-after-install]

set -e

CCS_HOME="$HOME/.ccs"
BIN_DIR="$HOME/.local/bin"
VENV_DIR="$CCS_HOME/.venv"
CREDENTIALS_PATH="$HOME/.config/ccs/credentials.sh"
CONFIG_PATH="$HOME/.config/ccs/config.toml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" 2>/dev/null)" && pwd 2>/dev/null || echo "")"
WRITE_SHELL_RC=0
RUN_SETUP=0
ENSURE_NODE22=0
LAUNCH_AFTER_INSTALL=0

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
        *)
            echo "❌ 未知参数: $1"
            echo "用法: bash install.sh [--write-shell-rc] [--run-setup] [--ensure-node22] [--launch-after-install]"
            exit 1
            ;;
    esac
    shift
done

echo "==============================="
echo "  CCS 一键安装"
echo "==============================="
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
mkdir -p "$CCS_HOME"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet rich httpx tomli-w
echo "✓ 依赖已安装到 $VENV_DIR"

# ── 3. 复制文件到 ~/.ccs ──
echo ""

# 判断来源：本地目录 or 远程
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/ccs_core.py" ]; then
    # 从本地安装
    cp "$SCRIPT_DIR"/ccs "$CCS_HOME/ccs"
    cp "$SCRIPT_DIR"/ccs_core.py "$CCS_HOME/"
    cp "$SCRIPT_DIR"/ccs_tui.py "$CCS_HOME/"
    cp "$SCRIPT_DIR"/ccs_launchers.py "$CCS_HOME/"
    cp "$SCRIPT_DIR"/ccs_installer.py "$CCS_HOME/"
    [ -f "$SCRIPT_DIR/config.example.toml" ] && cp "$SCRIPT_DIR/config.example.toml" "$CCS_HOME/"
    echo "✓ 文件已复制到 $CCS_HOME"
else
    echo "❌ 找不到 CCS 源文件，请在 ccs 目录下运行此脚本"
    exit 1
fi

chmod +x "$CCS_HOME/ccs"

# ── 4. 修正 ccs 入口的 Python 路径 ──
# 确保 shebang 指向隔离环境中的 python3
PYTHON_PATH="$VENV_DIR/bin/python"
sed -i.bak "1s|^#!.*|#!${PYTHON_PATH}|" "$CCS_HOME/ccs" && rm -f "$CCS_HOME/ccs.bak"

# ── 5. 建立命令入口 ──
echo ""
mkdir -p "$BIN_DIR"

# 创建 symlink
ln -sf "$CCS_HOME/ccs" "$BIN_DIR/ccs"
echo "✓ 命令已链接到 $BIN_DIR/ccs"

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

        MARKER="# Added by CCS"
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
if [ -x "$BIN_DIR/ccs" ]; then
    DID_LAUNCH=0
    echo "==============================="
    echo "  ✅ CCS 安装完成！"
    echo "==============================="
    echo ""
    echo "  运行 $BIN_DIR/ccs 开始使用"
    echo ""
    echo "  常用命令:"
    echo "    ccs              交互选择场景"
    echo "    ccs 1            快速启动场景 1"
    echo "    ccs --preset coding  使用预设"
    echo "    ccs config       查看/修改配置"
    echo "    ccs --export claude  导出环境变量"
    echo ""

    if [ "$RUN_SETUP" -eq 1 ] && { [ ! -f "$CONFIG_PATH" ] || [ ! -f "$CREDENTIALS_PATH" ]; }; then
        echo "检测到首次使用，启动配置向导..."
        echo ""
        "$BIN_DIR/ccs" || true
        DID_LAUNCH=1
    elif [ ! -f "$CONFIG_PATH" ] || [ ! -f "$CREDENTIALS_PATH" ]; then
        echo "  首次配置请手动运行:"
        echo "    $BIN_DIR/ccs"
        echo ""
        echo "  如需安装完成后立即进入配置向导，可执行:"
        echo "    bash install.sh --run-setup"
    fi

    if [ "$LAUNCH_AFTER_INSTALL" -eq 1 ] && [ "$DID_LAUNCH" -eq 0 ]; then
        echo ""
        echo "启动 CCS..."
        "$BIN_DIR/ccs" || true
    fi
else
    echo "❌ 安装似乎失败了，请检查上面的错误信息"
    exit 1
fi
