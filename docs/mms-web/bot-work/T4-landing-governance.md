# T4 · 落地与交付链（Claude 负责）

Task: 370e87ec37e741df · 在主 workspace 与分支 `codex/stride-370e87ec37e741df` 上操作

## 为什么先做这个
34 项改动全部未提交，其中 28 个是未跟踪新文件。没有 issue、PR、完整回归、fresh-user gate。origin/dev 已经从基线 a1348e3c（v4.16.0）前进到 2614c6b6（v4.19.4），差 10 个以上提交，其中有 `mms_web` 与 installer 的改动，合并冲突风险真实存在。其它三个包都要从一个已提交的基线开分支。

## 步骤
1. **基线提交（需用户批准，每个提交单独批）。** 按切片拆：
   - `feat(bots): runtime, executor, memory, communications, coordinator` = `mms_web/bots.py bot_executor.py bot_client.py bot_communications.py bot_memory.py bot_computer.py bot_coordinator.py browser_provider.py server.py .gitignore` + 7 个 `tests/test_*bot*.py`
   - `feat(web): Bot workbench UI` = `apps/mms-web/src/Bot*.tsx bot-artifact-preview.ts bot*.css App.tsx studio.css types.ts` + 重建 `mms_web_static/`（`python3 scripts/build_mms_web_release.py --skip-install`，规则要求与 src 同一提交）
   - `docs(bots): positioning, roadmap, BOTS, browser providers, continuation, work packets` = `docs/mms-web/BOT*.md BROWSER-PROVIDERS.md CLAUDE-CONTINUATION.md GETTING-STARTED.md design/ bot-work/`
   - `walls.md`、`RETROSPECTIVE.md` 是 Stride 任务记录，不进仓库提交；确认它们在 `.gitignore` 或留在未跟踪。
   - 提交身份按 `commit-identity.md`：`TZ=Asia/Singapore git -c user.name=... -c user.email=claude-fable-5.1@anthropic.com commit` 加 Agent-* trailers。
2. **开 issue**：标题 `Bot 工作台（MMS Bot v2.x）：落地、Coordinator、通知、UI 视觉系统`，正文贴 README 的四个包与验收，作为四个 PR 的父 issue。
3. **同步 dev**：`git fetch origin dev` 后 `git rebase origin/dev`（或 merge，看冲突量）。冲突只解本任务文件，不动别人的。
4. **完整回归**：`python3 scripts/ci_pytest_regression.py --base origin/dev`，只报它点名的差异。walls.md 说过全量 pytest 在这个 worktree 跑不了，先查原因。
5. **fresh-user gate**：`python3 scripts/regression_fresh_user_gate.py`，与 dev 上已知失败集对比（见 memory 基线）。
6. **PR 拆分**：先出 PR-0（基线），之后 T1 / T3 / T2 各一个 PR，都指向父 issue。合并由用户执行（agent 不 merge）。
7. 每个包回来后：核对其 walls 汇报、复跑其测试、在自建实例上过一遍验收项，再进 PR。

## 不做
不重启 60824；不 merge；不 push 未经批准的提交。
