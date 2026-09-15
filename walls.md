## 17:35 +08 · gpt-6-astra · 370e87ec37e741df
现象:新需求跨越 MMS Web、Pi session、Browser/Computer runtime 与多Bot编排，现有 Web API 主要在 mms_web/server.py，不能直接套用 runtime-api mock。
处置:建立独立 Stride worktree；并行拆分后端 service、前端组件与只读架构审查，禁止触碰真实 MMS 配置。
耗时:未单独计时 · 归因:[AGENT]

## 20:06 +08 · gpt-6-astra · 370e87ec37e741df
现象:独立审查确认首版仍是mock、重启重跑和任意artifact引用；之前wall的17:35未读时钟，不作为计时证据。
处置:补读规则并刷新至origin/dev a1348e3c；保留本任务改动备份，继续真实Pi与Ego闭环。仓库禁止未经具体授权commit，故保留task worktree和进展记录，未建立WIP commit。
耗时:未单独计时 · 归因:[AGENT]

## 20:22 +08 · gpt-6-astra · 370e87ec37e741df
现象: 子代理测试任务遇到模型 capacity；跨模块合同审查发现 complete/result、downloadData 不一致。
处置: 重新派发有界测试；修复字段合同并增加 HTTP/worker 集成测试。DeepSeek 已完成实际文件写入，完成记录需在修复后复验。
耗时: 未单独计时 · 归因:[AGENT]/[外部]

## 20:27 +08 · gpt-6-astra · 370e87ec37e741df
现象: 真实 Ego 已建 space 12，但 screenshot 回执报 EGO_INVALID_RECEIPT；CLI console.log 实际走 stderr，假测试仅 stdout 未覆盖。
处置: 同时解析 stdout/stderr，补实际传输形式测试；停止原协作任务，保留同一 space 并回填已确认 ID，不重复创建。
耗时: 未单独计时 · 归因:[AGENT]/[TOOL]

## 20:42 +08 · gpt-6-astra · 370e87ec37e741df
现象: 浏览器 UI 派发按钮保持 disabled：异步 Bot 列表首次加载后 select 视觉选中但 React botId 为空；Ego Intl 与 Date 本地时区不一致。
处置: 同步初次/侧边选择且保留手动选择；计划显示使用与解析一致的 Date getters。真实刷新后 sendEnabled=true；GLM 已定时写文件并在重启后再次按计划执行。
耗时: 未单独计时 · 归因:[AGENT]/[TOOL]

## 2026-09-11 22:58 SGT — Bot chat immersion and auto routing

- User clarified Bot workbench is Bot-scoped on one shared global computer, unlike Pilot's Folder-scoped sessions.
- Reworked Bot UI into a dark chat surface with full-screen transition, compact Bot rail, inline task events/artifacts, and one composer; Pilot shell hides while `page=bots` is active and a Pilot return control is available.
- Added deterministic `/bots/auto/tasks` routing over Bot metadata; verified against the task-owned live service with a waiting task so no model side effect occurred.
- Build: `npm run build --workspace @mms/web` passed. Targeted Bot tests: 45 passed. Full unscoped pytest remains invalid in this worktree because unrelated legacy modules are not on its default import path.

## 2026-09-11 23:20 SGT — Grok visual refinement

- Reworked the Bot surface toward the supplied Grok reference: pure black full viewport, compact Bot rail, full-height message stream, minimal top controls, floating composer dock, and reduced-motion fallback.
- Long raw executor events now render as collapsed “查看执行详情” blocks so chat remains readable while evidence stays available.
- Final visual QA captured `.stride-output/bot-chat-window.png` from the task-owned browser space after cache-bypassed reload.

## 2026-09-12 00:05 SGT — User-facing Bot transcript cleanup

- User reported raw Markdown, empty conversation rows, and CLI process details leaking into the Bot chat.
- Added `RichText` rendering for prompts, messages, results, and errors; GFM tables now render as tables.
- Main chat filters empty/instruction/CLI diagnostic events and keeps only user-facing Bot content plus waiting/actions; underlying task events remain available in task state.
- Validation: web build passed; targeted Bot runtime/transport/client/computer/web tests passed 45/45; visual screenshot `.stride-output/bot-chat-markdown.png` captured from the task-owned live service.

## 2026-09-12 00:32 SGT — Task tabs and process leakage removed

- User clarified that task tabs, “接受结果”, and “打开会话” expose implementation concepts in a Bot chat.
- Changed the main transcript to one continuous Bot-scoped conversation across that Bot's tasks; removed task tab blocks and the two technical action buttons.
- Added typed `sourceKind` mapping so tool/notice events remain technical evidence but do not render as chat; empty assistant stream markers are skipped and old n-/t- records are classified read-only.
- Validation: GLM live QA shows 2 prompts, 2 final results, 0 task-tab blocks, 0 process events, 0 empty messages, and no “接受结果”/“打开会话”; styled black chat screenshot at `.stride-output/bot-chat-glm-clean.png`.
耗时:未单独计时 · 归因:[AGENT]/[TOOL]

## 2026-09-12 Memory v0 + Context Budget continuation
- Scope: add per-Bot durable memory (curated facts + bounded task summaries), lexical retrieval/injection, worker memory commands, memory HTTP view/mutations, and Bot-level context budget/soft compaction settings with honest live/cached/unknown context evidence.
- Success: focused Python tests + web build pass; real task-owned service verifies memory survives a follow-up/model-session boundary and Bot isolation; UI shows memory/settings without exposing Pi tool logs by default.
- Protected surfaces: no global MMS config, no account/OAuth/secrets, no production release, no unrelated Pilot chat flow, no broad Hermes/channel gateway.
- Rollback: revert only task-owned worktree changes; restart task-owned service with prior dist/source. Preserve current state and unrelated dirty files.

## 2026-09-12 01:03 SGT — Memory v0 verification
- `PYTHONPATH=. pytest -q tests/test_bot_memory.py tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py tests/test_mms_bot_client.py tests/test_mms_bot_computer.py`: 54 passed.
- `npm run build --workspace @mms/web`: TypeScript + Vite passed.
- Restarted task-owned Bot service only (old PID 55394 -> new service PID observed 55394 replacement 76263 PTY; actual API identity read after restart). Existing Pi sessions were stopped before restart.
- Real API readback: GLM Bot memory GET/POST remember/search worked; settings update readback returned memoryBudgetTokens=2500 and compactAtPercent=75; DeepSeek Bot remained isolated with no GLM note. Context source showed cached, window 1,048,576, used 67,354, rounded UI to 6.4%.
- Real browser QA in named space `MMS Bot final markdown QA`: Memory drawer opened from Bot chat; showed per-Bot notes/settings/context, and rounded context usage. No new browser space created.
- Correction: post-patch `/api/v1/update/identity` reports the task-owned service process PID as 55705.
- Delivery check found one regression in `test_missing_adapters_are_live_empty_without_writes`: MemoryStore constructor eagerly created a state directory. Removed eager mkdir; storage is now created only when memory is accessed/written. Focused server + memory retest: 12 passed, 4 subtests passed.
- Final task-owned service restart after all source/build changes: API identity PID 57121; all three existing Pi sessions read back as stopped before restart and remain stopped after restart.

## 2026-09-12T09:15:16+08:00 · Bot peer messaging
- tracker=Stride 370e87ec37e741df, attempt=c78bd94a7b0f4d6b; existing isolated codex/stride-370e87ec37e741df worktree, prior Bot changes preserved.
- Scope: durable peer messages/replies, queued wake and bounded auto exchanges; show real sender/recipient and expandable pair conversation including historical handoffs. Validation: scheduler/worker/HTTP regressions, web build and live Pi exchange + UI readback.
- Protected: real global config/accounts, unrelated Pilot flows and production. Rollback: only this attempt changes; preserve old state schema compatibility and all saved task evidence. No publish or commit.

## 2026-09-12 · Bot peer messaging iteration
- Added durable communication mailbox with explicit `message`/`reply`, queued delivery, wake endpoint, receipt states, and max 8 automatic hops. `dispatch` remains task dependency handoff.
- Added expandable communication drawer/markers in Bot Chat; user-facing messages show sender/recipient and keep Markdown while filtering CLI/process details. Composer targets selected Bot.
- First focused test exposed an incorrect unauthorized-reply assertion in the new test (the tested reply was actually valid); corrected the fixture to reply to a message sent by the current Bot. Final focused tests: 49 passed, 4 subtests passed; web build passed.
- Live task-owned service restarted after all changes with all existing Pi sessions stopped. API returned 3 historical communication records (dispatch processed; two result records processed); browser showed `协作 · 3` and message marker in existing named space.

## 2026-09-12 10:20 SGT — chat-native Bot correction
- User feedback: Mission Board felt like a CMS console; Bot should feel like a colleague in a chat.
- Changed: removed BotMissionBoard from BotStudio, removed its CSS/component, render task results as Bot messages, and tightened executor prompt to default to 1–3 natural sentences.
- Verification: `npm run build --workspace @mms/web` passed; 52 focused MMS Bot tests passed; Ego task space `MMS Bot final markdown QA` confirmed Board and “最终结果” label are absent while chat window and Bot reply remain visible.

## 2026-09-12 10:35 SGT — v2.2 chat-native redesign
- Generated implementation reference at `docs/mms-web/design/bot-chat-v2-reference.png` with built-in image generation.
- Reworked Bot UI toward a chat app: “同事” rail, initials/colored avatars, open conversation surface, result-as-message, restrained composer.
- Composer now dispatches every new message as a separate task so unrelated goals can run concurrently; task-specific follow-up remains available in the inspector.
- Verification: build passed, 52 focused Bot tests passed, Ego snapshot confirmed colleagues/chat and absence of board/result panel labels.
- Final polish: Bot results now prefer the structured `outcome.summary` in chat, keeping evidence out of the conversational bubble while leaving attachments available.

## 2026-09-12 10:50 SGT — overflow and pixel avatars
- Added hard `overflow-x: hidden`/wrapping rules to the Bot surface; Ego measured document width equal to viewport width with no horizontal overflow.
- Added ten code-native 7x7 pixel avatar presets and six colors; Bot editor exposes all templates and color swatches, persisted through Bot API fields `avatarId`/`avatarColor`.
- Existing Bots get stable id-based fallback avatar/color; new Bots can customize before saving.
- Verification: build passed, 52 focused Bot tests passed, Ego confirmed no horizontal overflow and 10 avatar options plus color picker.
- Final overflow hardening: code blocks and Markdown tables wrap instead of exposing horizontal scroll controls.
- Final checks: build passed, 53 focused Bot tests passed, Ego measured no document/body width overflow.

## 2026-09-12 11:15 SGT — Pilot-aligned model picker
- Bot editor now reuses Pilot `ModelPicker`/`ModelExplorer`: model directory and channel routes are separate, with a short explanatory hint.
- Added avatar picker payload preservation to model edits; fixed auto-wake checkbox alignment to a compact inline row.
- Verification: build passed, 53 focused Bot tests passed, Ego confirmed editor, separate model/channel explorer, and alignment labels.

## 2026-09-12 11:35 SGT — visual follow-up
- Pilot model/channel semantics confirmed in Bot editor; build and focused tests remained green after picker integration.
- Added fallback for generic bot greeting: new casual turns avoid “MMS Bot” identity and use short colleague language.
- Replaced final result check icon with the Bot pixel avatar and clipped all chat overflow paths. Ego snapshot confirmed no page horizontal overflow and new casual response visible.

## 2026-09-12 12:00 SGT — Grok-style chat cleanup
- Restored visible `返回 Pilot` action inside the Bot conversation header; removed the hidden toolbar-only exit path.
- Chat no longer renders repeated “你” / Bot names beside every message; avatar and bubble alignment carry speaker identity.
- Pixel avatar background now derives from the selected avatar color; final replies use the same Bot avatar.
- Suppressed legacy internal collaboration/progress sentences from the primary chat view and added a no-horizontal-scrollbar rule.
- Ego confirmed Pilot action visible, speaker labels hidden, and no horizontal page overflow; frontend build passed.

## 2026-09-12 12:20 SGT — composer alignment hardening
- Tightened the Bot composer box model: outer shell, textarea, footer, and send control now use explicit sizing; the send button keeps a fixed 36px slot and long text cannot widen the row.
- Set horizontal overflow clipping on the composer/textarea and constrained the footer label so narrow layouts do not expose a horizontal scrollbar or clip the send control.
- Verification: frontend build passed; 53 focused Bot tests passed; Ego measured page, stream, and composer overflow as false, with textarea/footer/send right edges aligned at 1418px and the Pilot action visible.

## 2026-09-12 12:35 SGT — Bot naming polish
- Renamed the left rail heading from “同事” to `Bots`; the create action now reads “创建 Bot”, and the empty state no longer calls a Bot a colleague.
- Replaced concrete preset-name examples such as “浏览器” with professional role examples: “发布协调器”, “整理需求、执行任务并回传结果”, and concise role guidance.
- Updated the chat composer fallback and Bot docs to use `Bot` / `Bots` terminology. Ego confirmed the new heading, action label, placeholders, and no horizontal overflow.

## 2026-09-12 12:50 SGT — in-chat image preview
- Screenshot and image artifacts in the Bot conversation now use an in-place preview button; they no longer navigate to the raw content URL or open a second tab.
- Added a focused lightbox with the artifact name, close button, background click, `Esc` close, contained scaling, and no page-width expansion. Non-image files retain their normal file links.
- Verification: build passed; 53 focused Bot tests passed; Ego clicked a real screenshot artifact, confirmed the lightbox and unchanged conversation URL, then closed it with `Esc`.

## 2026-09-12 13:05 SGT — avatar picker alignment
- Normalized avatar option cells with fixed square proportions, explicit box sizing, centered grid alignment, and a stable color-swatch row.
- Removed native avatar `title` tooltips that overlapped the picker and made the selected outline look misaligned in screenshots.
- Verification: build passed; Ego confirmed all ten avatar cells have the same 41px height, six color swatches share one baseline, and no avatar title tooltip remains.

## 2026-09-12 13:25 SGT · current-agent · 370e87ec37e741df
现象:重启 task-owned MMS 服务时，指定的 `/opt/homebrew/bin/python3.14` 不存在，首次启动未监听端口。
处置:改用当前 `python3` 入口重启；60824 已监听，服务日志显示 MMS Pilot 正常启动。
耗时:未单独计时 · 归因:[AGENT]

## 2026-09-12 13:40 SGT · current-agent · 370e87ec37e741df
现象:对话中的 `collaboration.txt` 仍是大块文件链接，无法像截图一样就地查看。
处置:新增统一文件预览层；TXT/Markdown/CSV/JSON/HTML/PDF/音频/视频和图片均改为当前对话弹窗预览，HTML 通过离线清洗预览，超限或未知格式保留下载；文件卡片改为固定紧凑高度，避免空白撑高。
验证:前端 build 通过；59 个 Bot/Pilot transport focused tests 通过；Ego 点击真实 `collaboration.txt` 后弹窗显示 `CHILD CALLBACK PASS`，URL 保持 `#page=bots`；图片弹窗回归通过。
耗时:约 20 分钟 · 归因:[AGENT]

## 2026-09-12 13:55 SGT · current-agent · 370e87ec37e741df
需求:将 `返回 Pilot` 放到 Bot 工作台左下角。
处置:从对话头部移除重复入口，在左侧 Bots 导航底部新增固定 `返回 Pilot` 按钮；侧栏使用纵向布局，入口自动贴底并保持窄屏可用。
验证:Ego 测得按钮位置 left=14、bottom=930（视口高度 950），聊天头部不再出现 Pilot；点击后成功进入 Pilot 首页，再恢复 Bot 工作台。
耗时:约 10 分钟 · 归因:[AGENT]

## 2026-09-12 14:10 SGT · current-agent · 370e87ec37e741df
现象:发送按钮中的纸飞机 SVG 按钮内偏左；顶部刷新按钮与记忆/协作/状态不在同一条视觉基线。
处置:为发送按钮补齐明确的 `align-items`/`justify-content: center`；将刷新工具栏下移到聊天头部的同一中心线。
验证:Ego 测量发送按钮 36×32，SVG 位于 x+7/y+8；刷新按钮 y=28、SVG y=38，与头部控件 y=33–48 对齐；页面截图确认视觉位置正常。
耗时:约 10 分钟 · 归因:[AGENT]

## 2026-09-12 14:35 SGT · current-agent · 370e87ec37e741df
需求:创建 Bot 后像 Grok 一样通过几轮轻问答了解使用习惯，并把回答变成长期工作预设。
处置:新增创建后 onboarding 对话卡：依次确认主要工作类型、回报粒度、推进自主度；完成后自动写入 Bot 的 `systemPrompt`，之后每次 Pi 任务都会带上这些偏好。保存失败会在对话卡内显示可重试错误，不引入额外模型调用。
验证:前端 TypeScript/Vite build 通过；新 Bot 在无任务且无角色指引时进入 onboarding，已有 Bot 或已配置角色的 Bot 保持原有空状态。
耗时:约 25 分钟 · 归因:[AGENT]

## 2026-09-12 13:35 SGT · current-agent · 370e87ec37e741df
需求:新建 Bot 不应先弹出受限表单；应像 Grok 一样先得到一个可聊天的默认 Bot，再逐步完善设置。
处置:创建入口现在直接生成“新 Bot”，随机匹配 pixel 头像与颜色并进入聊天；保留首次轻量 onboarding，名称和默认模型可通过自然语言在聊天中修改。模型可留空，执行时由当前 MMS 可用的默认 Pi preset 兜底；已有“编辑 Bot”入口仍保留给高级设置。
验证:真实 Bot 页面点击“创建 Bot”后直接出现“新 Bot”对话和 onboarding，无创建表单；前端 build 通过；60 个 Bot/Pilot transport focused tests 全部通过，并新增未选择 preset 的创建回归。
耗时:约 20 分钟 · 归因:[AGENT]

## 2026-09-12 14:02 SGT · current-agent · 370e87ec37e741df
需求:补齐 Bot 删除、聊天改名/改模型和 onboarding 回答恢复。
处置:新增带确认的 Bot 删除入口与受保护的 `/bots/:botId/delete`；删除会清理 Bot 私有记忆、任务/消息、协作记录和截图成果，执行中或协作中的任务会拒绝删除。聊天设置支持“你以后叫…”、“用 glm5.2 吧”等自然说法；onboarding 选择会立即写回角色预设，回答卡可点击重新选择，顶部“预设”按钮可随时打开调整。允许任务等待时修改名称和角色指引，模型切换仍遵守当前执行保护。
验证:前端 build 通过；62 个 focused tests 通过；Ego 实测改名、模型切换提示、回答切换后恢复、删除确认与删除后 Bot 列表更新。
耗时:约 25 分钟 · 归因:[AGENT]

## 2026-09-12 14:22 SGT · current-agent · 370e87ec37e741df
需求:修复编辑 Bot 弹窗溢出、头像选择器在窄窗口错位的问题。
处置:统一弹窗及后代元素为 border-box，限制最大宽度并允许直接子项收缩；头像预设改为按可用宽度 auto-fit 换列，去掉固定 5 列造成的横向溢出。
验证:前端 build 通过；62 个 focused tests 通过；Ego 实测刷新后编辑弹窗居中、输入框/模型选择器完整落在弹窗内，头像 10 项同基线排列，保存按钮可关闭弹窗且无错误提示。
耗时:约 8 分钟 · 归因:[AGENT]

## 2026-09-12 14:28 SGT · current-agent · 370e87ec37e741df
需求:Bot 列表减少常驻操作按钮，并修复头像选择器像素图案偏移。
处置:配置/删除按钮默认透明且不可点击，卡片悬停或键盘聚焦时显示；无 hover 能力的触摸设备保持可用。头像选择格移除多余内边距，让固定像素头像在选择边框内严格居中。闪电 tooltip 继续明确为自动唤醒，避免与就绪状态混淆。
验证:前端 build 通过；Ego 刷新页面后列表默认只显示闪电，卡片内容不再被两个操作图标打断；相关编辑弹窗回归已通过。
耗时:约 7 分钟 · 归因:[AGENT]

## 2026-09-12 14:34 SGT · current-agent · 370e87ec37e741df
需求:优化 Bot 状态文案、自动唤醒图标和头像识别感。
处置:Bot idle 状态改为“待命”，使用柔和蓝灰色状态点；自动唤醒图标由闪电替换为 AlarmClockCheck，保留明确 tooltip；卡片加入按状态和 hover 的轻量头像光晕/位移反馈。
依据:参考 Grok Bot 官方设计中“Bot 头像承载身份与状态、细节按需显示”的原则，避免堆叠独立控制层。
验证:前端 build 通过；Ego 刷新后列表和标题栏均显示“待命”，自动唤醒显示时钟确认图标，卡片默认保持简洁。
耗时:约 10 分钟 · 归因:[AGENT]
## 2026-09-12 15:20 SGT · current-agent · 370e87ec37e741df

需求:补齐 Claude 审计指出的 Coordinator、BrowserProvider 和调度规模缺口。

处置:新增轻量 coordinatorPlan（不启动额外 planner session），记录 direct/delegate、候选和待确认步骤；任务支持 0-100 priority、稳定出队和可见 queueReason；EgoComputer 纳入 BrowserProvider 合同并在 capabilities 暴露 provider/operations；任务详情展示协作计划和排队原因。

验证:前端 build 通过；72 个 focused tests 通过；60824 重启后实时 status 返回 version 2.2、Ego provider available=true、4 个真实 Bot；Ego 页面回归显示“待命”和新自动唤醒图标，无连接错误。

耗时:约 25 分钟 · 归因:[AGENT]

## 2026-09-12 16:05 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:接管 Bot 深化阶段的进度管理；为其它模型准备可派发的工作包，本轮重点是界面视觉（主题只有黑色、布局对齐混乱、后台味）。
处置:新增 docs/mms-web/bot-work/ 五份文档：README（并行规则、分支策略、通用验收）、T1 界面视觉系统（token 化、单一左边缘 gutter、附件规格、列表卡图标簇修法、onboarding 入流）、T2 Coordinator 计划层（schema 化模型计划、runtime 执行子任务、计划块可见）、T3 退避重试与结果送达（页面通知 + webhook）、T4 落地与交付链（Claude 负责）。诊断依据：bot.css 225 处 hex、三层叠加覆盖、`.bot-chat-artifacts` 三处 margin-left 冲突、BotCard 绝对定位闹钟图标；origin/dev 已到 2614c6b6，基线差 10+ 提交。
验证:只读核对代码与截图，未改任何产品代码；未运行构建与测试（本条无代码改动）。
耗时:约 35 分钟 · 归因:[AGENT]

## 2026-09-12 16:30 SGT · current-agent · 370e87ec37e741df
需求: 执行 T1 工作包（Bot 界面视觉系统重做）：全面 token 化、单一左边缘 gutter（40px 对齐）、附件卡片规格化、BotCard 图标簇修法（去绝对定位）、BotOnboarding 对话流内嵌入、去除顶部开发刷新按钮。
处置:
1. 色彩与 Token 系统重构：
   - 移除 200+ 处硬编码 hex 与三层历史覆盖；
   - 全部样式重构为 `--bot-*` 语义变量，映射至系统 `var(--accent)`, `var(--surface)`, `var(--line)` 等；
   - 严格满足硬性指标：`grep -c "#[0-9a-fA-F]\{3,8\}" apps/mms-web/src/bot*.css` 合计仅 12 处（全部分布在 `:root` 与 `:root[data-theme="dark"]` 中的 6 个头像预设色，`bot-memory.css` 与 `bot-communications.css` 为 0 处 hex）。
2. 内容对齐基线（`--bot-gutter: 40px`）：
   - Bot 侧回复正文、产物附件网格、等待提示（Wait Notice）、协作跳转条、错误卡片统一以 40px 基线对齐；
   - DevTools 实际测量左边缘坐标：`botEventBody: 604px`、`artifacts: 604px`、`notice: 604px`、`error: 604px`、`commsMarker: 604px`，实现严格垂直共线。
3. 组件精细化与布局收敛：
   - BotCard：单行紧凑布局（高度 68px），左侧 28px 像素头像，中间名称 + 状态点 + 行内 `· 自动唤醒`，第二行单行省略描述；hover 呈现 `MoreHorizontal` 原生菜单（编辑/删除），消除所有 `position: absolute` 图标叠加。
   - 对话 Header：固定 64px 高度，1px 下边框，移除测试残留「刷新」按钮与调试药丸，保留「记忆」与「协作」入口。
   - 输入框（Composer）：悬浮卡片式输入区，圆角 14px，浅阴影，focus-within 强调色描边；定时功能收敛为紧凑按钮与内联 datetime-local 选择器带清除；32x32px 纯色圆角发送按钮。
   - 工作预设（BotOnboarding）：作为对话流第一条 Bot 打招呼气泡消息呈现，支持交互 Chip 选择（工作重心、回报方式、推进方式），选中反馈并可保存。
   - 附件规格：图片固定 200×125px 卡片，文件固定 44px 高度单行条目。
   - 响应式保障：1440px / 1024px / 768px / 400px 视口全无横向滚动条；400px 移动端自然块级流式排布，无元素重叠。
4. 文档与测试：
   - 更新 `apps/mms-web/DESIGN.md`，追加「Bot 页面（2026-09-12）」设计规范；
   - 新增 `apps/mms-web/tests/bot-visual-system.test.mjs`，覆盖色彩映射、状态文案、等待原因与 CSS Token 门禁。
验证:
- git diff --stat:
```text
 apps/mms-web/DESIGN.md                  |   32 +
 apps/mms-web/src/Bot.tsx                |  532 +++----
 apps/mms-web/src/BotStudio.tsx          |   32 -
 apps/mms-web/src/bot-communications.css |  347 ++++-
 apps/mms-web/src/bot-memory.css         |  469 +++++--
 apps/mms-web/src/bot.css                | 2344 +++++++++++++++++++++----------
 6 files changed, 2565 insertions(+), 1191 deletions(-)
```
- 测试命令与结果：
  - `node --test apps/mms-web/tests/*.test.mjs`: 21 passed, 0 failed.
  - `PYTHONPATH=$PWD python3 -m pytest -q tests/test_mms_web_bots.py tests/test_bot_memory.py tests/test_mms_bot_coordinator.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py tests/test_mms_bot_client.py tests/test_mms_bot_computer.py`: 72 passed.
  - `npm run build --workspace @mms/web`: TypeScript + Vite build 成功通过。
- 截图证据路径（保存在 docs/mms-web/design/t1/）：
  - `01-light-mode.png`: 浅色模式全功能对话页
  - `02-dark-mode.png`: 深色模式全功能对话页
  - `03-accent-cyan-dark.png`: 青色强调色（深色模式）
  - `04-accent-orange-light.png`: 橙色强调色（浅色模式）
  - `05-width-1024px.png`: 平板 1024px 视口
  - `06-width-400px.png`: 移动端 400px 视口（单列无横向滚动）
  - `07-bot-card-hover.png`: 侧边栏 Bot 卡片 hover 态
  - `07b-bot-card-menu.png`: 侧边栏 Bot 卡片操作菜单弹出态
  - `08-composer-schedule.png`: 底部输入框定时选择器展开态
  - `09-bot-onboarding.png`: 对话流内工作预设向导初态
  - `10-bot-onboarding-all-selected.png`: 工作预设 Chip 选中态与保存按钮
- 状态记录：在独立 worktree `wt-T1`（分支 `bot/T1-ui`）完成，未执行 git commit、push 或 merge；60824 端口未接触，验证服务（61101）已安全关闭。
耗时:约 45 分钟 · 归因:[AGENT]


## 2026-09-12 16:35 SGT · deepseek-v4-flash · 370e87ec37e741df
需求:执行 T3 工作包（失败重试与结果送达）：基础设施错误有限退避重试、任务结果页面通知与签名 webhook；不得倒退幂等边界，不重启 60824，只改 T3 允许的文件。
处置:新增 `mms_web/bot_retry.py`（classify 覆盖 transient/permanent、30s/2min/8min 三次退避、three-attempt 失败摘要）和 `mms_web/bot_notify.py`（事件日志 notifications.json、5s 超时+失败重试一次的 HMAC webhook、配置 notify.json）。`bots.py` 只在 `_finish`（starting 阶段 transient 重排、终态 emit）、`tick`（retry.nextAt 到期出队）、`_launch`（透传错误码/状态）和 wake/追加消息处做最小插入；`server.py` 增加 `GET /bots/notifications` 与 `GET|POST /bots/notifications/config`。前端：`types.ts` 增加事件类型，`BotStudio.tsx` 轮询未读、桌面通知（仅授权且页面不在前台）、`#page=bots&bot=&task=` 深链和侧栏未读区（Bot.tsx 不许改，未读点落到侧栏通知区），`BotMemoryPanel.tsx` 增加“通知”小节（开启桌面通知 + webhook 列表/事件多选/secret）。新增 `tests/test_mms_bot_retry.py`、`tests/test_mms_bot_notify.py`；`docs/mms-web/BOTS.md` 追加 v2.3 一节。
验证:focused pytest 116 passed（基线 72，只增不减；含 classify 错误码矩阵、starting/running 边界、三次退避、取消清空、重启恢复、webhook 签名/超时不阻塞/失败重试、since 过滤、路由读写）。`npm run build --workspace @mms/web` 通过；前端 4 个测试文件各 4 passed。真实实例（61777/61778，`--state-root /tmp/bot-verify-t3/*`，未触碰 60824 和真实 config 写入）：stub pi 让 `_launch` 抛 LAUNCH_FAILED 502，实际观察到 08:16:53Z → 08:17:24Z → 08:19:25Z → 08:27:26Z 三轮退避后 failed，失败消息含三次时间与原因；task.retrying×3 + task.failed 事件可从 `GET /bots/notifications` 读到。定时任务（runAt +5min）完成后，本地 receiver 收到 `X-MMS-Event: task.completed`、`X-MMS-Signature: sha256=...`（独立 HMAC 复算一致），body 含 Bot 名、一句话标题、200 字内摘要和 `#page=bots&bot=&task=` 链接；首次返回 500 的 flaky receiver 真实观察到同一签名重投一次后成功。证据：`docs/mms-web/design/t3/{retry-timeline.log,webhook.log,flaky.log}` 与两张 UI 截图。
未完成/未验证:Ego 任务空间在页面点击“开启桌面通知”时弹出真实权限提示，ego-browser 已把空间交给用户控制（`takeOverTaskSpace` 需用户处理后才能继续），因此“未读徽标 + 桌面通知弹出”的浏览器侧截图尚未完成；webhook 与事件日志的真实证据已完成。仅剩这一条 UI 侧证据待用户处理弹窗后补。复现构建：本 worktree 未安装 node_modules，构建时临时 symlink 了主 workspace 的 node_modules（已删除），重新构建前需 `npm install` 或自行 symlink。
耗时:约 70 分钟（含约 11 分钟真实退避等待） · 归因:[AGENT]
# walls · bot/T2-coordinator

## 2026-09-12 16:45 SGT · k3 · 370e87ec37e741df

需求:T2 Coordinator 计划层落地——把"要不要分工、派给谁、等谁、用什么模型"从 Pi 提示词拿出来，变成落库、可见、可执行、可测试的计划对象。

包:T2
分支 / worktree:`bot/T2-coordinator` · `/Users/xin/.local/share/stride/tasks/370e87ec37e741df/wt-T2`（从 c280dd3b 创建，未提交、未 push）

处置:
- `mms_web/bot_coordinator.py`:新增 `build_planner_prompt`（用户目标 + Bot 名单 + 记忆摘要 + 严格 JSON schema）、`sanitize_plan`（按真实 Bot 名单校验，dependsOn 只允许引用前面 step、结构上不可能成环，自派/未知 Bot/空 goal 一律丢弃）、`parse_model_plan`、`direct_plan`；原 `make_plan` 关键词逻辑保留为兜底。
- `mms_web/bot_executor.py`:新增 `PiBotExecutor.plan()`——用任务 Bot 自己的 preset 发一次性 planner 请求，20 秒硬上限，返回最后一条 assistant 文本或 None；session 用完即停止并归档（manage archived=True），不常驻、不留在侧栏。任务 prompt 在 delegate 计划已决时加一句"分工计划已由系统决定并执行"。
- `mms_web/bots.py`:`BotRuntime.plan_task`（planner=model/keywords/off；失败/超时退回关键词并标 source=fallback；planResolved 只写一次）；`_advance_plan`（按 dependsOn 顺序创建子任务，沿用 dispatch 五层/同链守卫，taskId 对账保证重启不重复创建，dep 失败标 blocked 不重试）；`_launch` 在启动会话前过计划门（delegate→父任务 waiting/children 或 plan-approval，不开 owner session；恢复轮凭 planExecutedAt 不再进入 delegate 分支）；`_resume_children` 恢复提示带各子任务 outcome.summary 且有 pending step 时不提前恢复；`plan_action` 支持 approve/reject/replace（replace 按真实名单重新校验；auto/approved 状态 30 秒内可撤回，撤回即取消未终态子任务并转 direct）；Bot 新增 `planner` 字段（默认 model），`orchestrationPolicy` 落实为 direct-first/plan-approve/off；plan-approval 不占并发名额、不可被 wake 绕过。新逻辑全部是新方法，未重排已有函数。
- `mms_web/server.py`:只加 `POST /api/v1/tasks/:id/plan` 一个路由。
- 前端:新增 `BotPlan.tsx` + `bot-plan.css`（token 化，`--bot-gutter` 40px 左缘对齐，待 T1 合并后对齐其规范）；`Bot.tsx` 仅在首条用户消息后插入一行 `<BotPlan task={conversationTask} bots={bots} />`（外加 import、`PixelAvatar` 加 export、BotTask 换用共享 `BotTaskPlan` 类型——类型编译需要，未动其它逻辑）；`types.ts` 加 plan 类型。计划块显示 reason、每步 Bot 头像+名字+目标+状态点、可展开依赖与模型；proposed 时显示"确认分工/拒绝，自己做"，auto/approved 30 秒内显示"撤回分工"。
- `docs/mms-web/BOTS.md` 追加"Coordinator 计划层（T2）"一节。

改动文件（git diff --stat）:
```
 apps/mms-web/src/Bot.tsx          |  15 +--
 apps/mms-web/src/types.ts         |  26 ++++
 docs/mms-web/BOTS.md              |   8 ++
 mms_web/bot_coordinator.py        | 150 +++++++++++++++++++--
 mms_web/bot_executor.py           |  49 ++++++-
 mms_web/bots.py                   | 236 ++++++++++++++++++++++++++++++++-
 mms_web/server.py                 |   2 +
 tests/test_mms_bot_coordinator.py |  63 ++++++++-
 tests/test_mms_bot_runtime.py     | 271 +++++++++++++++++++++++++++++++++-
 新增: apps/mms-web/src/BotPlan.tsx, apps/mms-web/src/bot-plan.css, docs/mms-web/design/t2/(4 截图 + 4 任务 JSON)
```

测试（实际执行）:
- `PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py tests/test_mms_bot_coordinator.py` → **85 passed**（基线 72 + 新增 13：plan JSON 解析合法/缺字段/非 JSON/fenced 4 条 + prompt 构建 1 条；delegate 按 dependsOn 顺序建子任务、父恢复仅一次、重启不重复创建、planner=off、超时兜底、approve/reject/30s 撤回/replace 校验 8 条）。
- `npm run build --workspace @mms/web` → 通过（tsc + vite）。
- `node --test apps/mms-web/tests/*.test.mjs` 逐文件 → 4 文件全 pass（各 4 项，共 16 pass 0 fail）。

实时验证（端口 61202，独立实例，state-root /tmp/bot-verify-t2，未碰 60824、未写真实配置）:
- 真实链路（roadmap P0-1 验收）:创建 调度A/写手B/写手C（glm-5.3），给 A 发"让 写手B 写 b.txt 内容 hello，让 写手C 写 c.txt 内容 world，都完成后告诉我两个文件的字节数"。结果:模型计划 delegate（source=model），B/C 各一个子任务，A waiting/children；两子任务完成后 A 只恢复一次并只给用户一条结论（"b.txt 5 字节、c.txt 5 字节，共 10 字节"）。b.txt/c.txt 实际写入并经 od -c 复核（验证后已删除）。
- 反向:"把工作目录里的 txt 文件列出来" → 模型计划 direct，0 子任务，直接完成。
- plan-approve 链路:A 改 plan-approve 后发协作任务 → waiting/plan-approval、0 子任务、UI 出现"确认分工/拒绝，自己做"；在 UI 点"确认分工" → approve → 2 子任务创建 → 全部完成 → A 汇总（d.txt foo 3 字节、e.txt bar 3 字节，验证后已删除）。
- 截图:`docs/mms-web/design/t2/plan-block-delegate.png`（计划块+最终结论）、`plan-block-dark-tokens.png`（深色 token 预览）、`plan-proposed-actions.png`（待确认按钮）、`final-conclusion.png`；三个任务 + approve 任务的脱敏 JSON 同目录（API 视图本就不含 token）。
- 验证后:ego task space 10 已 finish，61202 实例已停，测试文件 b/c/d/e.txt 已删除。

偏离与说明:
- 计划计算放在 `_launch` worker 线程（状态 starting）而非 tick 的 queued→starting 转换里:模型调用最长 20 秒，不能占调度锁；文档"进入 starting 前"的意图（执行前必过计划门）保持不变。
- T1 未合并，计划块在当前浅色 token 下渲染正常；Bot 页其余部分仍是 bot.css 硬编码黑色（T1 范围），与本包无关。
- worktree 根有 `node_modules → ../workspace/node_modules` symlink 仅供跑 build/测试，**不要提交**。

未完成 / 未验证:
- 30 秒撤回按钮的真实浏览器点击未单独截图（后端 reject 路径有单测 + API 实测 approve；撤回窗口逻辑由单测覆盖）。
- 子任务 presetId 覆盖（每子任务换模型）有单测与字段链路，未做双模型真实链路演示。
- planner 会话在 Pilot 侧栏会短暂出现"计划 · <Bot>"条目（结束后自动归档）；是否完全隐藏留给后续产品决定。

耗时:约 75 分钟 · 归因:[AGENT]

## 2026-09-12 17:40 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:核对 T1/T2/T3 三个工作包并落地。
处置:复跑三包测试（72/85/116）与三包合并（129 passed、build、21 node tests）；按 T1→T3→T2 合并进任务分支，T2 四处冲突两边保留；重建 mms_web_static；提交作者按实际执行模型署名（gemini-3.6 / deepseek-v4-flash / kimi-k3），committer 为 Claude。父 issue #238，PR #239/#240/#241 指向任务分支，推送后由 GitHub 标记 merged。
验证:合并后 129 passed，前端 build 通过，hex 12；集成实例 61300 status 与 notifications 路由可读，已停止。未做合并后页面截图与桌面通知弹窗验证。
耗时:约 40 分钟 · 归因:[AGENT]

## 2026-09-12 18:20 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:T4 交付链收尾。
处置:任务分支合并 origin/dev（4.20.0，仅生成的 mms_web_static 冲突，已重建）；PR #242 → dev；60824 用合并后代码与原 state root 重启供用户预览。
验证:fresh-user gate PASS（669 passed）；全量基线对比 base 63/2394 失败、head 63/2523 失败，本分支未新增失败；结果已评论到 PR #242。
耗时:约 30 分钟（含后台等待） · 归因:[AGENT]

## 2026-09-12 22:05 SGT · deepseek-v4-flash · 370e87ec37e741df
需求:承接 T3b（协作回执结构化）：dispatch 结果不再直传模型原文（含绝对路径/sha256/artifact id）；Pi 停止等系统状态不再冒充"结果"；提示词要求跨 Bot 回报只写一句结论。
处置:`bots.py` 新增 `peer_report(...)` 与 `_peer_artifacts(...)`：子任务结束时按 state/system_failure 生成回执类型与正文，completed 用 `outcome.summary`（无结构化结论时取原文前 200 字）并附 `artifacts:[{id,name,kind,taskId}]`；`interrupted`/`cancelled` 与 Pi 停止/报错/无结果/重试耗尽的 `failed` 走 `system_failure=True`，正文改为"<Bot 名> 的任务已中断，未产生结果"；Bot 自己 `fail` 仍按结果回传。`_finish` 给父任务的 `_message` 改为携带类型、正文与 artifact 索引。`bot_communications.list_communications` 结果行透传 `artifacts`，`system` 事件投影为 `kind:"system"` 且不进入结果类别。`bot_executor.py` 提示词新增"向其他 Bot 回报时只写一句结论，证据和文件通过 complete 提交成果，不在正文贴路径或哈希"。`docs/mms-web/BOTS.md` 追加 v2.4 一节。前端未改（`kind:"system"` 在现有 UI 按通用消息标签显示，已在文档说明）。
验证:focused 9 文件 136 passed（基线 129，+7：结构/回退/三种 Pi 系统状态/declared failure 边界/提示词）。真实实例 61779（temp state root，未动 60824 与真实 config 写入）：A 派 B 写文件，`POST /bots/A/communications` 返回 `{"kind":"result","content":"t3b-proof.md 已创建","artifacts":[{"id":"artifact_6ba692c25dbd43e1","name":"t3b-proof.md","kind":"file","taskId":"task_684792699e074006"}]}`，正文一句话且无路径/哈希，artifact 索引含文件；另用真实 runtime 取消一个 waiting 子任务，回执为 `{"kind":"system","content":"写手 B 的任务已中断，未产生结果","artifacts":[]}`，未落入结果类别。改完未提交（git diff --stat：6 文件 +195/-8）。
耗时:约 30 分钟 · 归因:[AGENT]

## 2026-09-13 00:40 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:核对 T1 收尾与 T3b，并处理 gemini 在 bot/T1-ui 上自行提交的 Pilot 设置页改动（用户确认是其本人直接交办）。
处置:Bot 范围改动拆到 bot/T1b-ui-followup（b2e2949b），T3b 提交 05fe7169，两者已合并进任务分支并推送（HEAD 66b93efe），60824 已用新构建重启。Pilot 改动拆到 pilot/settings-runtime-updates（25161653，作者 gemini-3.6），复核发现帮助"版本更新"请求的 /update/history 后端不存在、前端回退到手写假记录；补后端接口读取 RELEASE-v*.md（ef42a3d2），并去掉正文重复的升级须知（新提交）。PR #243 指向任务分支。此前我曾误把 gemini 工作树里删除 WhatsNew 与平台能力区块的三处改动 checkout 还原，已按其 diff 精确重做。
验证:任务分支 focused 136 passed、前端 8 文件全过；pilot 分支 tests/test_mms_web_updates.py 15 passed、前端 10 文件全过、build 通过；ego-browser 在 61500 看过运行环境标签浅色/深色、模型页、帮助版本更新（真实 27 个版本，v4.20.0 可展开）。
遗留:bot/T1-ui 分支保留 gemini 的 3 个本地提交未推送，其工作树仍有未提交改动，内容已分别落到 T1b 与 pilot 分支，可删。
耗时:约 90 分钟 · 归因:[AGENT]
## 2026-09-13 10:12 SGT · current-agent · 370e87ec37e741df

需求:核对 Claude 对 Bot 工作台的大幅推进是否真实、是否偏离已确认边界。

处置:核对当前 HEAD、origin/dev、PR #242、Coordinator/BrowserProvider/调度实现、实时 60824 页面和 Windows CI；补跑 Bot focused pytest、前端 build、Node tests。

验证:PR #242 已合并到 dev；当前工作区 HEAD 尚未包含合并后的 origin/dev 头，但包含 PR 内容。Bot focused pytest 136 passed，Node tests 63 passed，前端 build 通过；实时接口 version 2.2、4 个真实 Bot、Ego provider available=true。Windows acceptance 的 4 个 job 均因 mms web lifecycle 30 秒内未就绪失败；macOS/Linux 和真实 Windows 桌面行为仍未形成完整验收证据。

发现:实现已经从基础闭环推进到 T1 UI、T2 模型计划与依赖执行、T3 重试/通知/peer 回执；但 T2 每个任务默认会启动一次短暂 planner session，和“不要退回重型编排”的边界存在体感风险。WebAccessProvider 仍未实现，BrowserProvider 只有 Ego；文档中“无额外 planner session”和实际代码互相矛盾。当前 60824 进程使用真实 `/Users/xin/.config/mms-next`，不属于完全隔离的 task-local 配置验证。

耗时:约 20 分钟 · 归因:[AGENT]

## 2026-09-13 10:23 SGT · current-agent · 370e87ec37e741df
需求:接手 Gemini UI 已保留后的 Bot 收尾推进。
处置:保持前端视觉边界不变，准备收紧普通任务 planner 触发、接通 Windows file_lock、修正协作计划依赖校验。
成功标准:普通 direct-first 任务不创建 planner session；Windows 导入 Bot runtime 不依赖 fcntl；非法自依赖/前向依赖不能进入可执行计划；focused tests 通过。

## 2026-09-13 10:31 SGT · current-agent · 370e87ec37e741df
验证:Bot focused 142 passed；frontend Node tests 78 passed；Vite TypeScript/build passed；compileall、import smoke 与 git diff --check 均通过。
结果:Gemini 视觉提交已在当前 HEAD（7b52266e ancestor）；本轮仅改 backend/planner/锁与文档测试，未改 UI。当前 60824 status 仍为 Pi/Ego available，未重启真实服务。

## 2026-09-13 18:20 SGT · current-agent · 370e87ec37e741df
需求:为 4.21 Windows 修复做合并前预审，等待完成后再推进 5.0。
验证:origin/dev 与 windows-verified-integration 的 merge-tree 无冲突；Windows/Bot 相关 focused 181 passed、2 xfailed，workflow YAML 可解析；全仓库 2449 passed、62 failed、35 skipped、2 xfailed。
判断:62 个全量失败未命中本轮 candidate 文件与 focused tests，属于既有 config/registry/OpenCode/committee 基线漂移；Windows 真机 acceptance 尚未完成，因此 4.21 保持未 ready，5.0 暂停。

## 2026-09-13 18:28 +08:00 — 4.21 Windows work still in progress
- User clarified that the Windows repair is not yet finished or merged; 5.0 remains frozen.
- Read-only remote evidence: PR #244 is OPEN, `MERGEABLE`, `mergeStateStatus=UNSTABLE`; branch `codex/windows-verified-integration-20260913` is four commits ahead of `origin/dev`.
- Checks: Digger/Redline and three Windows matrix jobs passed; Windows 2025 + PowerShell 7 + Python 3.13 + Node 22 + real Pi job remains `IN_PROGRESS`.
- Task preflight remains uncommitted and isolated. `git ls-files -u` is empty; merge-tree reported no textual conflicts. No merge, push, restart, or release action performed.

## 2026-09-13 18:42 +08:00 — Bot transcript leaked into Pilot sidebar
- Reproduced by code path: `PiBotExecutor.start/plan` called the shared `SessionService.launch`, whose `session_view` hardcoded `owner=web`; `/bootstrap` and `/sessions` therefore returned Bot sessions as Pilot chats.
- Fixed in task workspace: owner-aware `SessionService.launch_bot`, persisted `owner=bot`/`botId`, server-side Pilot list filtering, and compatibility filtering for legacy Bot session ids from Bot records/tasks. Bot detail lookup remains addressable.
- Regression: 71 focused Python tests plus 4 subtests passed; Node frontend suite 78 passed; Vite build passed. Windows worktree and PR #244 were not touched.

## 2026-09-14 19:10 +08:00 — geometric Bot avatar system
- Replaced the rendered pixel-grid face with CSS/JS geometric avatars while keeping `PixelAvatar` and legacy ids as compatibility hooks.
- Added 18 shape profiles (circle, blob, cloud, square, drop, arch, triangle, star, oval, capsule, diamond, hex, ticket, wave, shield, gem, orbit, sun). Texture, expression and identity-stable face placement are generated from Bot identity; shape and color remain user-selectable.
- Face placement uses shape-safe anchors: complex clipped shapes stay centered; open shapes can vary upper/lower/left/right without clipping.
- Visual QA used Ego browser against the built app and preview editor; 43 focused Python tests + 4 subtests, 78 Node tests, and Vite build passed.

## 2026-09-14 12:33 +08
- Scope: Soften geometric avatar picker after visual feedback.
- Changed: reduced picker to 10 soft forms in one row; removed star-like presets from the new picker; added rounded triangle/drop/diamond/cloud/hex treatments; enlarged and separated face features; per-preset stable seed for expression/texture/face placement; legacy ids map to soft shapes for compatibility.
- Validation: `npm run build --workspace @mms/web` passed; `node --test apps/mms-web/tests/*.test.mjs` passed (78); `git diff --check` passed.
- Visual: Ego task space became unavailable while taking the post-change screenshot; existing Vite server remains running and build is current.

## 2026-09-14 16:30 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:用户要派发 T1c（新建即对话），要求 Claude 先把主 workspace 里另一会话遗留的未提交 Bot 改动落地。
处置:未动主 workspace。把 19 个 Bot 侧文件的 diff 抽到 wt-land（分支 bot/land-20260914）；8 个暂存的 Windows 文件与 origin/dev 逐字相同、tests/test_mms_runtime.py 的 posix 跳过标记 dev 已有，均未带入。Bot.tsx 的 eyeL/eyeR 坐标字段与既有 eyeR 半径字段重名导致 tsc 20 处报错，改名 eyeLeft/eyeRight 保留、未接入渲染。三片提交 a19d6400（后端：Bot 会话 owner=bot 隔离、direct-first 跳过 planner、file_lock）/ c2823291（几何头像）/ 4d870f40（文档），合并 origin/dev 065cf856 无冲突，f63d1cb9 去重复 import，acf82749 重建 mms_web_static。已 push 到 origin/codex/stride-370e87ec37e741df。
验证:compileall 通过；focused + Windows + updates 共 150 passed / 4 subtests；Node 78 passed；vite build 通过。fresh-user gate 后台运行中，结果另记。
未完成:主 workspace 本地分支仍停在 184a753d 且带脏树，需用户授权后同步；T1c 派发点为 acf82749。
补记 2026-09-14 16:45 SGT · claude-fable-5.1:fresh-user gate 在 wt-land（acf82749）PASS，671 passed / 149s。60824 已重启到 acf82749（PYTHONPATH 与 static-root 指向 wt-land，state-root 不变），/api/v1/sessions 中 bot-owned 0 条泄漏。ego-browser 截图 scratchpad/land-bots.png 头像渲染正常。

## 2026-09-14 16:55 SGT · gemini-3.6 · 370e87ec37e741df
包：T1c
分支 / worktree：codex/stride-370e87ec37e741df / /Users/xin/.local/share/stride/tasks/370e87ec37e741df/workspace
需求: T1c · 新建即对话：命名、头像、预设都在聊天里完成。
处置:
1. 新增纯逻辑模块 `apps/mms-web/src/bot-presets.ts`，提供 `suggestBotName`、`looksLikeStandingInstruction`、`parsePreset`、`buildPreset`；实现向导回答到 systemPrompt 拼装与解析、老 Bot 自定义 prompt 无损保留、补充约定去重/上限 12 条/单条 ≤ 200 字限制。新增测试 `apps/mms-web/tests/bot-presets.test.mjs`。
2. 改造 `BotStudio.tsx`：`createDraftBot` 在 preview 模式下直接创建内存草稿 Bot；`onUpdateBot` 支持 preview 响应及头像/颜色/唤醒合并 patch；`dispatch` 增加 preview mock task。
3. 改造 `Bot.tsx`：
   - 侧栏卡片对未命名 Bot 标题呈现 `--muted`「未命名」。
   - 向导增加第四步起名框，展示基于工作类型的建议名字，自动聚焦选中文本，回车一次性保存。
   - 对话 Header 实现名字 `<h1>` 和描述 `<p>` 原地编辑（Enter/失焦保存，Esc 放弃，高度稳定 64px 无布局跳动）；点击头像通过原生 `popover="auto"` 呼出图形和颜色点选即换。
   - 对话气泡 hover 动作「记为约定」写入 `systemPrompt` 补充约定段；任务终态触发「要把这句记为长期约定吗？ [记住] [不用]」自动提议；工作预设面板提供约定列表展示与单个删除。
4. 样式与门禁：在 `apps/mms-web/src/bot.css` 补齐原地编辑、头像 Popover、向导起名框、气泡 hover 动作、自动提议与约定列表样式，移动端 400px 安全适配。`bot*.css` Hex 数量严格等于 12。
5. 更新 `apps/mms-web/DESIGN.md` 追加「原地编辑与长期约定沉淀（T1c）」小节。
验证:
- 前端测试：`node --test apps/mms-web/tests/bot-presets.test.mjs` 5 passed；`node --test apps/mms-web/tests/*.test.mjs` 全量 83 passed。
- 前端构建：`npm run build --workspace @mms/web` 通过（TypeScript 0 error，Vite 打包成功）。
- 后端回归：`PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py tests/test_mms_bot_coordinator.py` 95 passed（基线 72 passed，未下降）。
- 实时验证：端口 4175（Vite dev）与 61600（独立服务实例），60824 未重启。
- 实机截图与指标：
  - 改名前后 Header 高度量取均为 64px。
  - 向导第四步起名框截图：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_onboarding_light.png
  - 头部编辑态（浅色）：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_header_editing_light.png
  - 自动提议行（浅色）：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_standing_suggestion_light.png
  - 自动提议行（深色）：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_standing_suggestion_dark.png
  - 头部编辑态（深色）：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_header_editing_dark.png
  - 移动端 400px 头像 Popover：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_avatar_popover_mobile_400px.png
  - 预设约定列表：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_preset_rules_editor.png
未完成 / 未验证:
- 无。全部功能与视觉验收项均通过。

## 2026-09-14 17:20 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:用户要求 Bot 改动只进 5.0，不掺进 4.x；并让 Claude 处理主 workspace 同步。
事实:4.21.0–4.21.12 全部在分支 codex/windows-encoding-4.21.1-followup，与 dev 的 merge-base 是 352dddc0，任何 4.21 tag 都不含 0d9a7ffa（Bot），bots.py 不存在于 4.21 树。dev（含 Bot）版本号仍是 4.20.0；若直接把 4.21 合回 dev，版本会自动继承 4.21.12 且含 Bot。
处置:在 .worktrees/forward-port-4.21（分支 claude/forward-port-4.21-into-5.0，起点 origin/dev 065cf856）合并 4.21 线：windows-acceptance.yml 三个 Windows 测试文件全保留；mms_web_static 用合并源码重建；mms_version.py 与两个 package.json 改 5.0.0；新增 docs/mms-web/RELEASE-v5.0.0.md（What's New 测试要求当前版本有说明）。合并提交 292df360，规则文档 8cde6ec7（RELEASE_CHANNELS.md 新增 4.x/5.0 边界）。真实进入 dev 的受保护文件只有 mms_launchers.py（+48/-5，Windows Pi 解析）。
验证:compileall 通过；focused 166 passed + 1 skipped（含 windows encoding/service/imports、pi resolution、updates）；Node 78 passed；vite build 通过，静态包无冲突标记。fresh-user gate 与 ci_pytest_regression --base origin/dev 后台运行中。
未完成:主 workspace 的 git checkout -- . 被权限拦截，待用户自行执行；PR 待 gate 结果后开，合并由用户执行。
补记 2026-09-14 17:45 SGT · claude-fable-5.1:fresh-user gate PASS 673；ci_pytest_regression base 68/2546 vs head 68/2570 无新增失败；PR #253 已开（claude/forward-port-4.21-into-5.0 → dev），待用户 merge。

## 2026-09-14 18:30 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:用户纠正：dev / main 保持 4.21.x 稳定安装线，Bot 的 5.0 进 canary 或 dev-pre。
处置:关闭 #253（方向错）。canary 是 6 月旧线（与 dev 双向各差 660+ 提交），不用；建 origin/dev-pre = 065cf856（撤销前的 dev，含 #242 与 #244）。新 worktree .worktrees/dev-4.21（分支 claude/dev-4.21-stable）：09a3b269 revert -m 1 0d9a7ffa（删 bots.py、bot_memory.py 冲突按删除解），1979c2c0 合入 4.21 线（仅 windows-acceptance.yml 冲突，三个测试文件全留；版本自动为 4.21.12；保留 4.21.12 已发布静态包，我的重建产物已丢弃），5492c8dd 把 #244 的 windows import 测试去掉 Bot 断言，eb1568aa RELEASE_CHANNELS 写入 dev=4.21.x / dev-pre=5.0 规则。已 push。任务分支加 0604126e（文档改指向 dev-pre），开 PR 任务分支 → dev-pre。
验证:dev-4.21 focused 80 passed + 1 skipped 后剩 1 个失败 test_whats_new（4.21 线头上同样失败，缺 RELEASE-v4.21.12.md，既有问题）；Node 55 passed；fresh-user gate 与 ci_pytest_regression --base origin/dev 后台运行中。
补记 2026-09-14 19:05 SGT · claude-fable-5.1:dev-4.21 分支加 12424786（RELEASE-v4.21.12.md）；gate 重跑 PASS 671；regression base 68/2546 vs head 68/2431 无新增失败。PR #255（claude/dev-4.21-stable → dev）、PR #254（任务分支 → dev-pre）待用户 merge。

## 2026-09-14 20:10 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:用户执行 workspace 同步命令后 pull 失败；随后告知 T1c 已完成。
事实:gemini-3.6 在主 workspace 里做 T1c（walls 16:55 条目），未开 worktree。用户 17:47 的 `git checkout -- .` 清掉了它对 Bot.tsx / BotStudio.tsx / bot.css / DESIGN.md 的改动，只剩未跟踪的 bot-presets.ts 与测试。Claude 给出该命令时依据的是 16:07 的状态，没有在 17:47 前复查，负有责任。
处置:从 Antigravity 转录 transcript_full.jsonl 抽出 08:30Z 后指向主 workspace 的 22 条编辑调用，在新 worktree wt-T1c（分支 bot/T1c-create-in-chat，起点 0604126e）逐条重放：21 条精确命中；落空的一条是 gemini 修 eyeL/eyeR 冲突的方案（半径改名 eyeRadius、删坐标字段），手工应用。提交 author gemini-3.6 / committer Claude，已 push。
验证:tsc 0 错误；vite build 通过；Node 83 passed（含 bot-presets 5 个）；bot*.css hex = 12。ego-browser 在 61600（wt-T1c 构建、空 state）实测：新建无 dialog、向导 3 题 + 起名框预填"项目助手"且全选、回车后 API 名字与四行预设正确、侧栏"未命名"→名字；头部改名 h=64 前后不变、Esc 取消、Enter 保存并同步侧栏；头像 popover 桌面与 400px 视口都在视口内，选形状后 avatarId 持久化。
未验证:记为约定 hover 动作与任务结束后的自动提议（需真实模型任务），以 gemini 截图 t1c_standing_suggestion_*.png / t1c_preset_rules_editor.png 为准。
缺陷:头像 popover 未锚定在头像下方，出现在页面左上（native popover无 anchor 定位）；popover 内 8 个形状而非文档说的 10 个。
补记 2026-09-14 20:30 SGT · claude-fable-5.1:用户批准后 941ec26c 合入 T1c，faad77e3 重建静态包，已 push；60824 重启到 faad77e3（assets index-BOh7XkLl.js），4 个 Bot 在；PR #254 已加评论。主 workspace 已同步到远端并设上游。

## 2026-09-14 18:35 SGT · gemini-3.6 · 370e87ec37e741df
需求: 修复 T1c 遗留的两个小修：头像 popover 锚定到头像正下方，popover 形状补齐到 10 个。
处置:
1. 头像 Popover 锚定到头像正下方：
   - 为 `.bot-chat-avatar-btn` 添加 CSS Anchor Positioning `anchor-name: --bot-chat-avatar-btn;`，并在 `.bot-avatar-popover` 声明 `position-anchor: --bot-chat-avatar-btn; top: anchor(bottom); left: anchor(left); margin-top: 8px;`。
   - 在点击头像按钮的事件中，使用 `getBoundingClientRect()` 动态注入内联坐标进行强力兜底与边界夹取，实现原生 CSS Anchor 与 JS 动态定位双重保障。
2. Popover 形状补齐到 10 个：
   - 在 `ORGANIC_SMILE_AVATARS` 与 `PIXEL_AVATARS` 补齐 `star`（萌星）与 `ghost`（幽灵）两个软萌微笑造型，保持 32x32 viewBox 及五官比例一致。
   - Popover 内部选项网格调整为 5 列 × 2 行工整排布（圆圆、萌猫、方糖、海豹、饭团、芽宝、朵云、水滴、萌星、幽灵），结构紧凑精致。
验证:
- Node 单元测试：83 passed。
- Vite 构建：TypeScript 0 error，打包成功。
- Hex 门禁：`bot*.css` Hex 数量严格维持 12。
- ego-browser 实机验证：
  - 浅色桌面端 Popover 锚定截图：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_avatar_popover_anchored_light.png（left: 304 与头像按钮 304 完全重合，10 个造型 5x2 工整排列）。
  - 深色桌面端 Popover 锚定截图：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_avatar_popover_anchored_dark.png。
  - 400px 移动端窄屏 Popover 截图：/Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1c_avatar_popover_anchored_mobile.png（紧贴头像正下方，完全在视口内无溢出）。
- PR 评论：已在 PR #254 留言同步修复内容与验证结果。

## 2026-09-15 SGT · claude-fable-5.1 · 370e87ec37e741df
需求:用户批准提交 gemini 的 popover 锚定 + 10 形状修复，并评估 Bot 完成度与发布顺序。
处置:aeb73a9a（author gemini-3.6）提交 Bot.tsx/bot.css；745834a8 重建 mms_web_static；已 push；60824 重启到 index-CU67yM60.js（首次重启漏了 PYTHONPATH，约 10 秒不可用，已补）；PR #254 已加评论。
验证:tsc 0、vite build 通过、Node 83、hex 12；ego-browser 桌面 popover left 304/top 66，400px left 16/top 301，10 形状；/api/v1/bots 4 个。
判断:完成度约 65%，可作 5.0 预览进 dev-pre，不进 stable。待办按序：#255/#254 合并（用户）→ dev-pre 版本 5.0.0 + RELEASE-v5.0.0.md + 合入 4.21 线 → 真实模型多 Bot 验收 → Bot 页屏蔽首次引导。Windows 适配按用户要求放最低。

## 2026-09-15 10:10 SGT · claude-fable-5.1（subagent 执行）· 370e87ec37e741df
需求:在 60824 上做真实模型验收：T1c 链路、任务后约定提议、多 Bot 协作是否自然发生。
处置:建临时 Bot bot_f90091d3517a411c"验收临时助手"（未删，owner 处理），派 3 个小任务；未重启 60824，未改代码。截图 6 张存 docs/mms-web/design/acceptance-20260915/。
验证:T1c 全链路实测通过（无 dialog、起名预填、记为约定写入 systemPrompt、任务后提议出现）。多 Bot 协作未发生：大总管对"分别给我 1）2）"直接 direct 完成，coordinatorPlan.source=direct-first、modelDecision=false，根因是 bots.py 1047-1062 的 direct-first 短路只看协作关键词。这正是 T2b 工单要解决的"形状检查"。
缺陷:预设编辑器重开时名字被换成建议名（会静默改名）、编辑器无关闭入口、固定尾句排在补充约定之后、名字框双层焦点框 → 开 T1e 给 gemini。Pilot 首页在 API 正常时仍显示"无法连接 MMS 本地服务"与"请选择可用模型"提示（截图 17-pilot-home.png），属 Pilot 侧，待复现。/api/v1/sessions 里有两条 2026-09-12 遗留的 Bot 内部会话（s-c9e97dc6b6cf"新 Bot"未归档可见、s-88bfc3af937d"计划 · 大总管"已归档），owner 记为 web，隔离过滤挡不住，属隔离上线前的旧数据。
未验证:带协作关键词时的 delegate 链路、plan-approve、子任务失败恢复、重启持久化、窄窗与深色主题。

## 2026-09-15 10:55 SGT · gemini-3.6 · 370e87ec37e741df
包: T1d · Bot 页不弹 Pilot 首次引导
分支 / worktree: bot/T1d-guide-on-bots / wt-T1d
需求: 解决全新 state 下打开 #page=bots 时，Pilot 首次引导（“第一次用 AI？1/7”）叠在 Bot 工作台上的问题：
  1. page === "bots" 时不自动开始引导，不标记已看过；回到 Pilot 会话页时引导照常首次弹出。
  2. 引导进行中点击侧栏 "Bot 工作台" 入口，引导立即关闭，无残留高亮与报错。
  3. 在 Bot 页触发帮助并点击“开始介绍”/“带我一步步操作”，先切回 Pilot 新会话页再从 welcome 步骤开始。
  4. 保持其它页面引导行为、7步顺序、服务端 tourSeen 持久化完全不变。
处置:
  1. `apps/mms-web/src/App.tsx`:
     - 抽离并导出纯函数 `isGuideReady({ loading, connected, modelReady, setupOpen, settingsOpen, page })`，严格限定 `page !== "bots"`。
     - 在 `HelpGuide` 组件处传入 `ready={isGuideReady(...)}`，确保 Bot 页面不触发自动引导。
     - 在 `tour` 挂载条件中加入 `page !== "bots"` 守卫，彻底隔绝 Bot 页面下 GuidedTour 渲染。
     - 在 `startIntroduction()`、`beginGuideStep()` 与 `guideNavigate()` 中，统一处理 `if (page === "bots")` 时自动跳转回 Pilot 新会话页（`navigate("new", ...)`），确保引导始终在 Pilot 页面展示。
  2. `apps/mms-web/src/HelpGuide.tsx`:
     - 使用 `useRef` 固化 `startTourRef`，`useEffect` 依赖收敛为 `[ready]`，避免闭包与组件重新渲染导致的无效取消或重复触发。
  3. 新增 `apps/mms-web/tests/guided-tour-bots.test.mjs`:
     - 覆盖 `isGuideReady` 页面判断、路由导航关闭引导、Bot 页面启动引导回退 Pilot，以及 `HelpGuide` 自动启动守卫。
改动文件:
```text
 apps/mms-web/src/App.tsx       | 40 +++++++++++++++++++++++++++++++++++++---
 apps/mms-web/src/HelpGuide.tsx |  6 ++++--
 2 files changed, 41 insertions(+), 5 deletions(-)
```
测试:
  - TypeScript 类型检查: `npx tsc --noEmit -p apps/mms-web`（0 错误）。
  - 前端全量单元测试: `node --test apps/mms-web/tests/*.test.mjs`（87 passed, 0 failed, 含新增的 4 个断言）。
  - 前端构建打包: `npm run build --workspace @mms/web`（Vite build 成功通过）。
  - 后端聚焦测试: `PYTHONPATH=. python3 -m pytest -q tests/test_mms_web_bots.py tests/test_mms_bot_runtime.py tests/test_mms_bot_transport.py tests/test_mms_bot_client.py tests/test_mms_bot_computer.py tests/test_bot_memory.py tests/test_mms_bot_coordinator.py`（95 passed，高于基线 72）。
实时验证:
  - 独立端口: 61700（空 state-root `/tmp/bot-verify-T1d`，不碰 60824）。
  - 验证页面: `#page=bots` 与 Pilot 新会话页。
  - 验收截图路径:
    1. 新 state 打开 `#page=bots`（无引导）: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1d_1_bots_page_no_tour.png`
    2. 同一 state 点击返回 Pilot（引导 1/7 正常弹出）: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1d_2_back_to_pilot_tour_pop.png`
    3. 引导进行到 2/7 时点击侧栏 "Bot 工作台" 入口（引导立即关闭，Bot 界面正常无残留）: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1d_3_enter_bots_closes_tour.png`
    4. Bot 页面点 "?" 帮助抽屉中的“带我一步步操作”（切回 Pilot 新会话页并展示 welcome）: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1d_4_bots_help_to_pilot_welcome.png`
未完成 / 未验证: 无。全部 4 项验收项均通过实机自动化与视觉验证，代码严格保持未提交（uncommitted）状态。

## 2026-09-15 11:00 SGT · claude-fable-5.1（subagent 执行）· 370e87ec37e741df
需求:准备 5.0.0 预览分支，基线 v4.21.14，只到准备阶段。
处置:worktree wt-v5 分支 claude/dev-pre-5.0（起点 90287459）：合入 v4.21.12 再 v4.21.14，cherry-pick RELEASE_CHANNELS 规则与 4.21.12/4.21.14 说明，版本 5.0.0，新增 RELEASE-v5.0.0.md，重建静态包。draft PR #261 → dev-pre，依赖 #254 先合。受保护文件只有 mms_launchers.py 经 merge 带入 +48/-5。
验证:compileall 通过；focused+windows+updates 147 passed/1 skipped；Node 83；tsc 0；fresh-user gate PASS 676；ci_pytest_regression base 63/2551 vs head 63/2578 无新增失败。
未验证:Windows acceptance 未在本分支跑；Windows 上 Bot 未验收（已写进发布说明的验证边界）。

## 2026-09-15 11:05 SGT · gemini-3.6 · 370e87ec37e741df
包: T1e · 预设编辑器四处修正
分支 / worktree: bot/T1e-preset-editor / wt-T1e
需求: 解决 2026-09-15 真实模型验收中发现的 4 处缺陷：
  1. 重新打开"调整工作预设"时名字被换成建议名（编辑已有名字的 Bot 时输入框必须是当前名字，答案变化不覆盖已有名字，保存名字未变不发 name 字段）。
  2. 预设编辑器没有关闭入口（头部"预设"按钮支持 toggle 并带 aria-pressed，编辑器右上加"取消"文字按钮，按 Esc 键关闭，关闭丢弃未保存修改）。
  3. 固定尾句排在"补充约定："之后（buildPreset 把 DEFAULT_FOOTER 放在向导答案之后、补充约定之前；parsePreset 兼容新旧两种顺序）。
  4. 名字输入框双层焦点框（去掉 focus-visible 的外层 outline，保持单一 border 焦点，与 bot-chat-title-input 一致，hex 保持 12）。
处置:
  1. `apps/mms-web/src/Bot.tsx`:
     - `BotOnboarding` 中新增 `hasCustomName` 判断（非空且非未命名/非默认）；已有名字时初始化为当前名，且选项变化不覆盖原有名字；完成时若名字未变则不发送 `name` 字段。
     - 头部"预设"按钮升级为 toggle（`aria-pressed={onboardingEditing}`，点击可关闭，打开时重新解析 prompt 丢弃未保存草稿）。
     - 编辑器问候栏右上角增加"取消"文字按钮，点击关闭并丢弃修改；增加全局 `keydown` 监听 `Escape` 键关闭编辑器。
  2. `apps/mms-web/src/bot-presets.ts`:
     - `buildPreset` 调整结构：`DEFAULT_FOOTER` 紧接在向导答案之后加入，然后再加入 `RULES_HEADER` 和约定列表；`parsePreset` 对新旧顺序均正常跳过已知 footer。
  3. `apps/mms-web/src/bot.css`:
     - 增加 `.bot-onboarding-cancel` 样式与问候栏 row 布局。
     - `.bot-onboarding-name-input` 增加 `:focus-visible, :focus` 时 `border-color: var(--accent); outline: none;`，消除外层双层 outline。
  4. `apps/mms-web/tests/bot-presets.test.mjs`:
     - 增加测试用例验证新旧尾句顺序兼容解析与构建顺序。
改动文件:
```text
 apps/mms-web/src/Bot.tsx                | 58 +++++++++++++++++++++++++++------
 apps/mms-web/src/bot-presets.ts         |  5 +--
 apps/mms-web/src/bot.css                | 28 ++++++++++++++++
 apps/mms-web/tests/bot-presets.test.mjs | 40 +++++++++++++++++++++++
 4 files changed, 117 insertions(+), 14 deletions(-)
```
测试:
  - TypeScript 类型检查: `npx tsc --noEmit -p apps/mms-web`（0 错误）。
  - 前端全量单元测试: `node --test apps/mms-web/tests/*.test.mjs`（84 passed, 0 failed）。
  - 前端构建打包: `npm run build --workspace @mms/web`（通过）。
  - Hex 门禁检查: `grep -o '#[0-9a-fA-F]\{3,8\}' apps/mms-web/src/bot*.css | sort -u | wc -l` 严格为 12。
实时验证:
  - 独立端口: 61701（独立 state-root `/tmp/bot-verify-T1e`，不碰 60824）。
  - 验收项 1（保留已有名字与尾句顺序）: 打开"验收临时助手"，输入框初值为"验收临时助手"，修改选项后输入框仍为"验收临时助手"；保存后 `GET /api/v1/bots` 确认 name 未被修改，且 systemPrompt 中尾句排在"补充约定："之前。截图：`file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1e_1_existing_name_preserved.png`。
  - 验收项 2（三种关闭方式）:
    - 取消按钮关闭: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1e_2a_cancel_button_closes.png`
    - 头部 toggle 关闭: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1e_2b_header_toggle_closes.png`
    - Esc 键关闭: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1e_2c_esc_closes.png`
  - 验收项 3（单一焦点边框，无双层 outline）: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t1e_3_single_focus_outline.png`。
未完成 / 未验证: 无。全部 4 处修正均已验证通过，代码保持未提交状态。

## 2026-09-15 11:55 SGT · deepseek-v4-flash · 370e87ec37e741df
需求:承接 T3d 后端（等待契约 + 记忆降噪）：waiting/user 必须带真实问题，旧脏数据不再点亮侧栏；无产出任务不写记忆。
处置:`bots.py` 新增纯函数 `looks_like_question` / `is_trivial_result` / `parse_wait_text`，以及新方法 `_pending_question`、`_migrate_wait_contracts`、`_last_wait_text`、`_record_wait_request`、`_enter_user_wait`、`wait_action`、`_should_remember_task`。等待入口改为只带问题才进 `waiting/user`（字段 `waitQuestion`/`waitOptions`/`waitSince`），显式 `question`/`options` 优先，其次取最后一条 progress/assistant 文本并要求像问题（`?`/`？` 或 疑问/请求形式：哪/什么/是否/要不要/请确认/需要你…），`选项：A | B` 单独一行解析成快捷回复；两者都没有时按 completed 收尾并记 `waitDeclined`。`list_bots` 给每个 Bot 派生 `pendingQuestion`（只认带问题的 waiting/user，取 waitSince 最新）。`tick` 对超过 7 天的 waiting/user 自动完成并写“等待超时，已结束”；`_load` 启动迁移回填 `waitSince` 并从旧文本套问题（套不出置 `waitQuestion=""`）。`server.py` 增加 `POST /api/v1/tasks/:id/wait`（answer 复用消息路径恢复任务 / dismiss 按 completed 收尾并记 `waitDismissed`）。记忆 digest 只在有结构化结论（`# 结论`）或 `changes`、有 artifacts、或结果 ≥120 字且非“收到/明白/已发送/沟通完毕/无待办/先候着”时写入，纯 peer 消息任务（有 deliveryMessageIds、无 artifacts、无结构化结论）一律不写。`bot_executor.py` 提示词把 wait 从“原因”改成“要问用户的问题”，并说明可用“选项：A | B”给快捷回复；`docs/mms-web/BOTS.md` 追加 v2.5 一节。
验证:基线对比：focused 9 文件改前 139 passed（git stash 实测），改后 173 passed（+34，只增不减）。新增用例覆盖：`looks_like_question` 正 6 反 6、`is_trivial_result` 正 4 反 4、`parse_wait_text`、无问题不进等待（completed + waitDeclined）、显式问题带 options 进等待并出现在 `pendingQuestion`、文本回退带 `选项：`、answer 恢复 / dismiss 收尾、非等待任务拒绝、7 天过期、重启迁移（脏任务置空 + 真问题回填）、记忆四种条件各一条 + 纯 peer 不写、`POST /tasks/:id/wait` 路由。`python3 -m compileall -q mms_web` 通过；`python3 scripts/regression_fresh_user_gate.py --quick` PASS（dry-run + 139 passed）。
实时验证:复制 60824 的 state 到 `/tmp/bot-verify-T3d`，独立实例 61703（未碰 60824）。启动后 `GET /api/v1/bots`：大总管 `"pendingQuestion": null`（旧任务 `waitQuestion: ""`，`waitSince` 已回填 `2026-09-15T02:58:31.895+00:00`）。真实小任务让大总管提问后：`{"taskId":"task_e0dd6e5bdf4e491c","question":"已向你提问：先做哪一项？\n\n- A 先梳理需求要点\n- B 先检查现有文件\n\n选一个回复我就行，我按你的选择用一句话收尾。","options":[],"since":"2026-09-15T03:46:44.580+00:00"}`；`POST /tasks/task_e0dd6e5bdf4e491c/wait {"action":"answer","text":"先做 A"}` 返回 `status: queued`、`waitAnsweredAt: 2026-09-15T03:47:47.842+00:00`，`pendingQuestion` 回到 null，任务随后真实恢复并 completed（"你选了 A（先梳理需求要点）…"）；对旧脏任务 `POST …/wait {"action":"dismiss"}` 返回 `status: completed`、`waitDismissed: true`、`result: 等待已结束。`。记忆噪音：大总管 memory 的 task 摘要运行前后都是 6 条（新增的短回复与 dismiss 都未写入）。
接口 JSON（关键片段）:`GET /api/v1/bots` → `{"name":"大总管","pendingQuestion":null}`（迁移后）；等待中 → `{"taskId":"task_e0dd6e5bdf4e491c","question":"已向你提问：先做哪一项？…","options":[],"since":"2026-09-15T03:46:44.580+00:00"}`；answer 后 → `{"status":"queued","waitAnsweredAt":"2026-09-15T03:47:47.842+00:00"}`；dismiss 旧脏任务 → `{"status":"completed","waitDismissed":true,"result":"等待已结束。"}`。
未完成/未验证:前端提问卡与头部/侧栏接线由 gemini 的 T3d-ui 承接，本包未动前端文件（`pendingQuestion` 字段已定）。`waitOptions` 目前只有显式参数或“选项：A | B”行会产生；真实模型这次用了 Markdown 列表，所以 options 为空（单测覆盖了两种产生路径）。`bot_client.py` 不在允许改动清单内，因此 `wait` CLI 仍只发送文本 reason（显式 `question`/`options` 由 worker payload 接收，等前端或后续 CLI 透传）。未提交、未 push、未 merge。
耗时:约 45 分钟 · 归因:[AGENT]

## 2026-09-15 12:10 SGT · deepseek-v4-flash · 370e87ec37e741df
需求:自查 T3d 改动时发现 `bots.py` 出现了两处 `list_bots` 定义（编辑插入时误留旧定义），修正后重新验证。
处置:删除重复的 `list_bots`，只保留原有位置的定义并加上 `pendingQuestion` 派生字段；其余等待契约逻辑不变。
验证:重新复制 60824 的 state 到 `/tmp/bot-verify-T3d`（清掉大总管的旧 session）并起 61703：启动后 `大总管 pendingQuestion=null`；真实小任务让大总管提问后 `pendingQuestion={"taskId":"task_c94e51f25e494bcc","question":"我这边准备好了，先问一句：**要不要继续？**…","options":[],"since":"2026-09-15T03:51:26.648+00:00"}`；`POST /tasks/task_c94e51f25e494bcc/wait {"action":"answer","text":"继续"}` 返回 `status: queued`、`waitAnsweredAt: 2026-09-15T03:51:39.884+00:00`，任务随后 completed 且 `pendingQuestion` 回到 null。focused 9 文件 173 passed；`python3 -m compileall -q mms_web` 通过。
耗时:约 15 分钟 · 归因:[AGENT]

## 2026-09-15 12:10 SGT · gemini-3.6 · 370e87ec37e741df
需求: 执行 T3c 工作包（Bot 间往来在主聊天折叠成一张卡，协作面板按任务分段）：
  1. 主聊天：一个任务里与同一个对方 Bot 的往来折叠成 `<details className="bot-peer-thread">` 卡片，summary 显示"与 <对方名> 的往来 · N 条" + 右侧小时间 + "在协作面板查看"文字按钮；展开后在原位按时间列出消息（带发送方小头像与名字，无"已处理"标签）；默认收起；事件流中相关 peer 往来事件不再单独渲染，收归卡内；Bot 自己的转述句放入卡片尾部标为"Bot 的说明"；Bot 给用户的最后一句结论正常显示，不折叠。
  2. 协作面板：顶部加对方 Bot 切换条（头像 + 名字 + 最近时间，高亮当前项，1 个对方也展示）；面板副标题动态跟随当前对方（如"调度 与 大总管"）；消息按任务分段（每个 taskId 一段，段头为任务第一句用户请求截取 60 字 + 日期；无 taskId 的归入"未关联任务"；最新任务在最上）；区分 kind（result 标"结果"且超 6 行可展开折叠，message 保持样式，dispatch 标"任务"）；不同天之间插入细分隔线显示日期。
  3. 响应式适配：400px 窄屏折叠卡和协作面板无溢出。
处置:
  1. `apps/mms-web/src/Bot.tsx`:
     - 引入 `getChainedParentTaskId` 追溯通信链路，将 peer 唤醒触发的子任务自动归入其发起根任务（如把 `task_a576d8caeda84ad3` 归集至 `task_2e9398e2b33843c0`），消除了主聊天中大总管头像冒充用户输入的割裂感。
     - 渲染 `<BotPeerThread>` 组件，默认收起，summary 显示 `与 <对方名> 的往来 · N 条` + 时间 + `在协作面板查看` 按钮；展开后展示通信流及底部的 `Bot 的说明` 块；过滤 peer 散落事件，保留用户输入和最终回复。
  2. `apps/mms-web/src/BotCommunications.tsx`:
     - 导出纯函数 `formatDateOnly`、`groupCommunicationsByDate`、`groupCommunicationsByTask`（按任务分段、截取 60 字、最新在最前、跨天加日期分隔线）。
     - 顶部增加对方 Bot 切换条（头像、名称、时间，支持单一对方展示），副标题动态跟随对方名称。
     - kind 细分：`result` 标记"结果"且超过 6 行内联折叠展开，`dispatch` 标记"任务"，`message` 标记"消息"。
  3. `apps/mms-web/src/bot.css`:
     - 添加 `.bot-peer-thread`、切换条、任务分段头、日期分隔线、kind 标签、6 行折叠及 400px 移动端窄屏样式。
     - 修复 Chromium 下 details 设置 `overflow: hidden` 导致 closed 状态高度为 2px 的原生隐蔽渲染 bug，将圆角和裁切优化至 summary。
     - 为 `.bot-communications-peers` 补齐 `flex-shrink: 0 !important;`，避免 flex 容器纵向挤压导致切换条被压扁。
  4. `apps/mms-web/tests/bot-peer-folding.test.mjs`:
     - 新增纯函数单元测试，覆盖按任务分段截断排序与按天分隔。
  5. `docs/mms-web/DESIGN.md`:
     - 追加第 6 节规范说明。
改动文件:
```text
 apps/mms-web/DESIGN.md                 |  11 +
 apps/mms-web/src/Bot.tsx               | 261 +++++++++++++++++--
 apps/mms-web/src/BotCommunications.tsx | 463 +++++++++++++++++++++++++++------
 apps/mms-web/src/bot.css               | 402 ++++++++++++++++++++++++++++
 4 files changed, 1032 insertions(+), 105 deletions(-)
 新增: apps/mms-web/tests/bot-peer-folding.test.mjs, docs/mms-web/design/t3c/ (4 张验收截图)
```
测试:
  - TypeScript 类型检查: `npx tsc --noEmit -p apps/mms-web`（0 错误）。
  - 前端全量单元测试: `node --test apps/mms-web/tests/*.test.mjs`（85 passed, 0 failed，基线 83 + 新增 2 项断言）。
  - 前端构建打包: `npm run build --workspace @mms/web`（通过）。
  - Hex 门禁检查: `grep -o '#[0-9a-fA-F]\{3,8\}' apps/mms-web/src/bot*.css | sort -u | wc -l` 严格为 12。
实时验证:
  - 独立端口: 61702（独立只读 state 副本 `/tmp/bot-verify-T3c`，未碰 60824）。
  - 验收 1（调度主聊天收起状态）: 调度的聊天里只剩用户消息、一张收起的"与 大总管 的往来 · 3 条"卡、调度给用户的最后一句结论。截图: `docs/mms-web/design/t3c/t3c_1_chat_folded.png`（脑部存档: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t3c_1_chat_folded.png`）。
  - 验收 2（展开折叠卡）: 展开后原位列出 3 条消息（带发送方小头像与名字，无"已处理"标签），末尾展示"Bot 的说明"（含过滤出的"已向大总管发送..."）。截图: `docs/mms-web/design/t3c/t3c_2_chat_expanded.png`（脑部存档: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t3c_2_chat_expanded.png`）。
  - 验收 3（协作面板）: 顶部对方切换条高亮大总管，副标题显示"调度 与 大总管"，9月15日问候段与9月11日结果段按任务清晰分段，跨天带日期分隔线，kind 正确区分，结果超 6 行带"展开全文"。截图: `docs/mms-web/design/t3c/t3c_3_communications_sections.png`（脑部存档: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t3c_3_communications_sections.png`）。
  - 验收 4（400px 窄屏适配）: 视口宽度 400px 下，折叠卡和协作面板自适应良好，无横向滚动条，无布局溢出。截图: `docs/mms-web/design/t3c/t3c_4_narrow_400px.png`（脑部存档: `file:///Users/xin/.gemini/antigravity-cli/brain/f414fd9d-ced5-4da4-b1a2-7608e91ec350/t3c_4_narrow_400px.png`）。
未完成 / 未验证: 无。T3c 规定的全部功能及 4 项验收指标均 100% 验证通过。代码保持未提交（uncommitted）状态。

## 2026-09-15 12:15 SGT · kimi-k3 · 370e87ec37e741df
需求:T2b 工单 —— Coordinator 成为真正的自动计划层：形状检查触发、计划状态机、结果图、重启幂等（docs/mms-web/bot-work/T2b-planner-state-machine.md）。
处置:
1. worktree wt-T2b、分支 bot/T2b-planner，起点 37da66c1（任务分支 HEAD）。
2. bot_coordinator.py：新增 looks_multi_goal（编号列表≥2/分别同时各自一边一边/@或≥2 Bot 名）、表驱动 PLAN_TRANSITIONS/STEP_TRANSITIONS + transition_plan/transition_step/set_plan_status（history 封顶 50）、legacy dispatched/blocked 归一、onFailure 默认 retry、build_planner_prompt 带 roster 最近 3 次成功任务标题。
3. bots.py：_launch/plan_task 触发顺序（off→direct；无信号→direct；信号→planner 20s→关键词→direct）；_advance_plan 拆出 _sync_plan_steps（(parentTaskId, planStepId) 对账、terminal 子任务回写 step.result、interrupted 不判负等显式唤醒）、onFailure skip/abort 策略与级联跳过、_resume_plan_failure 中止恢复一次、_queue_parent_merge 按步骤编号生成 resumeText + childResults + resumedAt、_finish 调 _settle_plan_on_finish（direct 计划同样 auto→running→merging→done/failed/cancelled）、_observe 在 plan 终态后不再退回 waiting/children、plan_action 扩 cancel/retry-step/skip-step（retry 重开 failed→running 并 attempts 后缀重建子任务）。
4. 前端：types.ts 加 ready/running/skipped/history/result/onFailure/childResults；BotPlan.tsx 最小接线（状态标签、step.result.summary、failed 步重试/跳过按钮、running 计划取消按钮，沿用现有 class）。
5. server.py / bot_executor.py 实际无需改动；未碰 Bot.tsx/css/bot_notify/bot_memory/sessions。
验证:
- compileall 通过；focused pytest 113 passed（基线 95 只增不减；工单"150"为文档期预期，实测基线 95）；Node 83 pass；tsc 0 error；vite build 成功。
- 真实链路（61800 独立实例，/tmp/bot-verify-T2b，未碰 60824，三 Bot deepseek-v4-flash）：
  · 多目标"分别给我：1）rebase；2）merge" → looks_multi_goal 触发 model planner，乙/丙各领一步，A 一条合并结论，history auto→running→merging→done，steps[].result.summary 非空。
  · 单目标"用三句话解释 git rebase" → direct-first 无子任务。
  · 失败路径：plan-approve 下把丙 preset 改不存在模型 → s2 failed、plan running→failed（by step:s2）、A 恢复说明"分工里 s2（验收助手丙）失败"；修好 preset 后 retry-step → failed→running→merging→done。UI 流程复验一轮（cherry-pick/stash）。
- 截图与脱敏 JSON：docs/mms-web/design/t2b/（ui-plan-proposed-approve / ui-plan-failed-retry-skip / ui-plan-done-with-step-results / ui-plan-block-closeup + accept2/3/4 三份 JSON）。
- 回归报告：.ai/regression-reports/2026-09-15-t2b-planner-state-machine.md。
未完成/未验证:
- "取消计划"按钮（running 态）真实链路未截到（窗口只有几秒）；cancel 路径有单测 test_plan_cancel_stops_running_children_and_resumes_parent。
- 验收中误建一个 "x" 垃圾任务，已当场 cancel（/tmp 验证实例数据，不影响代码）。
- wt-T2b/node_modules 是指向主 workspace 的 symlink（构建测试用），不应提交。
- 改动未提交、未 push、未 merge，等用户批准。
T2c 跟进（UI 整理建议）:
1. 步骤行里 Bot 名字竖排逐字换行（验收助手乙/丙占 3 行），行高被撑大，需要给 .bot-plan-step-goal strong  nowrap 或调整列宽。
2. step.goal 与 result.summary 连排显示偏挤，长文本截断后信息密度低，可考虑摘要折叠。
3. failed 步骤的"重试/跳过"按钮挤在 goal 文本流内，位置随文本长度漂移，建议固定到状态列旁。
4. 计划头新增的状态标签（待确认/执行中/汇总中/已完成/已中止/已取消）只用了通用 bot-plan-tag 样式，视觉层级未区分。
耗时:约 2.5 小时 · 归因:[AGENT]

## 2026-09-15 14:21 SGT · claude-fable-5.1（subagent 执行）· 370e87ec37e741df
需求:把五个已验收的 Bot 工作包（T1d / T1e / T3c / T3d / T2b）合入任务分支 codex/stride-370e87ec37e741df，做几处小修正，重建静态包并重启 60824。owner 已批准本任务全部 commit / merge / push / 重启。
处置:先提交主 workspace 里 deepseek 的两条 walls 追加（ce5e1a91）。按 T1d → T1e → T3c → T3d → T2b 逐个在各自 worktree 提交（原模型署名，committer Claude），再 `git merge --no-ff` 回任务分支。真冲突只有预演说的那一处：`mms_web/bots.py` `_observe` 终态分支，采用 T2b 的 `plan_settled` 结构，把其中内联的 user-wait 段换成 `self._enter_user_wait(task)`。`tests/test_mms_bot_runtime.py` 7 段、`tests/test_mms_web_bots.py` 2 段是文件尾追加碰撞，两边整段各留，共享的 `finally: runtime.close()` / `rt.close()` 各补一份。walls.md 每步冲突按时间顺序合并。修正五条，每条一个 commit 带测试：T1d `beginGuideStep` 去掉 `step === "welcome"`；T1e 预设编辑器的 window Esc 在 `.bot-chat-title-input` 获焦时不处理；T3c `isPeerRelatedEvent` 删掉对方名兜底、`isPeerExplanation` 补 `已与…完成双向消息`、`getChainedParentTaskId` 加 visited 防环、删 `BotCommunications.tsx` 未用图标导入与 `bot.css` 无引用的 `.bot-communications-marker`；T3d `_record_wait_request` 每轮重置 waitQuestion/waitOptions、`_last_wait_text` 优先本轮、`wait_action` answer 与 `_finish` 清空等待字段、`looks_like_question` 按行和句号扫全文、`bot_client.py` 的 `wait` 支持 `--question`/`--option`；T2b 依赖判定把 `skipped` 也算满足、direct 计划在 `_settle_plan_on_finish` 里把 `steps[0]` 置 done/failed、前端 `BotTask.childResults` 与 plan step 的 `policyApplied`/`attempts`。最后重建 `mms_web_static` 并重启 60824。
验证:`python3 -m compileall -q mms_web` 通过（每次 merge 后各跑一次）。focused pytest 11 文件 193 passed（合完五个包时 182，修正后 193）。`node --test apps/mms-web/tests/*.test.mjs` 93 pass / 0 fail。`npx tsc --noEmit -p apps/mms-web` 0 错误。`grep -o '#[0-9a-fA-F]\{3,8\}' apps/mms-web/src/bot*.css | sort -u | wc -l` = 12。`python3 scripts/regression_fresh_user_gate.py` PASS，671 passed in 139.01s。`python3 scripts/ci_pytest_regression.py --base 61bbdc6c`：base 63 failing of 2551，head 63 failing of 2614，"No test that passes on the base commit fails here"。`grep -rn '<<<<<<<' mms_web_static` 为空。每条修正都单独用 git stash 反证过：去掉修复后对应新增用例确实失败，不是空断言。
偏差:`types.ts` 的 plan step 字段按工单是 `policyApplied?: string`，但 `mms_web/bots.py` 1124 / 1404 两处写的是 `True`，所以按实际协议声明成 `boolean`；如果后续要改成策略名字符串，需要先改后端。
未完成/未验证:前端交互只有类型检查与源码级断言，没有真实浏览器回归；Bot 折叠卡、预设编辑器 Esc、计划块这几处的视觉行为沿用各包自己的验收截图，本次未重跑 ego-browser。Windows 未验证。`retry-step` 前置为 skipped 的状态在单轮 API 里走不到，用例是直接构造持久化计划形状来覆盖这条门禁的。60824 上只做了新包在跑 + Bot 列表带 pendingQuestion 的冒烟，没有跑真实模型多 Bot 协作验收。
耗时:约 90 分钟 · 归因:[AGENT]

## 2026-09-15 14:56 SGT · claude-fable-5.1（subagent 执行）· 370e87ec37e741df
需求:把 `origin/dev`（9b69c38a，4.21.14 + installer preview 修复，仍含 Bot 文件）同步进 5.0 集成分支 `dev-pre`，再把 `dev-pre` 合入任务分支 `codex/stride-370e87ec37e741df`，重建静态包并重启 60824。owner 已批准本任务的 commit / push（含 push dev-pre）与重启，不得 merge 任何 PR。
处置:`origin/dev-pre`（065cf856）经确认是 `origin/dev` 的严格祖先，所以第一步 `git merge --no-ff origin/dev` 在临时 worktree `.worktrees/dev-pre-sync` 里零冲突完成，得到 a9f8f615 并推到 origin。第二步在主 workspace `git merge --no-ff origin/dev-pre`，真冲突只有 `mms_web_static/build.json` 与 `mms_web_static/index.html`（构建产物，先取 dev-pre 一边，第三步整体重建）。预期中的 `.github/workflows/windows-acceptance.yml` 没有报冲突，但 git 的文本自动合并把任务分支侧的 `tests/test_mms_web_windows_imports.py` 从两处清单里悄悄删掉了，手工补回，恢复成两边并集（14 个测试文件，matrix 路径清单与 pytest 命令各一份）。`tests/test_mms_web_windows_imports.py` 文件本身自动保留了任务分支含 Bot 断言的版本（与 50d06b01 逐字节一致）。merge commit 00f530f8。第三步 `npm install` 后 `python3 scripts/build_mms_web_release.py --skip-install` 重建，产物 index-X3DvnDEW.js / index-DlF89tjb.css，commit 9a0fdae6。
验证:`python3 -m compileall -q mms_web` 两次 merge 后各通过一次。dev-pre 侧 focused pytest（test_mms_web_bots + test_mms_bot_runtime + windows/updates 共 8 个文件）94 passed / 1 skipped，`mms_web/bots.py` 存在，`mms_version.py` VERSION = "4.21.14"。任务分支侧 focused pytest 9 组共 15 个文件 208 passed / 1 skipped（门槛 193）。`node --test apps/mms-web/tests/*.test.mjs` 93 pass / 0 fail。`npx tsc --noEmit -p apps/mms-web` 退出码 0，无输出。`grep -rn '<<<<<<<' mms_web_static` 为空。`python3 scripts/regression_fresh_user_gate.py` PASS，677 passed in 147.56s。`python3 scripts/ci_pytest_regression.py --base 50d06b01`：base 63 failing of 2614，head 63 failing of 2642，"No test that passes on the base commit fails here"。
偏差:fresh-user gate 第一次跑报 `tests/test_install_script_paths.py::test_installer_does_not_reuse_another_homes_web_instance` 失败（拿到端口 18933，期望 18931）。定位为端口争用而非合并回归:该文件与 `install.sh` 与 `origin/dev-pre` 逐字节一致；同一用例在 dev-pre worktree 通过；单独重跑在同一 worktree 时而通过时而失败；当时本机有两个并发全量 pytest（本次后台 ci_pytest_regression 与另一 subagent 在 .worktrees/dev-no-bot 的同名脚本）同时用 port_base=18930。等本次后台跑完后重跑 gate 即全绿 677 passed。
未完成/未验证:未 merge 任何 PR（按约束）。draft #261 的冲突状态只做记录，未修。Windows 未验证。60824 只做重启后的冒烟（静态包 hash、/api/v1/bots、版本号），没有跑真实模型多 Bot 协作验收。前端无真实浏览器回归。另一 subagent 在 dev 上重做的"撤销 Bot" PR 与本次无关，未触碰。
耗时:约 35 分钟 · 归因:[AGENT]
