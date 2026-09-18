# 能力对照：保留什么，放在哪里

本表回答“如何减少重复维护”，不声称 DSH 已通过 MMS 的运行验收。DSH 固定在 `ddefc45fbc7f8e46dd73185e68295696d1297887`，MMS 固定在报告首页的 main/dev。下文“可做插件”是基于公开接口的设计判断，尚未实现验证。

分类：**P** 插件/preset 候选；**C** 自有发行/服务集成；**R** 留在独立 MMS；**D** 满足替代条件后不迁移旧实现；**T** 保留验收资产；**H** 历史整合/文档。分类可重叠，不能把 PR 数当功能数或维护成本。

## C01 模型通道、registry 与配置管理 — P + R

MMS 的价值是 Router/Lineup/Profile/Policy 分工、用户通道和账号绑定、批准数据、发现结果的 replace 语义、敏感通道的显式 manual、真实阻塞原因。主要见 #113、#127、#175、#204、#211、#236、#285，以及 #313/#315。

DSH 已能通过 `llm-pi-ai` 配置多 provider 和自定义协议，无需为普通 OpenAI-compatible 通道写整套 adapter。差异应放在 MMS registry 到 DSH 的导出/解析插件，复用现有 MMS 控制面；不要复制第二份模型数据库。其 `apiKeyEnv` 缺失时，catalog route 可走 provider 原生 ambient discovery，因此 MMS 的“当前账号失效就停止，绝不掉入全局账号”**不是自动继承**的。明确绑定 credential，按请求验证实际 route，才算接入完成。[DSH adapter](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/llm/llm-pi-ai/README.md)

**验收**：删掉远端模型后新会话不可再用；空/失败 discovery 不清空配置；缺失选中凭据必须失败；不得读另一账号的全局凭据。可行性中高，尚无实测。

## C02 能力真值、context、effort、vision relay — P + R + T

#114/#127/#168/#185/#194/#209/#213/#216/#227/#233 不是一组应永久保留的硬编码。应保留的是统一 resolver、来源证据、人工覆盖优先级、实际 consumer 校验，以及 vision relay 的同通道边界。#233 已收敛多处 context 真值；不要把先前 K3 256K/1M 补丁全部叠进 DSH。

DSH adapter 提供模型/协议/capability 元数据，UI 只呈现 adapter 声明的 effort。可以导出 MMS 已解析结果；vision relay 可优先复用 MCP 或做 tool plugin。**pi-ai 库不等于 Pi CLI**，Pi 的 models.json、RPC、扩展加载逻辑不能原样当作 DSH adapter。[模型与 effort](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-model-selection/README.md)

**验收**：UI、实际请求、context/effort 完全一致；明确协议不被静默替换；不能识图的模型借用后，凭据不进入工具返回。可行性中高。

## C03 Recipe 可分享场景 — P，优先级最高

#143 的 Recipe v2 具有变量、示例、期望结果、Skills/image/reasoning 要求、导出预览及已知凭据/路径清理。后端在解析实际启动模型及所选 Skills 后重新检查，缺能力直接拒绝。来源：[recipe-core.ts](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/apps/mms-web/src/recipe-core.ts)、[recipe_requirements.py](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/mms_web/recipe_requirements.py)、[sessions.py](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/mms_web/sessions.py)。

DSH preset 并非“什么都不校验的目录”：它检查 composition/module 能否加载，失败的 preset 有原因，运行后不能随意换 composition。可是这些检查与“接收方自己的模型满足 Recipe 要求”不同。适合做 **Recipe UI + schema/导出包 + session 启动前校验插件**，preset 只负责组合。现有证据不足以宣称 Recipe 是永远不会被上游覆盖的独有护城河。[DSH agent-presets](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/preset/agent-presets/README.md)

**验收**：另一台机器用自己的 Key 导入；满足要求可启动，不满足明确拒绝；正文/示例中的已知凭据不外泄；导入不自动执行。脱敏仅覆盖已知模式，不保证所有业务资料都可公开。可行性高。

## C04 项目资料与上下文消费证据 — P

#116/#143 的人工确认资料、revision/hash、防并发覆盖，以及按真实消息/工具记录的来源，可以经 DSH system-prompt/context、session 扩展事件和 UI projection 实现。DSH 有 skills/reference/context 基础，但“列出可能加载的资料”不等于“证明这一轮实际消费了什么”。保留这一区分。[MMS project_materials.py](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/mms_web/project_materials.py)、[DSH Session](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/session.md)

**验收**：资料改变后旧证据不被重写；旧历史无证据不得补造；两个窗口并发编辑可见冲突。可行性中高。

## C05 成果预览、快照与选段 — P + D

#115/#128/#155 中，通用文件预览可优先使用 DSH deliverables/sidebar。MMS 的 `ArtifactHistory` 则把真实工具完成后的文件内容保存为有界 blobs，并记录 hash/revision；这是独立增量，不只是 UI。DSH `present` declaration 本身不保存文件内容，但还有 Git changes review，故不能笼统说 DSH 没有历史/差异功能。[MMS artifact_history.py](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/mms_web/artifact_history.py)、[DSH deliverables](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-deliverables/README.md)

**迁移**：如仍需非 Git 文件快照及 hash 绑定选段，做存储/工具事件/UI 插件；否则旧预览渲染器可退休。**验收**：源文件后改/删除时，明确区分快照和当前文件；路径越界拒绝；存储限额可见。可行性中。

## C06 Skills、Weber 与任务工作包 — P + R

#130/#132/#155/#216/#258 的多数 skill 内容、MCP 服务和工作约定可以复用。DSH 已有 skills 和插件组合，不应重新制作安装/发现框架。保留来源、同名冲突、会话隔离、发送前只形成草稿的 UX。[DSH skills](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/skills.md)

Pi-specific 扩展注入继续供 Pi launcher 使用；正式取消 Pi Web 后才退役那层映射。安装器曾退休的全局 hooks/强装技能不恢复。可行性高，具体 browser backend 的运行权限与登录态仍需独立验证。

## C07 手机/LAN/公网入口与认证 — P + C + T

#149/#169/#181/#186/#283/#317/#329/#338/#339 形成 token、Host/Origin、QR、当前窗口 cookie、软键盘和更新 guardian 的组合合同。MMS 有 LAN 能力，不等于公网隧道已经替用户部署，也不等于手机一小时使用验收已完成。

DSH 固定版本的标准 `dsh web` 选择 loopback，并拒绝 `--host 0.0.0.0`；底层 web-server 可对外绑定，但认证/Origin 由 composition 负责。因此手机访问**不能仅凭一条标准启动命令认定等价**。可尝试自有 remote composition/Host 插件与 UI，需保持 Connection 全链路保护。[DSH HTTP Server](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/web-server.md)

**验收**：手机真实 LAN 读/写/附件/批准；无 token 拒绝；切换或轮换 token 当前窗口不掉登录；升级、回滚仍认证；软键盘不遮挡；关闭后释放监听。可行性中，尚不能保证无需任何上游扩展点调整。

## C08 历史、续接、CLI adoption 与失败恢复 — P + R + D

#149/#159 提供 Pi transcript 只读及复制采用；不是接管原 CLI 进程。`sessions.py` 持久化 resume 信息，服务重启后不会把旧队列伪装仍在运行。#341/#342 的“接续工作”在快照中仍 OPEN，只计候选，不能说当前两线已经具备。[MMS sessions.py](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/mms_web/sessions.py)

DSH 的 append-only Session/persistence 可替代新 DSH 会话底层；Pi JSONL 与 MMS task/state 并不因此兼容。保留旧历史只读，另写导入/脱敏 handoff/显式发送插件；不要伪装成无损 native resume。[DSH Session](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/session.md)

**验收**：关 CLI、关浏览器、重启服务、重启机器分别测；数据还在、可续接、进行中副作用是否重放分开判断。恢复新草稿未经用户发送不得执行。可行性中。

## C09 多 CLI launcher、账号隔离和协议适配 — R

#152/#164/#168/#175/#199/#204/#205/#208/#212/#213/#215/#227/#228/#233/#244/#248/#292 的相当一部分是 Claude/Codex/Pi/OpenCode/Grok 的启动与路由合同。DSH 是一个可接入的 harness，不会自然取代“管理多个既有 CLI”的产品需求。MMS 可继续作为这部分权威，增加一个 DSH 启动 adapter。[MMS adapter registry](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/mms_adapter_registry.py)

如果未来明确只用 DSH，才讨论逐个 CLI adapter 的退役。目前没有这种授权或需求结论。不能归入“完全抛弃”。

## C10 安装、服务发现与生命周期 — C + R

#120/#137/#147/#153/#189/#200/#202/#205/#226/#231/#234/#256/#257/#270 可保留为 MMS/自有发行层。DSH 进程可作为被管理程序，不需要 fork core 才能管理启动、日志、地址与版本。

MMS [service.py](https://github.com/CtriXin/multi-model-switch/blob/54d3ff991a2e332563c643cdfc7300c5bb4c52d5/mms_web/service.py) 开头明确说明当前没有 supervisor。后台 detached 进程不等于开机自启、崩溃自愈或运行任务跨 reboot 自动继续。若用户需要这些，应单独补服务管理与恢复策略，不能声称 4.x 已全有。

**验收**：新机器安装、找到正确 instance、port 保持、退出 shell 不退出服务；开机自启属于另一个尚未证明的验收项。

## C11 更新、回滚、版本真值与升级确认 — C + T

#137/#195/#198/#232/#266/#299/#313/#315/#319/#327/#328/#338/#339 的价值是安全发行合同。使用固定 DSH 包版本和自有 plugin lock，配合本地更新器、manifest 与回滚，而非直接 fork 其整个发布系统。Python updater 原样移植通常得不偿失。

**验收**：候选 ready 后才切换；安装/服务/bundle 版本相符；损坏 metadata 不覆盖；LAN 开启升级仍可认证；失败回滚文件/状态；5→4 不伪装自动降级。DSH 的 npm 更新命令不能直接算这些全部通过。

## C12 模型/effort/focus/移动端与阅读 UX — P（差异）+ D（通用实现）

#133/#135/#174/#179/#180/#236/#288/#289/#303/#304/#311/#314/#320/#323/#329/#331/#332 涉及用户确实在意的交互。DSH 已有 provider 分组、模型/effort、键盘菜单和异步 generation guard；不能因此假定它有 MMS 的独立常驻 effort、友好通道名、手机 bottom sheet、同等 focus/失败保留草稿。

优先用 DSH 原生 UI；只把仍存在的差异放到 `conversation.input.model` 等已声明 slot 或替换 UI package。UI 插件并非能随意插进任意内部组件，缺 slot 的点需要先证实。[DSH model selection](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-model-selection/README.md)、[UI slots](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-slots/README.md)

**验收**：两次点击改 effort；失败保留选择/草稿；成功才关菜单；打开输入框即有 focus，关闭回入口；390px/真实软键盘；异步旧响应不得覆盖新选择。按项判断，不为像素一致而整体 fork。

## C13 聊天状态、steer/queue/interrupt 与 BTW — P + D + T

#221/#258/#259/#281/#286/#294 的底层很大一部分与 DSH session/control 重合。DSH 子代理/队列能力可作为底座；不过 Pi 的 `BTW_EVENT`、side-question 脱敏上下文、主 transcript/queue 隔离、取消和“撤回已经送出则不能显示成功”不是名称相同就自动满足。[DSH subagent](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/subagent.md)

**迁移**：先沿用原生主会话；缺失的 bounded 旁问作为 tool/host/UI plugin；目标验收通过后退出旧 Pi RPC→Web 事件翻译和重复队列状态。

## C14 项目定位、文件夹树、拖拽引用 — P + D

#128/#132/#182/#250/#251/#307/#333 的需求值得保留；其中原生 OS picker 及其显示/超时补丁已被应用内树替代，可不再迁移。DSH 有 workspace、附件和文档预览，但“手机浏览主机目录、同名目录指纹找路径、路径仅插入草稿”仍要逐条对齐。[DSH workspace](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/workspace.md)

**验收**：不同 OS 路径、symlink/reparse/权限、层级截断、键盘左右、请求取消、手机路径可读。差异以 workspace route + UI plugin 实现。

## C15 品牌、中文帮助、入门与版本入口 — P + C

#119/#131/#142/#143/#216/#218/#243/#277/#322 的内容和目标用户路径可保留。DSH 官方品牌本身也是 package，占用 sidebar/hero slot，品牌替换不构成 fork core 的理由。[DSH official brand](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/client/ui-brand-official/README.md)

新用户连接流程、Recipe 示例和中文术语可做自有包；旧教程 DOM selector、过期版本文案与 duplicate What's New 状态无需迁移。

## C16 持久 Bot 身份、主会话、记忆与下一轮模型 — P

#242/#254/#265/#270/#306/#310/#314/#331 不能仅按“DSH 有 persona”判定全部重复。DSH preset/persona 负责 composition/prompt；Session 可持久化，Agent Team 有成员身份和 mailbox，确有明显重合。MMS Bot 还包含面向任务的独立配置、owner、长期记忆、自动唤醒以及主/临时会话边界。[DSH persona](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/preset/persona/README.md)、[Agent Team](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/agent-team.md)

**迁移**：保留用户确实使用的 Bot 产品层，复用 DSH Session/child 生命周期，避免再写 LLM loop。并非主张把目前整个 Bot runtime 原样包进 plugin。**验收**：Bot 设定改变不误关 wake、不污染主 session；临时任务结束回收；失败或 reboot 不自动重放副作用。可行性中。

## C17 计划、批准、DAG 与协作 mailbox — P + D

#241/#242/#265/#310/#315 与 DSH Agent Team task DAG、subagent/continuation 重合较高。默认复用其底层，保留人能读懂的计划、批准/拒绝、步骤指定模型与结果汇总。[DSH Agent Team](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/agent-team.md)

**验收**：依赖未满足不启动；用户拒绝不偷偷换路径执行；指定模型不是只改标签；父任务只恢复一次。团队 writeScopes 是 advisory，不能当真实写锁或权限隔离。可行性中。

## C18 独立日程、时区、周期和管理 UI — P

#278/#302/#306/#315 的 once/interval/daily/weekly、IANA zone、错过策略、启停/编辑及持久化，与 DSH 当前 schedule 不等价。DSH 是 session-local reminder，支持一次及固定间隔，原 Session 活跃时才派发；冷 Session 不运行 timer；没有 calendar/Cron recurrence zone；fork 不继承 active reminders。MMS 也必须有服务运行，持久日程不等于操作系统关机时还执行。[DSH schedule](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/schedule.md)、[MMS bot_schedules.py](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/mms_web/bot_schedules.py)

适合独立 Host scheduler + store + UI plugin，通过 SDK/服务接口派发会话。**验收**：DST、错过周期、暂停 once 不误消费、编辑不漂移、dispatch 前持久化失败不重复执行。可行性中，工作量显著高于一个 preset。

## C19 Fleet 多模型意见与只读 worker — P，保留用户要求

#295 已修复并合并，主修复也见直接提交 `5707bb07`、`789d45ba`。用户明确要求保留，不因 DSH 存在就替用户取消。

DSH subagent 支持 provider/model/effort 的 `agentOptions`（backend 需声明支持）和 `toolFilter`。这为插件实现提供了具体入口；但 shipped fork tool 继承父 route，**不能直接拿 fork 默认行为当多模型 Fleet**。需要 spawn 或自有支持精确路由的 backend，以及 coordinator 汇总/UI。[DSH subagent contract](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/subagent/subagent/README.md)、[tool-subagent](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/subagent/tool-subagent/README.md)

**验收**：精确模型失效就停；只读工具 allowlist；不能借 tool/MCP/子代理扩权；不续聊/fork/改主 Bot 模型；不写共享长期记忆；成功失败都回收；保留分歧和风险，不伪装一致共识。可行性中高，未经实跑不能宣称与修复版 #295 等价。

## C20 执行前重试、通知与结果投递 — P

#240/#242 的 pre-start bounded retry、通知日志、HMAC webhook 可做 Host 插件/外部服务。DSH provider 内 LLM retry 与“任务执行开始前重试”不是同一层；二者叠加需要定义边界。[MMS bot_retry.py](https://github.com/CtriXin/multi-model-switch/blob/afd5575e3971c782d3d4f1f6dbce547cc4778ae8/mms_web/bot_retry.py)

**验收**：执行已经开始后不因一般错误重放任务；通知失败不冒充任务失败；投递重试去重；secret 不进入用户结果。可行性中高。

## C21 Stable/Preview 与数据兼容 — C + T

#253/#255/#262/#271–#274/#279/#299/#327 是 MMS 当时的产品/发布决策，不是 DSH 产品功能。自有发行可以继续区分稳定和试验配置，但没有必要照搬三个历史分支的全部往返结构。

保留账号/数据根保护、未知 owner fail-closed、升级和降级不误导、旧历史仍能读；先做版本化数据合同再谈删除旧运行时。现有 5→4 需要安装器，不能用 UI channel 下拉证明自动回退。

## C22 Windows 与跨平台可靠性 — C + R + T

#231/#244/#246/#248/#249/#250/#251/#318 有大量 Python/Pi 专属适配。若这些组件还在 MMS 中使用，继续维护；DSH runtime 不原样搬 shim。保留中文路径、进程 pipes、原子写、锁、reparse 安全和打包产物与源码一致的验收。

DSH 在 Windows 的目标组合必须另测；本次未跑 Windows DSH，也不把 Windows Server Preview 证据扩大成任意桌面可用。

## C23 测试与验收规则 — T

#196/#210/#211/#228/#266/#309/#312/#326/#333–#336 值得保留的是失败案例、mutation、真实 handler/组件接线、新机器与发行门禁。不要把旧 Python/React 实现绑定测试全部平移，也不能因为改平台就丢掉案例。

特别保留：删除/skip/xfail 不算修复；source/build/CI/安装/浏览器用户验收分开；模型标签不证明实际模型；工具限制需负向测试；运行前后真实版本回读。

## C24 发布、整合与文档历史 — H + C

纯版本 stamp、生成 bundle、main/dev 同步、重复回补不应视为数十项独有功能。它们不搬进 DSH runtime，但保留 changelog 和关联以便追溯。#124/#229/#269/#313/#315/#335/#336 这类混合 PR 含真代码，台账已分别标注，不能按 `release:` 前缀一刀切。

## C25 自愿反馈 — P + C（未合并候选）

#330 的本地计数、低打扰邀请、用户点击打开表单适合 UI/preferences 插件。不是平台迁移前置，不应为迁移自动新建/发送外部数据。本次快照仍 OPEN；报告只评价方案位置，不代替原 PR review。

## 对“fork 魔改”问题的明确回答

**目前没有一项已取得“必须长期 fork DSH core”的证据。** 建议拥有自己的版本化发行仓库，内容可以是：MMS route/Recipe/Fleet 等 bundles、profile/preset、品牌与中文入门包、安装器/服务管理、依赖 lock 和兼容测试。这是自有产品，但不必维护 DSH 源码分叉。[官方 bundle/profile 机制](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish)

只有实际 spike 证明以下必要能力不能用现有接口表达，才讨论小 patch/fork：远程认证与生命周期边界无法组合；必需的精确模型/权限限制在 backend 被忽略；不可替代的 UI 入口没有 slot 且上游不愿补。每个 patch 要记录拒绝理由、影响包和退出条件。不能为了品牌、普通 provider、persona 或改菜单样式先 fork 整个 monorepo。

插件也有兼容维护成本，尤其 DSH 是 preview。应 pin 已验证版本、集中升级，不承诺“每天自动跟上游且免费获得全部能力”。
