# MMS Bot Claude 续接上下文：产品边界、当前事实与未完成能力

Date: 2026-09-12
Owner: current Codex agent
CLI: codex
Model: gpt-6-astra
Session / task ref: 370e87ec37e741df
Status: active

## 这份文档要解决什么

这是一份给后续 Claude 会话直接读取的背景文档。它保留已经和用户确认过的产品方向、交互取舍、当前真实状态和全部未完成能力，避免用户重复解释。

不要把它当成一次性大规划，也不要因为看到“多 Bot”就自动引入 Oh My OpenCode 式的重型编排。已经确认的边界要继续遵守；未完成的能力都可以继续补齐，具体实现方式和顺序由 Claude 根据代码和真实验证自行判断。

## 产品想做成什么

MMS 现在有三种使用状态，三者要共存，但不能混成同一种产品：

1. **CLI Terminal**：用户在 MMS 中选择 Harness 和 Model，在 Terminal 里直接对话。这是最早的能力，适合熟悉工具、需要直接控制运行环境的人。
2. **Pilot Web UI**：面向所有人的 ChatGPT 式对话入口，底层仍然使用 Pi Harness。它是会话级、即时交互的工作台。
3. **Bot**：长期存在的“员工”。用户可以用简单聊天交代事情，Bot 保留自己的身份、角色、记忆、任务和协作关系。Bot 不是一次 Session，也不是 Pilot 的另一个皮肤。

Bot 的目标是一个真实可用的工作流：用户说目标，Bot 自己完成能完成的部分，需要时调用 Skill、Harness、Browser Provider 或其他 Bot，最后给出简短、清楚、像同事一样的结果。Bot 不是噱头，也不是把若干 Harness 拼成一排让用户管理。

## 用户明确在意的体验

- **像聊天软件里的同事**：主界面是自然对话，不要做成 CMS、控制台或看板。用户不需要看模型思维过程、长篇工具日志或制式化报告。
- **结果优先**：完成后先说结论、改了什么、证据在哪里、还有什么没完成。默认短句、自然表达；详细执行过程可以折叠查看。
- **允许并行任务**：用户先让一个 Bot 整理资料，又提出完全无关的事情时，系统应能并行处理，而不是所有事情在一个队列里排死。共享资源冲突时要明确说明等待原因。
- **少打扰但不隐瞒**：正常运行不要求用户确认每一个内部步骤；涉及真实副作用、权限、登录、付款、删除或不确定回执时，必须保留清晰的确认边界。
- **创建 Bot 要轻**：点击新建后应先能聊天，不要一上来用表单限制用户。默认生成一个头像/颜色和默认模型（可在设置或创建通道时配置），用户可以边聊边改名字、模型、角色指引。创建后的 onboarding 问答要能写回 Bot 预设，不能只显示一次然后丢失。
- **Bot 可管理**：必须支持改名、换模型、编辑角色、删除 Bot；删除需要清理该 Bot 关联的记忆、任务、协作记录和成果引用，并给出明确结果。
- **模型和通道分开**：模型选择沿用 Pilot 的 ModelPicker / ModelExplorer 体验；Model 与 Channel 是两个可理解、可分别修改的维度。
- **浏览器能力复用**：macOS 上如果用户已安装并授权 Ego，浏览器操作交给 Ego，不重复开发浏览器引擎。MMS 只负责统一调用、状态和结果。Windows / Linux 可以寻找 Web Access 或其他成熟 Provider，接入同一合同。
- **可预览成果**：图片和能在本地解析的文件尽量在对话内弹窗预览，点击预览而不是直接跳转。内容 URL 必须经过 hash 和目录边界检查。
- **界面细节**：不能出现横向滚动条；侧栏和内容要在常见窗口内完整可用；状态文案使用“待命”；自动唤醒要用明确的时钟/闹钟语义，不再用容易歧义的闪电；配置和删除默认隐藏，hover / keyboard focus 时出现；头像使用约 10 个 pixel 预设和多种颜色，图案、底色、选择框必须真正居中；左下角保留返回 Pilot。
- **不要暴露预设内部名称**：侧栏显示用户命名的 Bot，不要把“浏览器”“验证员”等内部角色名强行当作产品标题。产品入口用 “Bots”。

## 不能退回的架构边界

用户明确不喜欢 Oh My OpenCode 那种重编排体验。不要把每个 planner、worker、reviewer、专家模型都暴露成永久 Bot，也不要为普通请求启动一串额外模型会话。

推荐保持两层，但不强求某个具体框架：

- **Bot 层**：长期身份、角色、memory、任务、调度、收件箱、用户关系。
- **工作层**：一次任务需要的轻量计划、临时分工、Skill、Harness、Browser Provider、结果汇总。

只有用户明确创建的员工才进入 Bot 列表。一次任务产生的临时 worker 完成后交回结果，不自动变成新的 Bot。简单任务应 direct-first；分工必须有实际理由，并让用户能看到“正在等谁/为什么等”。

## 当前已经存在的代码和能力

工作区：
`/Users/xin/.local/share/stride/tasks/370e87ec37e741df/workspace`

分支：
`codex/stride-370e87ec37e741df`

后端主要入口：
- `mms_web/server.py`
- `mms_web/bots.py`
- `mms_web/bot_executor.py`
- `mms_web/bot_client.py`
- `mms_web/bot_communications.py`
- `mms_web/bot_memory.py`
- `mms_web/bot_computer.py`
- `mms_web/bot_coordinator.py`
- `mms_web/browser_provider.py`

前端主要入口：
- `apps/mms-web/src/App.tsx`
- `apps/mms-web/src/Bot.tsx`
- `apps/mms-web/src/BotStudio.tsx`
- `apps/mms-web/src/BotArtifactPreview.tsx`
- `apps/mms-web/src/BotCommunications.tsx`
- `apps/mms-web/src/BotMemoryPanel.tsx`
- `apps/mms-web/src/bot.css`

已实现的运行能力：

- Bot 创建、改名、换模型、编辑角色、删除。
- Pixel avatar 预设、颜色选择、状态/hover 样式。
- 任务状态：queued、starting、running、waiting、completed、failed、interrupted、cancelled。
- 带时区的定时任务和自动唤醒。
- requestId 去重；重启时将执行中任务标为 interrupted，不自动重放未知副作用。
- 结构化结果：结论、证据、改动、未完成事项、下一步；聊天默认显示自然语言摘要。
- Bot 间 dispatch、依赖唤醒、message / reply 信箱、回执状态和循环上限。
- Bot 独立持久 memory、关键词检索、token budget 和 idle 边界压缩。
- Ego 浏览器操作：goto、snapshot、click、fill、press、screenshot。
- 图片、TXT、Markdown、CSV、JSON、HTML、PDF、音视频等成果预览。
- 聊天式全屏 UI、Bots 侧栏、单输入框、执行详情折叠、返回 Pilot、无横向溢出。
- ModelPicker / ModelExplorer 复用 Pilot 的模型和通道体验。
- 当前状态文案为“待命”，自动唤醒使用更明确的 AlarmClockCheck 语义。
- 卡片配置/删除默认隐藏，hover / keyboard focus 时出现。
- 轻量 coordinatorPlan：对任务记录 direct/delegate、候选 Bot、原因和待确认步骤；不启动额外 planner session。
- 任务支持 priority（0–100）、稳定出队和可见 queueReason。
- EgoComputer 已实现 BrowserProvider 合同并在 capabilities 返回 provider、available、operations、scope。

## 已验证的实时事实

2026-09-12 重启后的本地服务：

- 地址：`http://127.0.0.1:60824`
- 当前响应版本：`2.2`
- executor：Pi，available=true
- maxConcurrent：3
- autoWake=true
- BrowserProvider：Ego，available=true
- Ego operations：goto、snapshot、click、fill、press、screenshot
- 实时接口当前返回 **4 个真实 Bot**：大总管、调度、日程管理、牛马。不要把旧报告中的“5 个 Bot”当成当前事实。

验证命令：

```bash
cd /Users/xin/.local/share/stride/tasks/370e87ec37e741df/workspace
npm run build --workspace @mms/web
PYTHONPATH=. pytest -q \
  tests/test_mms_web_bots.py \
  tests/test_mms_bot_runtime.py \
  tests/test_mms_bot_transport.py \
  tests/test_mms_bot_client.py \
  tests/test_mms_bot_computer.py \
  tests/test_bot_memory.py \
  tests/test_mms_bot_coordinator.py
```

最近一次结果：前端 build 通过，72 个 focused tests 通过，`git diff --check` 通过。实时页面刷新后显示“待命”和新的自动唤醒图标，连接恢复正常。

## 对 Claude 审计结果的校正

Claude 之前给出的“能力层约七成、交付层为零”的方向判断基本可信，但完成度偏乐观，不能直接当验收结论。当前可采用以下事实替代旧报告中的数字：

- focused tests 最近一次是 72 个通过，不是旧报告中的 68 个。
- 实时 `/api/v1/bots` 最近一次读回 4 个真实 Bot，不是旧报告中的 5 个。
- `Coordinator` 目前只是轻量计划记录和候选建议，还不是完整的语义 planner。
- `BrowserProvider` 目前只有 Ego adapter；Windows / Linux 适配仍为空。
- 调度已经有 priority 和 queueReason，但成本、额度和资源预算仍未完成。
- 本地运行能力已经存在，但当前 worktree 仍没有正式 issue、PR、commit、merge 或 fresh-user gate 交付证据。

这些校正是为了避免后续会话把“代码存在”“接口可读”或“测试通过”误写成产品和交付已经完成。

## 还没有完成的能力

以下都是真实缺口，后续应继续补齐；不要把“接口已经存在”当成“能力已经完成”。

### Coordinator 还不是真正的自动计划层

目前 `coordinatorPlan` 能记录 direct/delegate、候选和待确认步骤，但：

- 是否需要分工仍主要依赖中文关键字和 Bot 元数据打分。
- 实际“派给谁、等谁、如何合并”仍由执行模型决定。
- 还没有稳定的计划状态机和真正的父子任务结果图。
- 还没有 planner / worker / reviewer 的一次任务内工作层；如果增加，必须保持轻量、按需，不暴露为永久员工。
- 需要用真实任务验证“A 自动把两个独立子目标交给 B/C，B/C 完成后 A 恢复并只给用户一份结论”，但不能为此引入重型多模型链。

### BrowserProvider 只有 Ego 实现

`BrowserProvider` 合同和 Ego adapter 已有，但：

- 没有 Web Access Provider。
- 没有 Windows / Linux 的实际适配和能力探测。
- 还没有 provider 不可用时的清晰降级、等待和用户提示。
- 需要避免复制 cookie、profile、浏览器引擎或重新开发 Computer Use。

### 调度规模化仍是第一版

现在有 maxConcurrent=3、同 Bot / workspace 的串行规则、priority 和 queueReason，但还缺：

- 按 Bot、Provider、Model quota 和 workspace 做资源预算。
- 成本、预计等待时间、长任务占用和抢占/取消策略。
- 浏览器单实例冲突、同一账号登录态冲突等真实资源约束。
- 并行任务在 UI 中的清楚呈现和结果归并。

### 外部能力 adapter 尚未接入

外部成熟项目可以调查和复用，但目前没有实际 adapter。优先复用能接入 MMS/Pi 的项目，不要同时引入多套同类 runtime。接入前要证明它解决了真实瓶颈，而不是为了增加名词。

### 交付链仍未完成

当前 worktree 的改动还没有：

- 正式 issue
- PR
- commit / review / merge
- fresh-user gate 和完整交付验证

不要把“实时接口可读”“build 通过”写成已经正式发布。是否提交、建 issue、开 PR 仍需按仓库规则和当前授权处理。

## 用户能接受的渐进方式

用户接受能力分阶段补充，但不接受产品退回到“几个不同模型互相 dispatch 的控制台”。可以先做薄而可靠的合同、状态、回读和降级，再逐步补齐复杂能力。每一次迭代都要有真实可感知的收益：

- 少一次手工配置。
- 少一次重复确认。
- 更快知道结果和等待原因。
- 任务能在重启后恢复且不重复副作用。
- 浏览器在支持的系统上直接可用。
- 复杂任务可以自然并行，但普通任务仍然像一次聊天。
- UI 更像同事沟通，而不是管理后台。

## 继续工作时的判断规则

1. 先读当前代码、测试和实时服务，再判断缺口是否仍存在。
2. 用最小可行改动补齐真实行为；不要为了“架构完整”先造一套重平台。
3. 每个新能力都要有 focused test，并尽量做 60824 的实时回读。
4. 不要隐藏失败、未知回执或未验证状态。
5. 结果消息保持短、自然、面向用户；工具细节放执行详情或附件。
6. 不要把临时工作角色做成永久 Bot。
7. Browser 操作优先通过已有 Ego；其他系统做 Provider adapter。
8. 不要修改真实 MMS 配置、账号、OAuth 或生产状态，除非用户在当前上下文明确授权。
9. 保留与本任务无关的 dirty work；不要 reset、stash、clean 或覆盖其他会话的改动。
10. 如果要改变已确认的产品边界，先在交付说明中明确指出改变了什么以及为什么。

## 给 Claude 的直接续接指令

请从当前 worktree 和实时服务继续推进上述未完成能力。你可以自行探索实现顺序，但优先处理能让 Bot 真正像“长期员工”而不是“多模型控制台”的缺口。所有已确认的体验和边界必须保留，尤其是：

- 不做 Oh My OpenCode 式重编排。
- 不重复开发 Ego 已经覆盖的浏览器操作。
- 不把内部角色名强行暴露给用户。
- 不让主聊天被思维链、日志和长报告淹没。
- 不把 build、接口可读或测试通过直接当成正式交付。
- 完成后如实记录测试、实时验证、剩余未知和交付状态。
