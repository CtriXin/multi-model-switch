# MMF Web 下一阶段：让任务和成果连续起来

> v4 更新：Pi 会话内模型/通道切换与过程折叠现已实现。本文保留原调研背景；最新能力与下一步以 [NEXT-PHASE.md](NEXT-PHASE.md) 为准。


调研日期：2026-09-08。官方文档/公开源码与本机 Pi 0.85.1 已检查；未声称实际运行过这些外部产品的全部功能。本文是后续产品建议，不代表下面的新增能力已交付。

## 判断

MMF Web 应成为一个可接续、看得懂结果、方便带给别人的本地 AI 工具。模型和通道是基础，真正的差异在于：同一件事换模型仍能继续，成果可直接使用，成功做法能被别人复用。

单独的多模型聊天、Skills、MCP、Web 外壳已经不稀缺。MMF 有价值的积累是现有路由、协议兼容、能力/effort 规则、会话隔离和实际使用经验；这些是构建产品优势的基础，还不能仅凭功能数量称为别人无法复制的护城河。新的功能应让这套积累对普通用户产生可感知的收益。

## 哪些产品值得借鉴

| 来源 | 值得借鉴的具体体验 | MMF 如何采用 | 依赖判断 |
|---|---|---|---|
| [OpenCode](https://opencode.ai/docs/) | Plan/Build 切换；对修改不满意可 undo/redo 后调整要求；[分享会话](https://opencode.ai/docs/share/) | 先保留已有规划/分支，增加“从此处试另一个方案”和可预览的分享导出 | Pi 有会话分支，文件回滚另需快照；分享服务另需存储与访问控制 |
| [Codex review](https://learn.chatgpt.com/docs/code-review) | 对话内查看和评审改动，工作文件与任务保持联系；[worktree](https://learn.chatgpt.com/docs/environments/git-worktrees) 支持隔离修改 | 成果旁直接比较版本、对选中部分提修改；写代码的任务按需提供独立工作副本 | 不依赖 Pi 专属能力，但需要文件服务与 Git adapter；现有 MMF runtime 隔离不等于项目文件隔离 |
| [Claude Code](https://code.claude.com/docs/en/checkpointing) | 分别恢复对话/代码，或从指定位置总结，降低尝试成本 | 恢复菜单明确区分“另开对话分支”和“恢复文件”，不能混成一个按钮 | Pi JSONL 分支不能代替文件 checkpoint；Claude 文档也说明 Bash 修改不在其文件 checkpoint 覆盖内 |
| [ZCode](https://zcode.z.ai/en/docs/agents) | 在浏览器面板看 Agent 打开网页、点击并检查结果；[从已有工具导入 Skills](https://zcode.z.ai/en/docs/skill) | 先做成果预览，再接可见浏览器验证；Skills 采用来源清楚、可启停的能力管理 | 浏览器需要独立服务/连接器；本轮未证实 ZCode 的具体底层实现，不把它归为 Pi |
| [MiMo Code](https://github.com/XiaomiMiMo/MiMo-Code) | 项目记忆、任务 checkpoint、按预算重建上下文 | 做可查看、可删除、用户确认后保存的项目记忆，以及换模型时可检查的接续摘要 | 官方 README 明确是 OpenCode fork。Pi 的 compact/extension 可作为基础，记忆检索和管理 UI 需要补齐 |
| [DeepSeek Harness](https://www.deepseek.com/harness/en/) | Creator mode 检查运行时、试验插件、组合能力；有详细过程记录 | 把“Customize”做成能力清单与配置预览：本次启用了什么、来自哪里、会做什么 | 它基于 Cordis，插件不能直接装进 Pi。先写 Pi adapter 与受限 Web UI 协议，再谈可视插件生态 |
| [Kimi Web](https://github.com/MoonshotAI/kimi-cli/blob/main/docs/en/reference/kimi-web.md) | 稳定的会话阅读/分支，prompt toolbar 集中状态、Todo、上下文，结构化提问与子任务来源 | 巩固已有阅读交互；让扩展状态、Todo、确认信息保持明确来源 | 可复用 Pi 的 events/extension UI，但子任务树要先有真实执行协议，不能从一段日志猜出来 |

这些产品不都依赖 Pi。可借鉴的是交互和能力设计，不能把不同 runtime 的插件、会话格式或权限机制当成互换件。DeepSeek 的 Customize 也不是 thinking 的一种显示方式，而是运行时扩展能力。

## 与当前代码对账

已存在：Pi 真实启动与工具过程、运行中补充消息、会话分支、上下文统计/压缩、Skills/文件引用、文本与 Markdown 成果查看、MMF 通道模型配置。本轮已进一步完成连接地址/Key 编辑、连接检查和恢复自动 effort。

实际缺口：

- `mms_web/artifacts.py` 仅收集成功 write/edit 命名的 UTF-8 文件，限制 1 MiB；`ArtifactView` 只渲染 Markdown 或原文。HTML、图片、PDF、Office、命令生成的文件、成果版本尚未形成统一可用体验。
- `SessionActions.fork` 复制同一 runtime 与历史，工作文件夹共用；没有换模型/通道的接续流程，也没有文件回滚。
- `PiRpcDriver._handle_ui_request` 已处理 select/confirm/input/editor；setWidget/setStatus 等仍退化为扩展通知。Pi `custom()` 在 RPC 模式不可直接呈现，不能照搬 TUI 自定义组件。
- runtime 面板已经有 token、费用、上下文和队列；再增加一个统计 dashboard 没有明显收益。缺的是来源解释、失败后的下一步和可控操作。

Pi 能力依据：本机 `@earendil-works/pi-coding-agent` **0.85.1** 的 `docs/rpc.md` 与 `docs/extensions.md`，以及 [上游 RPC 文档](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/rpc.md)。命令包括 steer、follow_up、compact、get_session_stats、fork、get_commands；扩展可注册工具、订阅事件并参与 compaction。上游当前内容可能与本机版本不同，开发以实际运行版本的协议验证为准。

## 采用顺序

### 1. 成果就在旁边可用

用户说“做一个活动页面”，右侧出现实际页面；说“整理成文档”，右侧出现可阅读文件。接着选中一段，点击“修改这里”，引用文件版本和选中内容回到输入框。入口出现在生成了成果之后，平时不占空间。

第一版限制为 Markdown、文本、图片、CSV 和独立 HTML。HTML 使用隔离的预览 origin/sandbox，不能获得 MMF API 和 Key；远端资源默认不自动加载。PDF/Office 后续通过已有转换工具加入，不承诺浏览器直接编辑所有格式。大型文件走文件服务与下载，不能把内容塞进每次 session snapshot。

验收：真实 Pi 写文件及 Bash 生成文件都能找到；文件失效提示清楚；连续修改可区分版本；选段请求准确引用版本；生成 HTML 无法调用 MMF 写接口；窄屏在对话/成果间切换；不会因为打开成果启动另一个模型任务。

### 2. 换个模型继续

用户看到“当前通道不可用”，可选择另一个通道；或者觉得当前方案不理想，点击“换个模型试试”。先显示接续预览：目标、约束、已完成内容、文件与版本、下一步，然后创建新 runtime。原会话保留。

第一版采用显式接续，默认不自动调用第二个模型，不宣传无损迁移。不同模型的上下文限制、私有 thinking/signature、工具格式与能力不同；传递用户可检查的任务材料，必要时压缩。资料将发给新通道这件事应在选择时清楚显示。认证严格使用新选择的 MMF route，失败不回退到全局账号。原始上下文中的工具/文档文字仍是资料，不能升级为系统指令。

验收：换同模型不同通道、新模型较小上下文、原通道失效、附件不兼容四种场景；新请求的 URL、model、effort、Key 来源与选择一致；源任务保留；用户不重复描述目标；共用文件夹与独立工作副本的语义清楚。

### 3. 我让它记住什么、它实际用了什么

会话边上提供一个按需打开的资料抽屉：用户固定的资料、已启用 Skills、工具实际读取的文件、上下文余量。区分“可用”“已调用”“已读取”，不把启用误写成执行。

先支持选中消息“记到这个项目”，可编辑、删除、停用并显示来源；后续再做检索。避免无法检查的自动长期记忆。Pi 扩展可在组装上下文和压缩时读取这些材料，MMF 负责 workspace/会话隔离。

### 4. 把有效做法分享给别人

把现有任务模板升级为可检查的能力组合：任务说明、需要的 Skills、模型能力要求、示例输入与示例成果。收件人只补自己的模型连接和工作文件夹，即可开始。

先做本地导入/导出与逐项预览，不要求账号和云服务。默认排除 Key、历史对话、机器绝对路径、环境变量和原工作文件；用户选了要分享的文字/文件也先预览。这比分享一份几十项 config 更接近普通用户的需求。

### 5. 有边界的能力扩展

把扩展分为资料、工具、界面三类。先利用 Pi 已有的 select/input/widget/status，补齐真实可操作呈现；插件安装前显示来源、版本、需要的访问能力和配置。再考虑用户描述需求后生成一个能力草稿。

不建议现在实现任意插件热加载到主 Web origin，也不直接运行 DeepSeek Cordis 插件。不建议把自主修改整个 MMF、自动多模型对战、桌面宠物或大型调度看板放在前面。能力实现、权限、版本兼容和卸载清理尚未解决时，商城只会把配置复杂度带回来。

## 稍后再做

- 可见浏览器操作：借鉴 ZCode/Codex，但普通 Web 不能随意控制其他网站或桌面，需要 browser backend/扩展或桌面宿主。
- 文件 checkpoint 与方案比较：先解决工作副本和并发修改检测，不用 `git stash/reset` 冒充可靠的项目回滚。
- 定时任务与完成提醒：有用，但 Pi RPC 本身不是持久调度器；应接独立任务服务，处理重启、取消、重复执行和通知。参考 [Codex scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app)。
- Runtimia：借它“任务、过程、成果、失败原因留在一起”的处理，不复制它的看板和组织层。当前本地 README 仍以 Multica 为标题，本轮只据此识别适用思路，未验收 Runtimia 的全部独有实现。

## 首轮落地决定

下一阶段先做第 1 项“成果就在旁边可用”，再做第 2 项“换个模型继续”。第 3、4 项一起形成可解释、能分享的使用经验。这些构成 MMF 应优先积累的产品优势；其他 harness 的聚合继续排在其后。
