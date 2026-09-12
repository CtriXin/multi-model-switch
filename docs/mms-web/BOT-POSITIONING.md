# MMS Bot 定位与能力复用边界

MMS Bot 是 MMS Pilot 的正式执行层升级，不是额外的装饰功能。Pilot 的普通 Web 会话面向“我现在直接做这件事”；Bot 面向“我交代目标，由一个有身份的执行者持续完成、分发、等待、记忆并回报”。

## 三层职责

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| Web UI | 聊天、Bot 选择、任务状态、成果、协作和记忆可视化 | 直接实现浏览器或 Terminal 引擎 |
| Bot / MMS | 角色、路由、调度、唤醒、Bot 间通信、结果回执、记忆 | 重写已有工具能力 |
| 外部执行器 | Pi Harness、Ego、Skill、Terminal、文件和模型 Provider | 替 Bot 决定业务目标 |

## 浏览器策略

浏览器能力由外部 `BrowserProvider` 提供。macOS 且已安装 Ego 时，导航、页面读取、点击、输入、上传、截图、登录态和用户接管都交给 Ego；Windows / Linux 可以由 Web Access 连接用户明确授权的 Chrome 或 Edge CDP。MMS 只做上下文桥接和结果归档。Provider 不可用时显示明确的 capability unavailable，不降级为一套自研的假浏览器。

## 复用优先级

1. 已安装且可调用的 Ego / Pi / Skill / Provider：直接复用。
2. 免费开源项目：先核对许可证、运行方式、登录态、维护状态和安全边界，再做 adapter。
3. 只有在没有成熟实现、且它是 MMS Bot 核心差异的部分，才自行开发。

## 候选复用项目

这些项目先作为 adapter 或参考实现评估，不直接替代 Ego：

| 项目 | 可复用部分 | 当前决定 |
|---|---|---|
| [Browser Use](https://github.com/browser-use/browser-use) | 浏览器任务循环、页面观察与动作规划 | Ego 已满足浏览器执行时不接入，避免双引擎 |
| [OpenHands Software Agent SDK](https://github.com/OpenHands/openhands) | Agent server、事件流、工具和 workspace 抽象 | 评估其事件模型，不搬入另一套 Harness |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 长任务状态机、检查点、可观测编排 | 只有当前调度器出现真实瓶颈时才做局部 adapter |

复用前必须核对许可证、维护状态、认证方式、数据边界和是否能接入现有 MMS/Pi/Ego 路径。仓库存在不等于可以直接嵌入产品。

## 当前与 Pilot 的体感差异

- Pilot Web 会话：用户发一句，当前 Harness 直接完成，反馈快，适合单一目标。
- Bot Web 会话：用户交代一个目标，Bot 可以选择模型、调用 Skill、使用 Ego、分发协作者、等待唤醒、汇总成果，适合长任务和重复工作。

Bot 内部仍然使用同一套 Pi Harness 和 Skill；变化在于它们被一个持久化的 Bot 身份、调度器、通信和结果界面包起来。

## 不在当前范围

暂不自研操作系统级 Computer Use、桌面窗口控制、通用 Connector 平台和云端 VM。它们应在发现成熟可复用执行器后通过 adapter 接入，而不是复制一套新引擎。Windows 第一版只承诺浏览器内 Computer Use，不承诺任意桌面应用控制。
