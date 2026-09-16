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
| T7a | 连接横幅与真实连接状态脱节：失败要防抖，连接噪音和操作失败必须分流 | `T7a-connection-banner.md` | gemini3.6 | **纯前端**，`App.tsx` 的 `load()` 失败处理与顶部红条、`styles.css`、新增一个单测文件。**base 是 `main`（4.22.1）** |
| T7b | BTW 旁问卡片收起后要被记住：换成"已读/已处置"语义，状态活过卸载 | `T7b-btw-card-fold-memory.md` | gemini3.6 | **纯前端**，`SideQuestions.tsx` / `side-questions.ts` / `App.tsx` 两处最小接线 / `side-questions.test.mjs`。**base 是 `main`（4.22.1）** |
| T7c | 把 MMF 挡下来的真实原因说给用户听：`blocked_reasons` 只当布尔值用，内容一个字都没传给用户 | `T7c-surface-blocked-reasons.md` | k3 / deepseek | **后端为主**，新增 `mms_web/config_block_reasons.py` + `model_settings_worker.py` 一句 message；前端只核对 `ChannelModels.tsx` 已有三处渲染点。**base 是 `main`（4.22.1）** |
| T7d | 开「手机访问」不该把当前这个窗口踢掉：开关/换 token 时给当前会话种 cookie，loopback 一律不放行 | `T7d-remote-access-keeps-current-window.md` | k3 / deepseek | **后端为主**，`server.py` 的 `set_remote_access` 与响应头链路；前端 `RemoteAccess.tsx` 三处文案 + `REMOTE-ACCESS.md`。**base 是 `main`（4.22.1）** |
| T7e | **（本轮最高优先级）** 被中断的回合：界面看不见发生了什么——回合按位置被误判成"已完成"、三槽位落空渲染 `null`、被重启作废的消息救不回来、被打断的一轮却说"本轮已完成" | `T7e-blank-turn-after-steer.md` | gemini3.6（纯前端） | **纯前端**，`Transcript.tsx` / `SessionStatus.tsx` / `transcript.css` / `App.tsx` 三处最小接线 / `turn-working-status.test.mjs`。**base 是 `dev`（5.0.1）**，理由见包内"为什么不是 `main`" |
| T4 | 落地与交付链 | `T4-landing-governance.md` | Claude（本会话） | rebase、issue、PR 拆分、全量回归、fresh-user gate |

建议只是建议，派发给谁由用户决定。

第七轮（2026-09-16）追加 **T7e**，**优先级高于 T7a / T7b / T7c / T7d**。来自 owner 当天的两张截图：一张是一次 BTW 加一条中途引导之后，transcript 最后一段**整片空白**，而 composer 上方的状态栏仍在写「执行工具 · bash　正在执行终端工具…」；另一张是一条用户消息标着「已取消，未执行」、上面一张已回答的 BTW 卡、**没有任何 assistant 回复**，状态栏却写着「本轮已完成」（owner：「这个任务都完成了 我都不知道他回复什么 结果是什么」）。前四条是烦人，这一条是**用户会对会话状态做出错误判断并因此做出错误处置**——以为卡死去杀进程，或者以为成功去找根本不存在的结果。

两张截图的**放大器是同一个**：`Transcript.tsx` 把"这一回合完成没有"从**位置**推出来（`completed={index < turns.length - 1 || !active}`），把"会话忙不忙"只从 `session.state` 读（而 `SessionStatus.tsx` 读的是 `session.activity.phase`，两套数据源），然后在三个渲染槽位全部落空时**返回 `null`**。**触发器有两条**：服务重启把排队消息作废、把 `state` 改写（`sessions.py` 恢复路径 `1566-1570` + `_resume()` 置 `idle`），以及一条中途消息把回合切开。**重启那条是首选复现路径**——不需要凑 BTW 或 steer 的时序。包里除了修渲染，还硬性要求两件事：被重启作废的消息要有**重新发送**入口（现在只有一行小灰字，owner 完全没注意到），被打断的一轮**不许呈现成「本轮已完成」**。`sessions.py` 把作废消息标成 `cancelled` 的处理**本身是对的，不许改**；包里已经分析清楚服务端信息"一半够一半不够"，不够的那一半要停下来问 owner 才能动后端。

**T7e 的实现 base 是 `dev`（5.0.1，`f04d740e`），不是 `main`**——这是本轮唯一一个偏离"能在 4.22.x 上修就 base 在 `main`"默认规则的包，理由三条写在包内："回合按位置推 completed"两线逐字相同，但工单点名要补单测的 `apps/mms-web/tests/turn-working-status.test.mjs`、以及"不许渲染 `null`"所依赖的 `TurnWorkingStatus` / `turnWorkingHint` / `activityHints` / `.turn-working-*` 样式**全部只存在于 5.x**（gemini 的 `88114765` / `6d9001d6`），在 `main` 上实现等于把 5.x 功能回流 4.x，方向与 owner 定的流向相反。4.22.x 侧的残留（自动折叠提前触发、中间文字被当成最终回答、无重新发送入口）已在包内"残留"一节如实记下，**是否回流由 owner 决定，不在本包**。包文档本身照旧落在 `dev`。

第六轮（2026-09-16）追加 **T7c / T7d**，来自 owner 当天的两条真实故障：同事在装过旧版本的电脑上删除通道，弹出一句**猜出来的**错误文案（真实原因是 MMF 的 `blocked_reasons`，算出来了却只当布尔值用）；以及打开「手机访问」开关后，本机原本开着的 `127.0.0.1` 窗口立刻被踢掉。这两个包**互相独立、可以并行**，都建议给 k3 / deepseek（都是后端为主，各带一点前端文案），**改动面零重叠、没有任何共享文件**。**两个包的实现 base 都是 `main`（4.22.1，`6c62a656`）**——实测 owner 指定的那条六文件 diff 只有 `server.py`（117 行，全是 5.x Bot 工作台接线）和 `SettingsPage.tsx`（138 行，T6b 运行环境 tab）有差异，**两处都不落在这两个包的改动面上**；`model_settings_worker.py` / `model_settings.py` / `remote_access.py` / `ChannelModels.tsx` / `RemoteAccess.tsx` / `api.ts` / `mms_registry_cli.py` / `mms_state_io.py` 以及相关测试文件 blob hash 全部逐字节相同。唯一需要留意的合流点是 T7d 选方案 B 时会碰到 `do_POST` 的收尾行（两条线不同），包里已写明怎么合。**包文档本身照旧落在 `dev`**。

第五轮（2026-09-16）追加 **T7a / T7b**，来自 owner 当天的两条 Pilot 使用反馈（顶部红条反复出现、BTW 旁问卡片收起后又自己展开）。这两个包**互相独立、可以并行**，都建议给 gemini，改动面零重叠（唯一共享文件 `App.tsx`，两处相距一千多行）。**两个包的实现 base 都是 `main`（4.22.1，`6c62a656`）**——实测两个包要改的代码在 `main` 和 `dev` 上逐字节相同（`api.ts` / `SideQuestions.tsx` / `side-questions.ts` / `side-questions.test.mjs` blob hash 完全一致；`App.tsx` 的 64 行差异全是 Bot 工作台接线，`styles.css` 的 49 行差异是 `ModelExplorer` 重试按钮和 `.model-picker-trigger`，都不落在这两个包的改动面上），按 owner 定的"4.x 的所有改动默认进入 5.x"，修在 4.22.x 会自动流到 5.x。**包文档本身落在 `dev`**，因为 `docs/mms-web/bot-work/` 这棵树只存在于 `dev`，`origin/main` 上没有这个目录——和 T6a / T6b 是同一个形状。

第四轮（2026-09-16）追加 **T6a / T6b**，对应 owner 新定的发布模型（`main` = 4.22.x 永久稳定线，`dev` = 5.x，用户可在两条线之间升降级，同一台机器不能同时装两个）。这两个包的 **base 是 4.22.x 线**（重组后是 `main`；重组尚未完成时用 `origin/dev` = `1f466eea` = 4.22.1），**不是 5.x**——理由是 owner 定的流向是"4.x 的所有改动默认进入 5.x"，门禁写在 4.x 侧会自动流到 5.x，反过来则不会回到 4.x。同一轮把 T5a / T5b / T5c 按 `origin/dev-pre`（`77f2fd8a` = 5.0.1）重新定位了行号与基线，并给三个包各加了一节"与近期改动的冲突面"。

第三轮（2026-09-16）追加 **T5a / T5b / T5c**。这三个包的 base 是 **`dev`**（重组后 `dev` 即 5.x 线）；重组尚未完成时用 **`origin/dev-pre`**。T5a 从 base 开，**T5b 和 T5c 都从 T5a 完成后的 HEAD 开**。落地顺序 **T5a → T5b / T5c**（T5b 纯前端、T5c 后端为主，两者可并行；T5c 与 T5a 动同一批文件，不能和 T5a 并行）。三个包都验收完才一起合；owner 的硬约束是"功能要么做完，要么不做"，**后端不单独进主线**。

第二轮（2026-09-14）追加 T1c。T1c 不从 6a223c7c 开分支，而是从任务分支当时的 HEAD 开，派发前先确认主 workspace 里的几何头像改动已提交。
每个包顶部都写了范围、不许碰的文件、验收和汇报格式。

评审分工：T1 的验收里有截图比对，需要能识图的模型。glm5.3 不能识图，只做代码侧评审（hex 计数、token 使用、diff 里是否混入行为改动、build 与测试结果）；截图的视觉评审由 Claude 做。

## 分支目标（2026-09-14 起）

owner 决定（2026-09-14）：`dev` / `main` 是 4.21.x 稳定安装线，不含 Bot；Bot 工作台是 5.0，集成分支是 `dev-pre`（从撤销前的 dev 065cf856 建立）。所有 Bot 包的 PR 指向 `dev-pre`。README 其它地方写的"→ dev"按此理解。

**2026-09-16 更新**：owner 定下新的发布模型——**`main` = 4.22.x 永久稳定线**（不含 Bot），**`dev` = 5.x**，用户可以在设置里在两条线之间升降级，同一台机器不能同时装两个。底层 mms 终端能力两条线完全相同（已验证：`mms_core.py` / `mms_launchers.py` / `mms_tui.py` / `mms` / `install.sh` / `mms_platform.py` 在 `v4.22.1` 和 `origin/dev-pre` 上逐字节相同），配置共用 `~/.config/mms-next`（Single Config Root 硬规则，见 `docs/AGENT_GUARDRAILS.md`，不许改）。

**分支现状（2026-09-16 晚实测，重组已经完成）**：

| 分支 | 版本 | HEAD | 说明 |
| --- | --- | --- | --- |
| `origin/main` | **4.22.1** | `6c62a656` | **4.22.x 永久稳定线**（不含 Bot） |
| `origin/dev` | **5.x** | `e5d32243` | **5.x 线**（Bot 工作台在这里）。T7a / T7b 那轮记的是 `5bf1f31d`，此后 PR #276 已合入，2026-09-16 晚实测 HEAD 为 `e5d32243`；T7e 那轮 PR #280 也已合入，**实测 HEAD = `f04d740e`（version 5.0.1），T7e 的 base 就是它** |
| `origin/dev-pre` | 5.0.x | `2b9260d8` | 重组后闲置，**不要再用作 base** |

所以：**5.x 侧的包 base 用 `origin/dev`，4.22.x 侧的包 base 用 `origin/main`。**

⚠️ **这张表在重组前是反过来的**（`origin/dev` = 4.22.1、`origin/main` = 4.10.0 陈旧），T5a/b/c 和 T6a/T6b 正文里写的"重组尚未完成时用 `origin/dev-pre` / `origin/dev`"是当时的临时说法。**现在按上表读**：T5a/b/c → `origin/dev`；T6a/T6b → `origin/main`；T7a/T7b → `origin/main`；T7c/T7d → `origin/main`；**T7e → `origin/dev`**（唯一的例外，理由见 T7e 包内"为什么不是 `main`"）。那几份包里引用的 `origin/dev-pre` = `77f2fd8a`（5.x）与 `origin/dev` = `1f466eea`（4.22.1）行号基线仍然有效，只是分支名要按上表换过来，实现者在自己的 base 上复核行号。

**包文档本身统一放在 `dev` 的 `docs/mms-web/bot-work/`**，包括 base 在 `main` 的那几个（T6a / T6b / T7a / T7b / T7c / T7d）。原因：这棵文档树只存在于 `dev`，`origin/main` 上没有 `docs/mms-web/bot-work/` 目录，在 `main` 上另起一棵会在 4.x→5.x 合流时和这份 README 必然冲突。

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

**2026-09-16 晚在重组后的两条线上实测的前端门禁基线**（T7a / T7b 用这组）：

| 门禁 | `origin/main` = `6c62a656` = 4.22.1 | `origin/dev` = `5bf1f31d` = 5.0.1 |
| --- | --- | --- |
| `npx tsc --noEmit -p apps/mms-web` | **0 错** | **0 错** |
| `node --test apps/mms-web/tests/*.test.mjs` | **tests 56 / pass 56 / fail 0**（7 个文件） | **tests 121 / pass 121 / fail 0**（19 个文件） |
| `node --test apps/mms-web/tests/side-questions.test.mjs` | **17 / 17 / 0** | **17 / 17 / 0**（该文件两线逐字节相同） |
| `npm run build --workspace @mms/web` | 通过，css 148.95 kB / js 660.01 kB | 通过，css 223.13 kB / js 793.19 kB |

**2026-09-16 在 `origin/dev` = `f04d740e` = 5.0.1 上复测（T7e 用这组）**：`tsc` **0 错**；`node --test apps/mms-web/tests/*.test.mjs` **tests 121 / pass 121 / fail 0**（19 个文件）；`npm run build --workspace @mms/web` 通过，1916 modules，css **223.13 kB**（gzip 37.55）/ js **793.19 kB**（gzip 255.72）。与 `5bf1f31d` 那次逐项相同，PR #276 / #280 都是纯文档合入。

`apps/mms-web/tsconfig.json` 的 `include` 只有 `["src"]`，**`tsc` 不检查 `apps/mms-web/tests/*.mjs`**。

跑前端门禁之前先在 worktree 里 `npm install`。

**设计文档的路径**：是 `apps/mms-web/DESIGN.md`，**不是 `docs/mms-web/DESIGN.md`**（后者不存在）。T1e / T1f / T2c / T3c 几个旧包里写的那个路径已过期，T5 / T6 各包已订正。

## 已经确认、不得倒退的边界

来自 `docs/mms-web/CLAUDE-CONTINUATION.md`，摘要：

- 不做 Oh My OpenCode 式重编排；planner / worker / reviewer 不暴露成永久 Bot。
- 浏览器只走 Ego，不自研浏览器引擎，不复制 cookie / profile。
- 主聊天只有用户消息、Bot 回复、成果、等待提示；工具日志折叠在执行详情。
- 状态文案"待命"；自动唤醒用闹钟语义；配置 / 删除默认隐藏。
- 不把 build 通过、接口可读、测试通过当作交付。
