#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_SCRIPT="$SCRIPT_DIR/install.sh"

if [ ! -f "$SCRIPT_DIR/lib/mms_core.py" ]; then
    echo "这份 MMS 安装是旧布局(模块在安装根,当前入口需要 lib/)。"
    echo "旧布局不再被支持,请重新执行安装命令更新:"
    echo ""
    echo "  curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/dev/install.sh | bash -s -- --channel dev"
    echo ""
    echo "如果 Pilot 正在运行,先执行 mms web stop 再装。"
    echo ""
    echo "This MMS install uses the old layout (modules at the install root; this entry needs lib/)."
    echo "The old layout is no longer supported. Re-run the install command to update:"
    echo ""
    echo "  curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/dev/install.sh | bash -s -- --channel dev"
    echo ""
    echo "If Pilot is running, run mms web stop first, then install."
    read -r -p "按回车关闭窗口..." _
    exit 1
fi


if [ ! -f "$INSTALL_SCRIPT" ]; then
    echo "未找到 install.sh"
    read -r -p "按回车关闭窗口..." _
    exit 1
fi

echo "===================================="
echo "  MMS 安装器"
echo "===================================="
echo ""
echo "将执行："
echo "  bash install.sh --run-setup --write-shell-rc --launch-after-install"
echo ""

set +e
bash "$INSTALL_SCRIPT" --run-setup --write-shell-rc --launch-after-install "$@"
status=$?
set -e

echo ""
if [ "$status" -eq 0 ]; then
    echo "安装完成。以后可直接输入：mms"
else
    echo "安装失败，退出码：$status"
fi
echo ""
read -r -p "按回车关闭窗口..." _
exit "$status"
