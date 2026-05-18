# Open Source Audit

更新日期：2026-05-18

## 当前结论

本仓库当前开源发布检查的目标是：公开源码只保留 launcher/runtime 产品源码、示例配置、公开文档和测试；本地 AI 上下文、运行状态、私有 handoff、签名/数据库/构建产物继续留在本机并由 `.gitignore` 保护。

## 已完成

- License 已统一为 `Apache-2.0`：根目录 `LICENSE`、README badge/License 段落、landing page 文案保持一致。
- `.gitignore` 已覆盖本地 AI/运行上下文：`.ai/`、`.omc/`、`.claude/`、`.worktrees/`、`DESIGN_V3_SPEC.md`、`AI_PROJECT_CONTEXT.md`、`HANDOFF_WEB_APP.md`、根目录和 app 级 `findings.md` / `progress.md` / `task_plan.md`。
- 已从 git 索引移出、但保留在本地的上下文/状态文件：`.ai/regression-reports/*`、`.omc/*`、`AI_PROJECT_CONTEXT.md`、`HANDOFF_WEB_APP.md`。
- 已确认真实 runtime 配置、gateway state、签名证书、build 产物不应进入公开仓库：`apps/runtime-api/gateway-config.json`、`apps/runtime-api/gateway-state.db`、`apps/web-v2/src-tauri/*.provisionprofile`、`apps/web-v2/src-tauri/*.p12`、`apps/web-v2/ios/build/`、`apps/web-v2/src-tauri/target/`。
- 已将公开文档里的本机绝对路径示例改成相对路径、`~` 或环境变量形式。

## 本轮扫描结果

- `git ls-files -ci --exclude-standard`：应为空，表示没有 tracked 文件继续命中 ignore 规则。
- tracked 文件中未发现真实本机 Home 绝对路径。
- tracked 文件中未发现常见 API key、GitHub token、Slack token、AWS key、私钥块。
- `localhost`、`127.0.0.1`、`private`、`internal` 等词仍会出现在示例配置、loopback proxy、测试和通用 runbook 中；当前语义是示例/占位/本地网络边界，不是实际凭证。

## 仍需人工判断

- 如果目标是“只公开当前 main 之后的新历史”，当前源码层面风险较低。
- 如果目标是“公开完整历史”，仍建议在发布前对历史提交运行一次 secret/path 扫描；如果历史里有旧 `.ai`、本地 handoff 或签名痕迹，需要用 `git filter-repo` 处理。
- `package.json` 保留 `private: true` 是为了避免误发 npm；不影响 GitHub 开源发布。

## 开源前最小检查清单

1. `git ls-files -ci --exclude-standard` 为空。
2. Home 绝对路径扫描无真实本机路径输出。
3. secret pattern 扫描无真实 key / token / private key。
4. `git diff --check` 通过。
5. `npm run build --if-present` 通过。
6. `python3.13 -m pytest -q` 通过，或明确记录跳过/失败原因。
