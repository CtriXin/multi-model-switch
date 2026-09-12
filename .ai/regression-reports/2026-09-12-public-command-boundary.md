# 回归报告：公共安装命令入口

- 时间：2026-09-12（Asia/Singapore）
- 范围：stable 安装只维护公开 `mms`，不覆盖维护者本机的 `mmf/mmg/mmd/mmm`；显式 dev/canary 仍可创建 `mmf` 预览入口。
- 修改：`install.sh`、`README.md`、安装脚本测试、版本与 `v4.19.3` release note、Pilot bundle metadata。

## 验证

- `python3 -m pytest -q tests/test_install_script_paths.py`：71 passed。
- `python3 scripts/build_mms_web_release.py --skip-install`：通过，bundle v4.19.3。
- `git diff --check`：通过。

## 边界

- 普通用户继续使用 `mms`；`mmf` 等入口由维护者本机的 `scripts/link_local_channel_commands.sh` 管理。
- 旧 MMS-owned `mmf` symlink 会清理；普通文件、指向本地 worktree 的 wrapper/symlink 不会触碰。
- 当前真实本机 Pilot 仍由用户控制，未在回归中停止或重启。
