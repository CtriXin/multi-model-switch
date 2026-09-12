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
| T4 | 落地与交付链 | `T4-landing-governance.md` | Claude（本会话） | rebase、issue、PR 拆分、全量回归、fresh-user gate |

建议只是建议，派发给谁由用户决定。每个包顶部都写了范围、不许碰的文件、验收和汇报格式。

评审分工：T1 的验收里有截图比对，需要能识图的模型。glm5.3 不能识图，只做代码侧评审（hex 计数、token 使用、diff 里是否混入行为改动、build 与测试结果）；截图的视觉评审由 Claude 做。

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

前端测试：`node --test apps/mms-web/tests/<file>.test.mjs`，逐文件跑。后端 focused tests：

```bash
PYTHONPATH=. python3 -m pytest -q \
  tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py \
  tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py \
  tests/test_mms_bot_coordinator.py
```

当前基线：72 passed。任何包不得让这个数字下降。

## 已经确认、不得倒退的边界

来自 `docs/mms-web/CLAUDE-CONTINUATION.md`，摘要：

- 不做 Oh My OpenCode 式重编排；planner / worker / reviewer 不暴露成永久 Bot。
- 浏览器只走 Ego，不自研浏览器引擎，不复制 cookie / profile。
- 主聊天只有用户消息、Bot 回复、成果、等待提示；工具日志折叠在执行详情。
- 状态文案"待命"；自动唤醒用闹钟语义；配置 / 删除默认隐藏。
- 不把 build 通过、接口可读、测试通过当作交付。
