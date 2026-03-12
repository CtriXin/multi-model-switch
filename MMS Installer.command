#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_SCRIPT="$SCRIPT_DIR/install.sh"

if [ ! -f "$INSTALL_SCRIPT" ]; then
    echo "未找到 install.sh"
    read -r -p "按回车关闭窗口..." _
    exit 1
fi

echo "===================================="
echo "  MMS 安装器（兼容 ccs）"
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
    echo "兼容旧习惯时，也可以继续输入：ccs"
else
    echo "安装失败，退出码：$status"
fi
echo ""
read -r -p "按回车关闭窗口..." _
exit "$status"
