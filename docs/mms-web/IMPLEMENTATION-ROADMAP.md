# MMF Web：本地文件、四项能力与多 harness 路线

日期：2026-09-09。沿用 task 855b1bed42aa43bb。本文保留四项能力的设计来源。v4 已完成同一 Pi 会话内模型/通道切换和本地文件引用；跨 harness 交接及其余增量仍是规划。详见 NEXT-PHASE.md。

## 产品边界

Web 是本地工具的可视入口。文件已经在这台电脑上，应把原路径交给 harness；不要求用户上传、拆分或额外复制数据集。Web 保存引用元数据、展示图片和成果，harness 自己按需读取。只有截图/剪贴板图片这种没有可用原路径的数据才需要保存。浏览器的 File 对象不能提供可靠的完整源路径，因此通过本地服务打开系统文件选择器，或接受用户明确粘贴的路径；不能根据文件名猜路径。

2026-09-09 本轮采用：本地文件选择、路径粘贴、图片缩略预览、原路径传递，保留旧附件兼容。大文件 streaming-upload 方案已经按用户纠正收回，不是最终采用方案。文件引用没有 1 MB 或 64 MB 上传门槛；预览的读取量、单次模型输入量和文件本身的大小是不同限制。原文件移动或删除后引用会失效；引用不是快照。

## 四项能力如何加入

| 顺序 | 用户怎么用 | 实现落点 | 第一版验收 |
|---|---|---|---|
| 1 成果预览 | 生成文件后点击成果，在对话旁看；选中一段直接提修改 | 复用本地路径和文件服务，扩展 artifacts.py / ArtifactView；先 Markdown、文本、图片、CSV、独立 HTML；文件版本用 hash 识别 | Pi write/edit 和命令生成的实际文件都可发现；文件过期提示；修改请求带路径/版本/选段；HTML 预览不能访问 MMF API |
| 2 换模型继续（Pi 会话内已实现） | 点击“换个模型继续”，选择模型与通道，检查接续材料再启动 | SessionActions 与 MMS selection；增加可检查的任务摘要/材料包，创建新 runtime，保留旧会话 | 原通道失败也能选择新通道；目标/约束/文件/下一步完整可见；新模型/Key/effort/URL 确实生效；不假装迁移私有 thinking |
| 3 项目资料与记忆 | 选消息“记到这个项目”，在资料抽屉看来源、编辑或删除 | Web 管理用户确认的项目资料；Pi adapter 在本次请求组装/compact 时取用；事件记录实际注入来源 | 区分可用/已选/已读；停用后新请求不再注入；切换项目不串资料；先不做不可检查的自动长期记忆 |
| 4 分享有效做法 | 导出任务模板，对方看预览、补自己的模型与文件就能使用 | 现有模板升级为任务说明、Skills 需求、能力要求、示例输入/成果；先本地导入导出 | 不带 Key、环境变量、私有历史和原机器绝对路径；缺少 Skills/模型时指明缺口；导入先进入草稿，发送才执行 |

这四项属于 MMF Web 的共同能力，不应各写一套 Pi/Codex/OpenCode 页面。普通任务只显示当前有关入口，避免再出现“工作台”式功能堆积。

## Pi 为什么让现在的开发更容易

已检视源码：Pi 提供 Agent loop、工具执行、上下文管理及 RPC 事件，所以我们不需要重新实现 Agent。现在 Web 仍有 Pi 专属耦合：sessions.py 的创建/恢复、driver 构造、runtime control，以及 launch_bridge.py 的 RPC 参数。不能把它理解成已经做完通用 harness adapter，只差下拉选项。

其他 harness 也有可用程序接口，并非要重写其 Agent loop。新增工作主要是启动环境衔接、事件转换、会话恢复、交互确认、能力差异与长期版本维护。

## 接入选择

| Harness | 接入方式 | 工程判断 | 重点 |
|---|---|---|---|
| Pi | 已有 RPC driver | 当前基线 | 把 Pi 专属代码留在 adapter，继续验证现有交互 |
| Codex | App Server，优先 stdio JSON-RPC | 中等偏上，建议第一个新增 | conversation/turn/item、审批和提问、resume/fork、模型与 sandbox；沿用 MMS 的独立环境和明确认证 |
| OpenCode | 独立 server 的 HTTP API + SSE | 中等，适合第二个 | session/message/permission/Todo/diff、事件重连；避免多个 MMS 隔离通道误共享一个全局 server/provider 配置 |
| Claude Code | Agent SDK，或支持双向交互的 CLI adapter | 中等偏上 | streaming、permission callback、hooks/subagents、会话恢复、native plugin；不把一次性 -p 输出当完整交互接入 |

依据：[Codex App Server](https://learn.chatgpt.com/docs/app-server)、[OpenCode Server](https://opencode.ai/docs/server/)、[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)。这些是官方接口与本地代码审查所得的工程判断，未对其他 harness 做真实 MMF Web 接入验收。本轮没有启动 Claude。

### 共同实现步骤

1. 从现有代码提炼薄的 driver contract：start/resume/send/interrupt、events、user-question/approval、capabilities；保留 native session ID 与原始事件。
2. 为每个 harness 声明实际能力；Web 只显示支持的 effort、Skills、planning、fork 等控件。不把一个 harness 的参数硬塞给所有引擎。
3. 新增一个 harness，完整验证启动 → 工具 → 确认 → 中断 → 重启恢复 → 完成/未读状态；通过后再接下一个。
4. 每个 adapter 继续走 MMF 已选择的 runtime；路由、账号、协议、effort 的来源不另建第二套真值。不自动回退到全局账号。
5. 接入“新建与恢复 Web 自己管理的 session”后，再研究 Glint/CLI 已有会话发现。仅能读取历史不等于能接管正在运行的进程，不能重复启动同一个 session。

## Codex App 的 plugin 能否一起使用

可以复用一部分，但不是复制 Codex App 就得到全部能力。

- Skills、标准 MCP 等组件优先复用；Codex runtime 可以承载它实际支持的插件。某个插件还包含 UI、OAuth 或宿主能力时，需要分别适配。
- 官方 App Server 提供 app/list，并区分 accessible/enabled 等状态。官方当前把 plugin/list/read/install/uninstall 标为 under development，明确不建议生产客户端调用；因此第一版不把完整插件商城作为承诺。
- 官方资料说明 OpenAI API Key 登录可使用部分 curated plugins，部分 OAuth 流程不可用。MMF 某个转发通道的 Key 不能据此被视为 OpenAI 官方插件服务的登录身份；模型推理和插件服务认证应分别明确，不借用全局账号兜底。
- Codex App 内的浏览器、桌面、语音和专属面板，不会因为接入 App Server 自动出现。它们有额外宿主/连接服务，必须逐个验证。
- Claude Agent SDK 支持加载本地 plugin 路径；它的 plugin 和 DeepSeek Cordis plugin 不能直接当 Pi 扩展加载。

依据：[Codex plugins 与认证差异](https://learn.chatgpt.com/docs/plugins)、[App Server API](https://learn.chatgpt.com/docs/app-server)、[Claude SDK plugins](https://code.claude.com/docs/en/agent-sdk/plugins)。

## 建议顺序与完整接入的含义

本地文件引用与 Pi 会话内切换已落地。下一步扩展成果预览，再做跨 harness 可检查材料包；在这个过程中整理共同 driver contract。随后以 Codex 为第一个新增 harness 验证公共设计，之后再接 OpenCode/Claude。记忆和模板按共同材料模型推进，不依赖先集齐所有 harness。

接完多个 adapter 后，MMF 的启动能力会拥有完整得多的 Web 入口。但还需要逐项覆盖已支持 harness、账号模式、启动参数、原生会话恢复和特殊交互，才能称为“MMF 启动能力完整接入”。启动一个进程、可在 Web 聊天、完整原生能力对等，是三个不同的交付范围。
