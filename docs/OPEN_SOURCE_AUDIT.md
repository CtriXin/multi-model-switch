# Open Source Audit

更新日期：2026-03-19

## 已完成

- 已补充 `.gitignore`，避免以下本地文件继续被误同步：
  - `DESIGN_V3_SPEC.md`
  - `apps/web-v2/GEMINI.md`
  - `apps/web-v2/*-worktree/`
  - 根目录与 app 级 `findings.md` / `progress.md` / `task_plan.md`
  - `apps/*/.ai/`
- 已确认以下敏感物料目前未被 git 跟踪：
  - `apps/runtime-api/gateway-config.json`
  - `apps/runtime-api/gateway-state.db`
  - `apps/web-v2/src-tauri/*.provisionprofile`
  - `apps/web-v2/src-tauri/*.p12`
  - `apps/web-v2/ios/build/`
  - `apps/web-v2/src-tauri/target/`

## 已跟踪但应视为本地上下文的候选项

这些文件不是源码主干，更像 planning / handoff / local release context。即使现在补了 ignore，它们仍在 git 历史里，需要后续显式处理。

- `.ai/plan/TODO.md`
- `findings.md`
- `progress.md`
- `task_plan.md`
- `apps/web-pro/.ai/agent-release-notes.md`
- `apps/web-pro/.ai/plan/TODO.md`
- `apps/web-pro/findings.md`
- `apps/web-pro/progress.md`
- `apps/web-pro/task_plan.md`
- `docs/archive/todo-archive-2026-03.md`

建议动作：

1. 用 `git rm --cached` 将上述文件从索引移除，但保留本地文件。
2. 若这些文件已经进入公开历史，开源前评估是否需要 `git filter-repo` 清理历史。

## 已跟踪且与 ignore 语义冲突的遗留项

这些文件当前已经被跟踪，但现有 ignore 规则本身就把它们定义为本地/生成物：

- `.ai/plan/TODO.md`
- `apps/web-v2/ios/App/App/capacitor.config.json`
- `docs/archive/todo-archive-2026-03.md`

说明：

- `apps/web-v2/ios/.gitignore` 已将 `App/App/capacitor.config.json` 和 `App/App/config.xml` 视为 generated config。
- 根 `.gitignore` 已将 `.ai/plan/` 和 `docs/archive/todo-archive-*.md` 视为本地上下文。

建议动作：

1. 确认 `apps/web-v2/ios/App/App/capacitor.config.json` 是否需要保留为公开仓库的一部分。
2. 如果不需要，和上面的 planning 文件一起从索引摘掉。

## 需人工确认的公开发布配置

下面这些文件目前没有直接发现 secret，但包含发布或签名语义，开源前应人工复核：

- `apps/web-v2/ios/App/App.xcodeproj/project.pbxproj`
  - 当前包含 `DEVELOPMENT_TEAM = 2HJP9YYL3H`
- `apps/web-v2/src-tauri/tauri.appstore.conf.json`
  - 引用了 `embedded.provisionprofile`
- `apps/web-v2/ios/App/App/capacitor.config.json`
  - 当前是生成文件，且包含 app id / app name / webDir

建议动作：

1. 判断 `DEVELOPMENT_TEAM` 是否要替换为占位值或改为本地覆盖。
2. 保留 `tauri.appstore.conf.json` 结构，但确保仓库中永远不提交真实 `AppStore.provisionprofile`。
3. 若 `capacitor.config.json` 只是生成产物，则不应继续被跟踪。

## 本轮未发现

- 未扫到硬编码 API key、GitHub token、Slack token、私钥块。
- 文档里存在 `localhost`、`private.key`、`internal gateway` 等字样，但当前看到的是示例、占位或方案讨论，不是实际凭证。

## 开源前最小检查清单

1. `git ls-files -ci --exclude-standard` 应为空，或只保留明确接受的例外项。
2. `git status --short --ignored` 里不应出现新的签名证书、数据库、构建产物被误跟踪。
3. 重新扫描 `project.pbxproj`、`tauri.appstore.conf.json`、runtime/gateway 配置相关文件。
4. 若要公开历史，补做一次 `git filter-repo` 风险复核。
