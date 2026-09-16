# 回归报告：安装与 Pilot 手动升级提示

- 时间：2026-09-12（Asia/Singapore）
- 范围：旧 `~/.config/mms` 的安装器提醒；跨声明迁移边界的 Pilot 手动升级引导；暂存副本和一键更新 guard；v4.19.2 bundle。
- 修改：`install.sh`、`mms_web/updates.py`、`mms_web/update_guidance.py`、`mms_web/update_install.py`、`mms_web/update_coordinator.py`、`apps/mms-web/src/UpdateCenter.tsx`、`apps/mms-web/src/updates.css`、版本与 release note。

## 预期行为

1. 旧根只有真实配置文件时提示；只有 gateway/session 运行目录时不提示。
2. 安装器不卸载、不删除、不移动整个旧根。
3. 已声明需要手动安装的版本，以及运行在暂存副本或精确旧默认根的 Pilot，显示可复制的官方安装命令并禁用一键更新。
4. 新版本 release body 带有升级须知，旧版 Pilot 仍能读到文字说明。

## 验证

- `python3 -m pytest -q tests/test_mms_web_updates.py tests/test_mms_web_update_coordinator.py tests/test_install_script_paths.py`：95 passed。
- `npm run build --workspace @mms/web`：通过。
- `python3 scripts/build_mms_web_release.py --skip-install`：通过，生成 `mms_web_static` v4.19.2。
- `python3 -m compileall -q mms_web tests/fixtures/mms_web`：通过。
- `git diff --check`：通过。

## 风险与边界

- 已安装的旧客户端无法被新 JavaScript 反向改造；旧客户端的覆盖依赖下一版 GitHub release body 中的 `升级须知`。
- 不自动迁移或清理 API keys、gateway/session、旧配置；用户确认新安装正常后再人工处理。
- candidate preflight（候选版本启动时验证旧配置根）留作后续独立变更，避免本次触碰启动切换链路。

全量 `python3 -m pytest -q` 在当前 `dev` 基线出现 63 个与本次范围无关的既有失败（能力 fixture、旧入口断言、环境隔离等）；本次触及的更新/安装/配置根定向覆盖保持通过，未把这些失败归因于本改动。

状态：实现与定向回归完成，待提交和发布验收。
