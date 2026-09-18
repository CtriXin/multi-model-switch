#!/bin/sh
set -eu
_mms_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -f "$_mms_root/lib/mms_core.py" ]; then
  echo "这份 MMS 安装是旧布局(模块在安装根,当前入口需要 lib/)。" >&2
  echo "旧布局不再被支持,请重新执行安装命令更新:" >&2
  echo "" >&2
  echo "  curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/dev/install.sh | bash -s -- --channel dev" >&2
  echo "" >&2
  echo "如果 Pilot 正在运行,先执行 mms web stop 再装。" >&2
  echo "" >&2
  echo "This MMS install uses the old layout (modules at the install root; this entry needs lib/)." >&2
  echo "The old layout is no longer supported. Re-run the install command to update:" >&2
  echo "" >&2
  echo "  curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/dev/install.sh | bash -s -- --channel dev" >&2
  echo "" >&2
  echo "If Pilot is running, run mms web stop first, then install." >&2
  exit 1
fi
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec ./mms-web --open "$@"
