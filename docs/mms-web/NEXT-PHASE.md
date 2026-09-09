# MMS Web：产品方向、技术边界与下一阶段交接

日期：2026-09-09。维护者：Codex / gpt-6-astra。原开发任务：Stride 855b1bed42aa43bb。

本文保存产品意图与当前代码的边界，供下一次开发直接接续。v4 发布与分支晋级状态以 GitHub tag、Release、PR 及原 task 的最终交接为准；本文不把路线图当成交付。

## 我们在做什么

用户长期在 Glint 中通过 MMF 启动不同 harness，再选择 provider、模型和通道。MMS 的价值在这些选择背后的运行能力：协议兼容、模型能力与 effort、通道规则、会话环境隔离、恢复、Skills 注入和故障诊断。新产品要让普通人也能用上这些能力。

目标是一个特别顺手的本地工具：安装后配置自己的模型服务，选择工作文件夹，直接说需求；随时理解 AI 正在做什么，能找到自己的提问，能拿到成果，能换模型继续。用户明确不喜欢后台、工作台、功能卡片墙和大块绿色侧栏，也不接受只有历史会话列表的展示壳。

Kimi Web 的截图是交互参照，用户没有要求复制 Kimi 的品牌。真正需要借鉴的是工具记录的信息密度、可折叠过程、提问导航、hover 操作、状态与输入框的集中设置。Codex App 的阅读细节与 Glint 的状态/完成高亮也属于参考。不要再次只换颜色、加大标题或堆设置来宣称设计完成。

## 为什么先做 Web

v4 使用本地 Python 服务与 React 页面，AI 仍在本机通过 MMS → Pi 执行。这样复用已有 launcher，先验证真实产品，不必立即维护桌面壳、多个系统安装包与更新机制。Web 页面已经预编译随 MMS 分发。

这是阶段选择，不是 desktop 不可行。研究过的 desktop-cc-gui 是 desktop 项目，使用发布包分发，macOS 签名、公证与商店上架是不同问题。用户有 Apple 开发者账号；未来如果系统文件拖放、开机启动、托盘和零终端安装确实是首要痛点，可以在同一 backend/UI 上增加轻量 desktop shell。无需为了 desktop 重写产品或先去 App Store。

本地 Web 仍有真实成本：后台服务生命周期、PATH/Node、浏览器拿不到完整原文件路径，以及不能直接把 localhost 地址分享给别人。当前没有远程多用户认证，不应把本机工具宣传成云端协作服务。

## v4 当前能力

| 用户任务 | 当前实现 | 明确边界 |
|---|---|---|
| 开始和继续真实任务 | Pi RPC、原 MMS launch chain、流式回答、工具执行、原生历史恢复 | Web 实际 adapter 只有 Pi |
| 选模型/通道 | 模型合并展示、逐通道选择、收藏、备注、默认能力与 effort | 能力来自 MMS 配置及 Pi，不靠名字杜撰 |
| 会话中切换模型 | 同路由原生 set_model；跨通道复制本会话 native history 到新私有 runtime，再验证并切换 | 本轮执行/等待确认时先停止或完成；跨 harness 材料包另做 |
| 简单配置 | 通道接入、地址/Key 编辑、模型拉取、连接测试、模型可见性、默认 effort、保存差异 | 高级 Config Web 保留；默认 effort 管理依赖已批准 Registry，独立配置差异见阶段 0；写入由真人确认 |
| 阅读长对话 | Markdown/GFM、工具分组、thinking、hover 复制、提问导航、回到最新、逐轮/全部过程折叠 | 只展示 harness 实际发出的内容，不生成假的 thinking、Todo 或子任务 |
| 查看状态 | thinking/工具/运行/等待/异常/完成；完成高亮与浏览器阅读状态 | CLI/Glint 外部会话尚未全量导入并控制 |
| 添加文件 | 原路径引用、工作目录 @ 搜索、本地图片缩略图、无原路径截图保存 | 引用不是备份；原文件移动后失效；拖入浏览器不保证能取得绝对路径 |
| Skills 与参数 | 当前 workspace 的 Skills 发现/选择、命令提示、规划/执行、queue、compact、统计等 | 原生终端 UI 的所有扩展不一定可直接映射到 Web |
| 会话管理 | 搜索、重命名、归档、导出、基于 native history 分支 | 对话分支不等于文件 checkpoint/undo |
| 成果 | Markdown/文本、CSV、图片、静态 HTML，成果版本比较、原文/图片选区修改 | v4.1 增量；PDF/Office、文件回滚尚未提供 |
| 分享做法 | 任务模板草稿导入/导出 | 不是完整的插件/依赖/模型账号安装包 |

本地文件方案曾走过“大文件上传”方向，已经按用户纠正撤回。JSON 等文件已经在本机，应把原路径交给 Pi 按需读取。不要重新加一个强制上传、复制或拆分数据集的流程。剪贴板截图没有源路径，可以保存副本；预览读取预算和模型输入预算仍要各自管理。

## 代码结构与责任

```text
mms web / mmf web / mms-web
  → mms_web.__main__：本机 HTTP 服务与启动入口
  → React client：任务、阅读、模型选择、设置
  → CatalogService：既有 MMS 配置/Registry 的受控读取与模型解析
  → SessionService：Web 会话身份、事件、恢复、RPC 操作
  → launch_bridge / launch_worker：原 MMS launch_cli
  → 每会话独立 runtime → Pi RPC → 所选模型通道
```

- `apps/mms-web/src/App.tsx`：应用状态、会话读取、导航、设置与动作。
- `Transcript.tsx` / `ToolEvent.tsx` / `components.tsx`：按用户轮次组织过程与最终回答。自动收起仅控制呈现，不删事件。审批和错误不可被一个总折叠吞掉。
- `TaskSettings.tsx` / `ModelExplorer.tsx` / `LaunchOptions.tsx`：新会话和既有会话的模型、通道、effort；共享选择组件。
- `SettingsPage.tsx` / `ChannelModels.tsx` / `ConnectionDialog.tsx`：常用配置入口。后续增加设置前，先判断是否属于当前模型/本次任务/全局偏好。
- `mms_web/catalog.py` / `catalog_worker.py`：解析 MMS 模型与创建私有快照。Web 不能另造一份与 MMS 相冲突的路由真值。
- `model_switch.py`：原生切换、候选 runtime、上下文延续、实际状态校验。不要把更新标题或下拉选项当作切换成功。
- `sessions.py` / `session_actions.py` / `drivers/pi_rpc.py`：生命周期、原生事件、队列、交互请求、操作幂等。运行状态与完成/未读提示分开。
- `runtime.py`：私有配置快照、0600 敏感文件、保护源配置根目录。
- `files.py` / `artifact_history.py` / `artifact_preview.py`：显式文件引用、成果版本与安全预览。文件是用户工作内容，不是配置隔离目录的附属物。
- `extensions/web-controls.ts`：当前 Web 与 Pi 之间的可控扩展能力。
- `scripts/build_mms_web_release.py` / `mms_web_static`：可复现前端打包与分发；`build.json` 记录源码及资产 hash。

MMS 模型数据合同继续由 `docs/MODEL_CONFIG_CONTRACT.md` 管理。Router、Lineup、Profile、Policy 各有归属；不要为了新 UI 改协议优先级、账号 fallback 或 cache 敏感路径。配置隔离保护账号/运行状态，不是操作系统文件 sandbox。

## 已调研内容与可借鉴之处

这部分来自 2026-09-08 至 09 的官方文档、公开源码和本机源码检查，不代表完整使用或性能对比。

| 参考 | 借鉴点 | 在 MMF 的落点 |
|---|---|---|
| [Kimi CLI / Web](https://github.com/MoonshotAI/kimi-cli) | prompt toolbar、工具组、长对话提问导航、结构化问题、会话阅读 | 已借鉴阅读交互；继续补真实 Todo/子任务来源、快捷键与稳定状态 |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | Cordis plugins、上下文注入轨迹、Creator/Customize、插件设置与 inventory | 先做能力来源与实际加载清单，再评估受限可视扩展；Cordis 插件不能直接装进 Pi |
| Glint 本地源码 | pane/session 身份、hooks 状态、完成高亮、主题色；Web Remote 的 PTY snapshot/seq/输入 | 保留明确 owner 与 capability；PTY 镜像不等于 rich chat；不要根据标题/cwd猜会话身份 |
| Runtimia 本地源码 | 引导 setup、可解释 timeline、Skills 来源与同名冲突预览 | 逐步加入引导与能力管理，避免搬入团队看板和企业权限复杂度 |
| [OpenCode](https://opencode.ai/docs/) | Plan/Build、分享、undo/redo、HTTP/SSE server | 参考成果比较与显式尝试另一方案；实际文件回滚需独立实现 |
| [Codex App Server](https://learn.chatgpt.com/docs/app-server) | thread/turn/item、审批、恢复/分支、原生工具事件 | 建议第一个新增 adapter 的候选，先只读协议 spike |
| [Claude Code](https://code.claude.com/docs/en/checkpointing) | 对话/代码 checkpoint、SDK 结构化消息与 plugins | 分清对话历史和文件恢复；不能把 Bash 改动都算进文件checkpoint |
| [MiMo Code](https://github.com/XiaomiMiMo/MiMo-Code) | 项目记忆、checkpoint、预算下重建上下文 | 它基于 OpenCode；Pi compact/extension 是实现入口，不代表功能已自带 |
| [ZCode](https://zcode.z.ai/en/docs/agents) | 可见浏览器操作、导入 Skills | 先让成果可读，再增加可见浏览器验证。没有证实其具体底层，不把它归为Pi |
| [desktop-cc-gui](https://github.com/zhukunpenglinyutong/desktop-cc-gui) | 多 CLI desktop 接入与 GitHub 安装分发 | 证明直接下载 desktop 可行；Web 先验证产品，桌面壳按真实安装摩擦决定 |

详细原始判断保留在 [Harness 方向](HARNESS-DIRECTION.md)、[扩展方向](EXTENSION-DIRECTION.md)、[四项能力路线](IMPLEMENTATION-ROADMAP.md)。这些历史文档中“尚无会话内换模型”已由 v4 更新；阅读时以本表为准。

### Pi 能力与扩展不是无成本可用

Pi 已提供 agent loop、工具、模型切换、native session、compaction、RPC 和 extension UI，所以现在开发比从头实现 harness 简单。Web 仍需处理生命周期、取消/恢复、消息队列、权限问题、数据落盘及 UI 映射。原生终端扩展可以自绘界面，浏览器不能直接运行这套终端 UI。

DeepSeek 的 Customize 是开发/挂载能力的过程，不是 thinking 开关。应记录 `available / selected / loaded / invoked / failed`，来自哪个 Skill/plugin、作用于本会话还是全局。没有 runtime 事件就显示未知，不能把模型说“我已加载”当作系统证据。

Codex App 的 plugin 也不能直接当 Pi plugin 导入。要分别检查客户端/服务器 API、认证、连接器权限、版本与支持的调用路径；通过 MMF 的模型 API Key 不等于拥有 ChatGPT 账号连接器能力。

## 下一阶段建议顺序

### 0. 新用户入口的剩余收口

v4.0.1 已发布独立 Web 默认 effort：连接保存与模型管理复用 Registry writer，支持连续修改和重启后生效；旧独立配置在明确保存时导入全部通道。源码、测试、安装与发布状态以原 task 的本轮回归记录为准。真实 MMF 根目录不会自动迁移。后续主增量为成果预览与修改。

### 1. 把成果做成可直接使用的东西

这是优先级最高的增量。用户完成任务后最关心文件能否打开、哪里改了、如何提出下一次修改。

先扩展 Markdown、文本、图片、CSV、独立 HTML；记录真实路径、内容 hash、文件是否已变化，支持对选中段落或区域提修改。收集 write/edit 与命令生成的实际文件，不只匹配工具名。HTML 采用受限预览，不允许预览内容调用 MMS 本地 API。PDF/Office 在确认预览依赖与用户任务后再加。

验收：新用户生成实际成果 → 打开 → 选中部分要求修改 → 查看新版本/差异；文件变化或删除提示清楚；长过程不会挤掉结果。不要先做漂亮空卡片。

v4.1.0 已发布实现范围（PR115 / 90bfcd2a）：
- 以工具实际完成事件记录文本、Markdown、CSV、HTML和图片成果；命令前后观察工作目录变化，并明确标注来源为观察到的文件变化。
- 只为成果保存有容量上限的本机版本，记录内容hash；不复制整份工作目录。预览可分辨当前文件、已变化、已删除；比较已记录版本。
- 选中文本或图片区域后加入当前会话草稿，用户发送才执行；发送时校验文件hash，避免误用过期选段。
- HTML采用禁止脚本、外部资源、表单和导航的静态预览；PDF/Office和文件回滚暂沿原后续计划。
- 验证真实Pi生成→打开→选段修改→新版本差异、命令生成文件、恢复后的版本、变化/删除、HTML本地API与网络隔离。


### 2. 让上下文与能力可检查

做一个轻量「本次使用」清单，呈现工作目录、显式文件、Skills、项目资料、实际注入/工具执行来源。项目资料要有来源、时间、用户确认、编辑和删除；停用后不再注入；切换项目不串资料。先做用户可管理的内容，再考虑自动长期记忆。

Runtimia 的 Skills 来源/冲突预览适合此处。不要把它做成必须填写大量参数的设置后台。

v4.2.0 候选已实现，验证中：用户主动保存项目资料，可编辑、停用和删除，按项目分区；新消息读取当前已启用版本，记录真实来源与发送状态。停用/删除只阻止后续再次加入，不承诺清除历史上下文。「本次使用」展示 Web 明确加入请求的资料、Skills、文件引用、附件和成果选段；缺少原生加载证据时不标为已加载。不做自动长期记忆，不写全局 MMS 配置。


### 3. 把成功做法分享出去

将当前任务模板升级为：目标、示例输入/成果、Skills 需求、模型能力要求、必要变量。导入先变为可修改草稿，缺少能力时清楚提示；发送才开始实际执行。预览并移除 Key、环境变量、私有历史、原机器绝对路径。

分享“工作配方”的意义是复用一次成功的方法，不是让别人导入自己的账号配置。界面继续使用更易懂的「任务模板」。

### 4. 最后扩大 harness 覆盖

先定义最小公共 driver contract，再选一个 adapter 验证，不一次接齐。

| Adapter | 工作量判断 | 首轮需要验证 |
|---|---|---|
| Pi | 已有，继续拆出耦合 | model/control、事件、恢复与失败回滚都保留 |
| Codex | 中等偏上，优先评估 | stdio App Server，thread/turn/item、审批/提问、resume/fork、模型、sandbox、账号路径 |
| OpenCode | 中等，成熟 server 接口可借鉴 | HTTP/SSE、权限请求、session/message、文件、取消、版本兼容 |
| Claude | 中等偏上 | SDK 流式事件、canUseTool、resume、permission模式、插件；用户明确授权后才启动实际 Claude 验证 |

公共模型应显式携带 owner、harness、native session ID、workspace、model/provider/channel、capabilities。没有该能力的 adapter 不显示可点击假按钮。不要仅靠 shell stdout 文本解析来推断权限和完成。

跨 harness 继续任务需要“可检查材料包”：目标、约束、已完成/未完成、文件与版本、下一步、来源会话。新的 harness 创建自己的 native session，用户知道迁移了什么；不能承诺无损迁移私有 thinking 或所有工具状态。

“MMF 启动完整接入”必须逐项覆盖 harness、账号模式、模型参数、skills/hooks、特殊交互和恢复。当前 Web/Pi 可用不等于所有 Glint/mmf CLI 会话已能无缝接管。

## 质量与发布方式

每个增量都做一个真实任务闭环，并记录源码、实际服务、浏览器正常入口三者的对应关系。源码通过和 build 成功不等于用户已用上新版。

当前测试入口：

```bash
python3 -m pytest tests/test_mms_web_*.py -q
python3 scripts/regression_fresh_user_gate.py
node --test apps/mms-web/tests/markdown-reading.test.mjs
python3 scripts/build_mms_web_release.py
```

Web 集成测试用真实 Pi 进程和本机测试 provider，验证请求 model、Authorization、native history、effort；避免消耗用户真实额度。Pi 未安装时部分测试会 skip，发布验收必须另记录实际有 Pi 的结果。浏览器验收用任务独立空间，覆盖长对话、hover、键盘/触屏、失败反馈、刷新恢复和真实发送。

新版本除了源码，还需检查干净 Git archive 是否带 TypeScript配置、lockfile、Python package、extension和静态包；用隔离 HOME 安装后从已安装路径请求一次真实测试 provider。version/tag/Release/PR/本机运行状态分别记录，禁止把其中一个当成其他几个已经完成。

## 推广建议与护城河判断

多模型、Web、Skills、会话管理在开源生态中都已经存在。MMF 的积累值得继续做，但不能诚实地宣称“网上独有”或“别人复制不了”。长期优势取决于通道兼容的可靠性、可解释的配置、稳定恢复与真实任务模板；更关键的是别人第一次使用时能否明显少走弯路。

先找 5 位目标用户：2 位产品/运营、2 位开发、1 位当前多模型用户。准备一个不依赖私有代码的 60–90 秒演示和三个任务：整理一份本地资料、修改一个小项目、换模型继续同一任务。让他们自己安装配置，记录在哪一步停住、是否理解文件位置、模型通道、成本和结果。先修这些阻塞，再扩平台宣传。

GitHub Release 作为唯一下载入口，README 明确“本地服务/自己的 Key/Pi 首版/不是全 harness”。可准备中英文短介绍、安装视频、可复用模板和 issue 反馈模板。推广执行可包括写文案、录制演示脚本、制作截图、整理FAQ；公开发帖、给别人发消息需用户明确授权。不要用没有证据的对比宣传代替产品验收。

## 后续 Agent 必须保留的约束

1. 工具感、阅读顺手优先，不加后台式导航和卡片墙。
2. MMF 是运行/配置来源；UI 简化不阉割底层，也不绕过原启动链。
3. 本地文件默认原路径引用；截图与本地已有文件分清。
4. 模型/通道/effort 必须以执行进程及实际请求确认；不能只更新 UI。
5. thinking、工具、上下文、Skills、plugin、Todo、子任务各有来源，不能互相冒充。
6. 完成状态、未读结果、进程存活是不同概念。错误和待确认不可被折叠隐藏。
7. 不覆盖用户的配置和工作。实时服务可能正在执行其他任务，重启前必须回读。
8. 沿用原 Stride task 或明确新的下一阶段任务；交接记录不要变成多套手写状态链。
9. 发布后用正常入口回读版本和行为；只在 GitHub 推送不等于发版或本机激活。
