# v5.0.0 · Bot 工作台预览

## 升级须知

本版本走 `dev-pre` 预览通道，不是 Stable。5.0 的边界是 Bot 工作台；`dev` / `main` 继续维护 `4.22.z` 稳定线，两条线在 owner 宣布 5.0 发布前不合并。

内容由两部分组成：`dev-pre` 上的 Bot 工作台，加上 v4.21.1–v4.21.14 的全部 Windows 修复，以及 v4.22.1 的版本一致性修复。配置根仍是 `~/.config/mms-next`，无需迁移；已有 config、session 和 OAuth 不受影响。

Bot 工作台的功能验证在 macOS 上进行。**Windows 上的 Bot 工作台没有做过验收**，本版本合入的 Windows 修复只覆盖 Pilot、Pi 启动与会话链路，不构成对 Bot 工作台的 Windows 支持声明。

## Bot 工作台

- **长期 Bot 身份**：每个 Bot 有独立身份和长期会话，记忆存放在 `state_root/bots/memory/<botId>/memory.json`，与 Pi 会话和 workspace 分开；切换模型或重启服务不会混用记忆。`presetId` 可以留空，执行任务时再解析当前可用的默认 Pi preset。
- **新建即对话**：点击“创建 Bot”直接生成可用的 Bot 并进入聊天。onboarding 向导多出一步起名，并给出建议名；聊天头部可以就地改名称、简介和头像，弹层锚定在头像下方，不产生布局跳动。用户消息可以存成长期约定（“你以后叫小天才”“以后都先给我方案”），一次任务结束后会提示一次是否要存；预设编辑器可以列出和删除这些约定，同时保留手写的 prompt 行。首次 onboarding 的每个回答立即保存，可重新打开修改。
- **几何头像**：十种几何形状的头像选择器（含 star、ghost），随机匹配形状和颜色。
- **聊天派活**：Bot 窗口按 Bot 聚合历史任务，自动路由的新任务和指定 Bot 的任务接在同一条对话里，不需要切换任务块。主聊天只呈现用户消息、Bot 回复、成果和等待提示；`bash`、`exit`、内部 `list`/`wait` 等 CLI 诊断保留在任务事件数据中，不进主聊天。
- **Bot 间往来折叠**：Bot 之间的握手事件不再刷屏。同一轮往来折叠成一张可展开的摘要卡，卡片正文用 Bot 自己的说明，通讯视图按真实分节展示。折叠只识别真正的 peer 事件：普通叙述里提到另一个 Bot 的名字不会被折走，回复链遍历带环检测。
- **等待契约**：任务只有在真的有问题要问时才进入 `waiting/user`。等待记录带 `waitQuestion` / `waitOptions` / `waitSince`，按 Bot 汇总成 pendingQuestion，旧数据在加载时迁移，七天后过期。问题每一轮重新计算，回答或任务结束后清除，不会拿上一轮的旧问题继续挡着你。只在 Bot 之间来回、不需要你介入的琐碎任务不再写进 Bot 记忆。
- **失败重试与结果送达**：基础设施类错误做有界重试；任务事件（完成/失败/等待/重试）通过 `GET /bots/notifications` 拉取，webhook 列表存在 `state_root/bots/notify.json`。
- **Bot 间消息**：独立于 `dispatch` 的 `message`/`reply` mailbox，用于通知、澄清和追问，不伪装成用户消息。接收方空闲时自动投递、忙时排队，每条消息有 `queued`/`delivered`/`processed`/`waiting`/`failed` 回执；连续自动往返超过 8 跳会暂停，避免空转。
- **Coordinator 计划**：计划从提示词里拿出来，成为落库、可见、可执行的对象。需要规划时用该 Bot 自己的 preset 发一次短 planner 请求（用完即弃，不常驻），要求输出严格 JSON；解析失败、模型不可用或超过 20 秒退回关键词计划并标记 `source: "fallback"`，任何情况下不阻塞任务启动。多目标请求不再因为“没出现协作关键词”而直接走 direct：`direct-first` 路径改为按目标数量决定是否出计划，计划有 `plan_settled` 状态门、步骤依赖和重试/跳过策略，前端 `BotPlan` 直接展示。被跳过的前置视为已完成，direct 计划的唯一步骤在负责人完成后落到终态，不会停在 ready / pending。`mode == "delegate"` 时由 runtime 按 `dependsOn` 执行，沿用现有 dispatch 路径、五层深度和同链不重复守卫。
- **Ego 浏览器执行**：浏览器操作收敛到 `BrowserProvider` 合同。macOS 且已安装 Ego 时提供任务自有的持久空间、导航、点击、输入和截图；未安装时明确返回不可用，不把 isolated backend 冒充为登录态浏览器。
- **会话隔离**：Bot 会话标记 `owner=bot`，不出现在 Pilot 的会话列表里。截图保存为 task-private artifact，只通过校验过的内容 URL 读取，裸本地路径不经 HTTP 暴露。
- **预设编辑器修正**：重开编辑器不再把 Bot 名字悄悄换成建议名；编辑器有明确的关闭入口，固定底栏不再被额外约定挤到后面，名称输入框不再出现双重焦点圈；改名时按 Escape 只取消这次改名，不会连编辑器一起关掉。
- **Bot 页不弹引导**：Pilot 的首次引导是为会话工作区写的，在 Bot 页没有意义。自动开始改由 `isGuideReady` 控制，`startIntroduction` / `guideNavigate` 会先回到新建会话页；欢迎步骤保留在你启动它的那一页，不再把你从当前会话上弹走。

默认最多同时运行 3 个任务；不同 workspace 的任务并行，同一 Bot 或同一 workspace 的任务串行。这是协调规则，不是操作系统级沙箱：Bot 使用当前用户权限，workspace 之间不能当作安全隔离边界。

自动唤醒只在 MMS 服务进程和当前电脑都保持运行时发生，不会开机或唤醒睡眠中的电脑，也不保证无人值守的网页登录、验证码或账号会话始终有效。

## 包含的 4.21.x Windows 修复

合入 `v4.22.1`，包含 v4.21.1 到 v4.21.14 的全部修复，以及 v4.22.1 的版本元数据修复：

- Pi 启动：允许更慢的启动握手；RPC 管道在 launcher 中保持传递；Pi 的 bash 不可用时改用 PowerShell。
- 会话历史：Pi 历史按 UTF-8 读取，GBK 系统不再出现乱码或轮询中断。
- 工作区：支持文件夹选择器，并保持选择器在长列表下可响应。
- Pi 生命周期：sink 出错后 RPC reader 继续存活，流式历史不再中断。
- Pilot doctor：自检，可选模型 smoke。
- 会话守护：用 Win32 API 查询守护进程 pid，不再依赖命令行工具输出的编码。
- Pi 共享 bin：Windows 上改用 junction 建立共享 agent bin 链接，不再依赖需要开发者模式或提权的符号链接；POSIX 仍走原有 `os.symlink` 路径。
- Pilot skills 读取：Windows 没有可用的符号链接 overlay，改为按优先级直接把选中的 skill 条目传给 Pi，避免扫描父目录把被覆盖的 skill 带回来；子进程输出固定按 UTF-8 解码。
- 成果预览：Windows 缺少 `O_DIRECTORY` / `dir_fd`，改为逐段词法校验路径，对工作区根、每级目录和目标文件都拒绝符号链接、junction 及其它 reparse point。
- 服务日志：未归类异常在返回通用 500 的同时把 traceback 打到服务日志，用户可见文案不变。

同时带入 README 的 Windows Native Preview 从零安装步骤、`docs/mms-web/WINDOWS-CONTRIBUTING.md` 与 `WINDOWS-PI-FIX-HANDOFF.md`。

细节以 `RELEASE-v4.21.0.md`、`RELEASE-v4.21.1.md`、`RELEASE-v4.21.14.md`、`RELEASE-v4.22.1.md` 与对应提交为准。

## 验证边界

本分支上执行过：Bot 相关 pytest、Windows / updates / whats-new / release 相关 pytest、`apps/mms-web` 的 node 测试与 `tsc --noEmit`、fresh-user gate，以及针对 `origin/dev-pre` 基线的 pytest 回归对比。

未执行：Windows Acceptance workflow 没有在本分支跑过；Windows 上的 Bot 工作台没有真实机器验收。Windows Native 仍是 Preview，本版本不宣称 Stable。

Bot 工作台涉及本机文件、浏览器和长期后台执行，预览通道的使用者应自行核验成果，不要把任务结果当作已审计的产物。外部副作用仍需按成果核验，不能保证任意外部系统 exactly-once。

## 回滚

`dev-pre` 是预览通道，可以回退到上一个正式 release（`v4.21.14` 或更早的 4.x）。Windows 安装保留版本目录，出现问题时可停止 Pilot 并选择先前版本目录；不要删除包含会话和 runtime 的 state 目录。Bot 数据位于 `state_root/bots`，回退到不含 Bot 工作台的版本后该目录不会被读取，但也不会被自动删除。
