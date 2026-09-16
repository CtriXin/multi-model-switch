# MMS Bot 深化阶段 · 工作总纲

Date: 2026-09-12
Manager: Claude（本会话负责进度、合并顺序、验收核对）
Task: Stride 370e87ec37e741df
Workspace: `/Users/xin/.local/share/stride/tasks/370e87ec37e741df/workspace`
Branch: `codex/stride-370e87ec37e741df`
基线提交：`6a223c7c`（2026-09-12，已 push；分支起点 a1348e3c = v4.16.0，origin/dev 已到 2614c6b6 = v4.19.4）

## 这一阶段要做成什么

Bot 是长期存在的员工，用户用聊天交代事情。MMS 只做身份、路由、编排、记忆、回执；执行交给 Pi、Ego、Skill。护城河是每个角色、每个子任务都能换模型。

这一轮四个工作包，按优先级：

| 包 | 名称 | 文档 | 建议模型 | 改动面 |
| --- | --- | --- | --- | --- |
| T1 | Bot 界面视觉系统重做（本轮重点） | `T1-ui-visual-system.md` | gemini3.6 主做，glm5.3 评审 | `apps/mms-web/src/bot*.css`、`Bot.tsx`、`BotStudio.tsx`、`BotMemoryPanel.tsx`、`BotCommunications.tsx` |
| T2 | Coordinator 计划层落地 | `T2-coordinator-plan.md` | k3 | `mms_web/bot_coordinator.py`、`bots.py`、`bot_executor.py`、新增 `BotPlan.tsx` |
| T3 | 失败重试与结果送达 | `T3-resilience-and-notify.md` | deepseek | 新增 `mms_web/bot_notify.py`、`bots.py` 最小改动、`server.py` 一个路由 |
| T1c | 新建即对话：命名、头像、预设在聊天里完成 | `T1c-create-in-chat.md` | gemini3.6 主做，glm5.3 评审 | `Bot.tsx` 头部与向导、`BotStudio.tsx` 的 `onUpdateBot`、新增 `bot-presets.ts` |
| T1d | Bot 页不弹 Pilot 首次引导 | `T1d-guide-on-bots.md` | gemini3.6 | `App.tsx` 引导插入点、`HelpGuide.tsx` 自动开始条件、新增测试 |
| T2b | Coordinator 成为真正的自动计划层：触发形状检查、状态机、结果图、重启幂等 | `T2b-planner-state-machine.md` | k3 主做，Claude 评审，UI 跟进另开 T2c 给 gemini | `bot_coordinator.py`、`bots.py` 新方法、`server.py` 一个路由的 action、`types.ts`、`BotPlan.tsx` 最小接线、测试 |
| T1e | 预设编辑器四处修正：重开不改名、可关闭、尾句顺序、单一焦点框 | `T1e-preset-editor-fixes.md` | gemini3.6 | `Bot.tsx` 向导/编辑器、`bot-presets.ts`、`bot.css`、测试 |
| T1f | 向导改成对话（题库分支、自由输入、答案入记忆），预设在侧栏与面板可见 | `T1f-conversational-wizard.md` | gemini3.6，T1e 之后 | `Bot.tsx` 向导与面板、`bot-presets.ts`、`BotStudio.tsx` 卡片一行、测试 |
| T3c | Bot 间往来在主聊天折叠成一张卡，协作面板按任务分段 | `T3c-peer-chat-folding.md` | gemini3.6（纯前端） | `Bot.tsx` 事件渲染、`BotCommunications.tsx`、`bot.css`、测试 |
| T3d | "等你补充"必须带问题（waitQuestion / pendingQuestion / dismiss / 过期），记忆不存无产出任务 | `T3d-waiting-contract.md` | 后端 deepseek，前端 gemini 随后 | `bots.py` 新方法、`bot_executor.py` wait 参数、`server.py` 一个路由、测试；前端 `Bot.tsx` 提问卡 |
| T2c | 计划块视觉整理：名字不竖排、goal/summary 分行、按钮固定行尾、状态标签三档、history 时间线 | `T2c-plan-block-visual.md` | gemini3.6 | `BotPlan.tsx`、`bot-plan.css` |
| T3d-ui | 等你回复：提问卡、头部与侧栏文案、旧任务结束等待 | `T3d-ui-question-card.md` | gemini3.6 | `Bot.tsx`、`BotStudio.tsx` 一行、`types.ts`、`bot.css`、测试 |
| T5a | 定时换成独立 schedule 实体 + 真周期调度，迁移旧 `runAt` 机制，命令清单从 parser 生成 | `T5a-schedule-backend.md` | k3 / deepseek | 新增 `mms_web/bot_schedules.py`、`bots.py` 最小接线、`bot_client.py`、`bot_executor.py` 提示词、`server.py` 路由 |
| T5b | 定时的选择器（一次/每天/每周/每 N 小时）与管理列表 | `T5b-schedule-ui.md` | gemini3.6，T5a 之后 | `Bot.tsx` composer 与面板、新增 `BotSchedulePanel.tsx`、`bot-schedules.ts`、`bot-visual-system.ts` |
| T5c | 在对话里换 Bot 的模型，下一轮生效 | `T5c-model-switch-by-dialogue.md` | k3 / deepseek，T5a 之后 | `bot_client.py` parser、`bots.py` `worker` 与启动优先级、`Bot.tsx` / `BotStudio.tsx` 最小接线 |
| T6a | 4.x ↔ 5.x 双向切换门禁 + **修掉降级泄漏内部会话**：4.22 忽略不认识的会话所有者、schema 不许升、fresh-user gate 加双向切换场景 | `T6a-channel-switch-gate.md` | k3 / deepseek | `mms_web/sessions.py` 与 `server.py` 各一处、`scripts/regression_fresh_user_gate.py`、新增契约与前向兼容测试。**base 是 4.22.x 线** |
| T6b | 把「运行环境」设置 tab 从 5.x 回流到 4.22.x，且不带进任何 Bot | `T6b-runtime-tab-backport.md` | gemini3.6 | **纯前端，只有** `SettingsPage.tsx` + `studio.css`，加一条无 Bot 断言。**base 是 4.22.x 线** |
| T4 | 落地与交付链 | `T4-landing-governance.md` | Claude（本会话） | rebase、issue、PR 拆分、全量回归、fresh-user gate |

建议只是建议，派发给谁由用户决定。

第四轮（2026-09-16）追加 **T6a / T6b**，对应 owner 新定的发布模型（`main` = 4.22.x 永久稳定线，`dev` = 5.x，用户可在两条线之间升降级，同一台机器不能同时装两个）。这两个包的 **base 是 4.22.x 线**（重组后是 `main`；重组尚未完成时用 `origin/dev` = `1f466eea` = 4.22.1），**不是 5.x**——理由是 owner 定的流向是"4.x 的所有改动默认进入 5.x"，门禁写在 4.x 侧会自动流到 5.x，反过来则不会回到 4.x。同一轮把 T5a / T5b / T5c 按 `origin/dev-pre`（`77f2fd8a` = 5.0.1）重新定位了行号与基线，并给三个包各加了一节"与近期改动的冲突面"。

第三轮（2026-09-16）追加 **T5a / T5b / T5c**。这三个包的 base 是 **`dev`**（重组后 `dev` 即 5.x 线）；重组尚未完成时用 **`origin/dev-pre`**。T5a 从 base 开，**T5b 和 T5c 都从 T5a 完成后的 HEAD 开**。落地顺序 **T5a → T5b / T5c**（T5b 纯前端、T5c 后端为主，两者可并行；T5c 与 T5a 动同一批文件，不能和 T5a 并行）。三个包都验收完才一起合；owner 的硬约束是"功能要么做完，要么不做"，**后端不单独进主线**。

第二轮（2026-09-14）追加 T1c。T1c 不从 6a223c7c 开分支，而是从任务分支当时的 HEAD 开，派发前先确认主 workspace 里的几何头像改动已提交。
每个包顶部都写了范围、不许碰的文件、验收和汇报格式。

评审分工：T1 的验收里有截图比对，需要能识图的模型。glm5.3 不能识图，只做代码侧评审（hex 计数、token 使用、diff 里是否混入行为改动、build 与测试结果）；截图的视觉评审由 Claude 做。

## 分支目标（2026-09-14 起）

owner 决定（2026-09-14）：`dev` / `main` 是 4.21.x 稳定安装线，不含 Bot；Bot 工作台是 5.0，集成分支是 `dev-pre`（从撤销前的 dev 065cf856 建立）。所有 Bot 包的 PR 指向 `dev-pre`。README 其它地方写的"→ dev"按此理解。

**2026-09-16 更新**：owner 定下新的发布模型——**`main` = 4.22.x 永久稳定线**（不含 Bot），**`dev` = 5.x**，用户可以在设置里在两条线之间升降级，同一台机器不能同时装两个。底层 mms 终端能力两条线完全相同（已验证：`mms_core.py` / `mms_launchers.py` / `mms_tui.py` / `mms` / `install.sh` / `mms_platform.py` 在 `v4.22.1` 和 `origin/dev-pre` 上逐字节相同），配置共用 `~/.config/mms-next`（Single Config Root 硬规则，见 `docs/AGENT_GUARDRAILS.md`，不许改）。

**分支现状（2026-09-16 实测，重组尚未完成，别凭记忆）**：

| 分支 | 版本 | HEAD | 说明 |
| --- | --- | --- | --- |
| `origin/dev-pre` | **5.0.1** | `77f2fd8a` | 5.x 线。重组后成为 `dev` |
| `origin/dev` | **4.22.1** | `1f466eea` | 4.22.x 线。重组后成为 `main` |
| `origin/main` | 4.10.0 | `ca6c09eb` | **陈旧，重组前不要用** |

所以：5.x 侧的包（T5a/b/c）今天 base 用 `origin/dev-pre`，4.22.x 侧的包（T6a/T6b）今天 base 用 `origin/dev`。重组完成后分别改成 `dev` 和 `main`。

## 派发时给模型的开场话（直接复制）

```
你在 MMS 仓库的 Stride 任务 370e87ec37e741df 里承接一个工作包。
先完整读 /Users/xin/.local/share/stride/tasks/370e87ec37e741df/workspace/docs/mms-web/bot-work/README.md，
再读你的包 <T?-xxx.md>。严格遵守"只许改 / 不许改"、并行规则和验收项。
从基线提交 6a223c7c 创建你自己的 worktree 和分支（README 第 2 条），不要在主 workspace 里改。
做完不要提交，把 git diff --stat、测试命令与结果、实时验证截图路径、未完成项按 README 的格式写进你 worktree 的 walls.md，然后汇报。
```

## 并行规则（必须遵守）

1. **基线已落。** 提交 51e85fd1（后端）、b3d18c86（前端）、6a223c7c（文档）在分支上并已 push。所有包从 `6a223c7c` 或之后开分支。
2. **每个包一个 worktree、一个分支**，从基线提交创建：
   ```bash
   cd /Users/xin/.local/share/stride/tasks/370e87ec37e741df/workspace
   git worktree add ../wt-T1 -b bot/T1-ui codex/stride-370e87ec37e741df
   ```
   分支名固定 `bot/T1-ui`、`bot/T2-coordinator`、`bot/T3-notify`。不要在主 workspace 里直接改。
3. **不要碰别的包的文件。** 每个包文档里有"只许改 / 不许改"清单。共享文件（`bots.py`、`Bot.tsx`）只允许做文档里指定的最小插入点。
4. **不提交、不 push、不 merge。** 改完在 worktree 里 `git diff --stat` 给用户，由用户批准提交。Claude 负责合并顺序：T1 → T3 → T2。
5. **不重启 60824。** 那是用户的验证实例。前端验证用独立实例：
   ```bash
   cd <你的 worktree>
   npm run build --workspace @mms/web
   PYTHONPATH=$PWD python3 -P -m mms_web --port 61xxx \
     --state-root /tmp/bot-verify-<包名> \
     --config-root ~/.config/mms-next \
     --static-root $PWD/apps/mms-web/dist
   ```
   每个包用不同端口。不要在真实模型上发长任务，验证 UI 用空草稿或一句话任务。
6. **不改受保护文件**：`mms_core.py`、`mms_launchers.py`、`mms_tui.py`、`mms_bridge.py`、`mms_account_state.py`、`mms_session.py`、`mms_adapter_registry.py`、`mms`。不写真实 `~/.config/mms*`。
7. **不引入依赖。** 前端只用现有 lucide-react、react。后端只用标准库。

## 通用验收

每个包结束时必须给出：

```
包：T?
分支 / worktree：
改动文件：git diff --stat 输出
测试：实际执行的命令 + 结果（通过数 / 失败数）
实时验证：端口、看了哪些页面或接口、截图路径
未完成 / 未验证：逐条
```

写进 worktree 根目录的 `walls.md`（追加，不改旧条目），格式沿用现有条目：`## 日期 时间 SGT · <模型名> · 370e87ec37e741df` 加 需求 / 处置 / 验证 / 耗时。

前端测试：`node --test apps/mms-web/tests/*.test.mjs`。**必须带 `*.test.mjs` glob**——`node --test apps/mms-web/tests/` 不带 glob 会直接报 `fail 1`（2026-09-16 在 `77f2fd8a` 实测）。后端 focused tests：

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py \
  tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py \
  tests/test_mms_bot_coordinator.py
```

当前基线：72 passed（这一组七个文件）。任何包不得让这个数字下降。

**2026-09-16 在 `origin/dev-pre` = `77f2fd8a` = 5.0.1 实测的全套基线**（T5 / T6 各包以自己文档里写的为准）：

| 门禁 | 实测值 |
| --- | --- |
| 九文件 focused pytest（见 T5a 门禁那一组） | **202 passed**（旧包里写的 203 是错的，两个 commit 上重测都是 202） |
| `node --test apps/mms-web/tests/*.test.mjs` | **121 pass / 0 fail**（19 个测试文件；旧包写的 114 是 gemini 新增三个测试文件之前的数） |
| `npx tsc --noEmit -p apps/mms-web` | **0 错** |
| `grep -ohE '#[0-9a-fA-F]{3,8}\b' apps/mms-web/src/bot*.css \| sort -u \| wc -l` | **12**（没变） |

跑前端门禁之前先在 worktree 里 `npm install`。

**设计文档的路径**：是 `apps/mms-web/DESIGN.md`，**不是 `docs/mms-web/DESIGN.md`**（后者不存在）。T1e / T1f / T2c / T3c 几个旧包里写的那个路径已过期，T5 / T6 各包已订正。

## 已经确认、不得倒退的边界

来自 `docs/mms-web/CLAUDE-CONTINUATION.md`，摘要：

- 不做 Oh My OpenCode 式重编排；planner / worker / reviewer 不暴露成永久 Bot。
- 浏览器只走 Ego，不自研浏览器引擎，不复制 cookie / profile。
- 主聊天只有用户消息、Bot 回复、成果、等待提示；工具日志折叠在执行详情。
- 状态文案"待命"；自动唤醒用闹钟语义；配置 / 删除默认隐藏。
- 不把 build 通过、接口可读、测试通过当作交付。
