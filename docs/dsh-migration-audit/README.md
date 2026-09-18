# MMS v4 起的 DSH 去留盘点

**现在不做整体迁移，不为定制先 fork DSH，也不一刀切停掉 5.x。保留现有可用 Pilot 和明确需要的能力；新投入优先验证 DSH 能否接走通用执行部分，独有差异优先做 plugin/preset。**

“做自己的产品”和“自己维护每一层实现”不是同一个决定。可以拥有自己的 MMS/Recipe/Fleet/发行包，同时使用上游 DSH runtime。这个方向有接口依据；是否值得替换现有 Pilot，仍缺运行证据。

这次已完成**历史盘点和迁移位置评估**，覆盖 198 个 PR、221 个 merge 节点、702 个唯一 commit，其中 51 个未归入所收集 PR 的引入范围。没有把这些数量冒充 198 项独有功能，也没有把文档比较冒充迁移验证。

## 先消除两份建议的矛盾

我前面倾向转向/定制 DSH，说得过早，应收回那种确定性。Claude 的“先收窄、先验证”有道理，但以下几项不能直接成立：

| 说法 | 本次核对后的判断 |
|---|---|
| 4.x 已具备你要的一切，所以只缺验证 | 有 LAN、持久历史、Recipe 等实现；但需求边界要拆开。后台进程不等于开机自启，记录还在不等于运行任务自动恢复。 |
| 5.x Bot 不在你的需求里，所以应停止 | 不能替你删需求。你明确要求保留并修复 #295；快照中它已经 MERGED。应评估每个 Bot 能力，而非按大版本号决定去留。 |
| DSH preset 只是复制目录，没有校验 | 它有 composition/module 健康检查及启动失败原因。但不等于 Recipe 的接收方模型能力/Skills 要求复核。 |
| DSH 有 schedule/subagent，所以日程和 Fleet 已覆盖 | 有可复用底座，默认产品语义不完全等价；时区周期日程、精确多模型只读 worker 仍需扩展及验证。 |
| 有 plugin 就永远不需要 fork，也不需要维护 | 当前没有证明必须 fork 的缺口；也没有证明所有扩展都不用改上游。Preview API 变化仍会带来插件维护。 |
| fork 能最快得到自己的版本 | 品牌、provider、预设、UI slot 和发行包装已有扩展入口，先 fork 整仓没有必要证据。 |

关键证据：MMS [服务生命周期](https://github.com/CtriXin/multi-model-switch/blob/54d3ff991a2e332563c643cdfc7300c5bb4c52d5/mms_web/service.py) 明确没有 supervisor；DSH [preset](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/preset/agent-presets/README.md)、[schedule](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/schedule.md) 和 [subagent](https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/packages/subagent/tool-subagent/README.md) 各自写明边界。

## 第一类：适合 plugin/preset 的内容

详细入口、缺口和验收条件见 [25 类能力对照](CAPABILITIES.md)。以下是完整候选组；并不主张同时全部开工。

| 候选 | 相关 PR 例子 | 推荐形态 | 判断 |
|---|---|---|---|
| 模型路由/账号明确绑定、registry 管理 | #113/#127/#175/#204/#211/#285 | MMS 配置导出/读取插件；必要时定制 LLM adapter | 复用既有控制面，避免第二份配置数据库 |
| capability/context/effort/vision relay | #114/#185/#213/#216/#233 | adapter metadata + tool/MCP | 迁移解析合同与证据，不复制历史常量 |
| Recipe、变量、要求复核、导出预览 | #143，前序 #111 | UI + schema + 启动校验 + preset | 最优先的小范围验证对象 |
| 项目资料和真实上下文来源记录 | #116/#143 | context/session event/projection/UI | 不把“可能加载”冒充“实际消费” |
| 非 Git 成果快照、版本选段 | #115/#128/#155 | tool event + bounded store + UI | 通用预览用上游，只补快照缺口 |
| Skills/Weber/任务包 | #130/#132/#155/#216/#258 | bundle/preset/MCP | 优先复用内容与工具 |
| 手机/LAN/token/QR 与远程 UX | #149/#181/#186/#283/#317/#329 | 自有 Web composition + Host/UI plugin | DSH 标准 Web 默认 loopback，需验证完整认证链 |
| 旧 Pi 历史/失败恢复草稿 | #149/#159；候选 #341/#342 | import/read-only adapter + recovery UI | 不承诺跨格式无损 native resume |
| 明确仍需的交互差异 | #174/#288/#304/#311/#320/#331 | 已声明 UI slot / 替换 UI package | 原生体验先用，差异逐项补 |
| BTW、队列额外语义 | #221/#258/#259/#281/#294 | Host/tool/UI plugin | 通用 queue/steer 尽量复用 |
| 项目定位、拖拽目录、主机目录树 | #128/#132/#182/#307/#333 | workspace route + UI | 保留移动端及路径安全要求 |
| 品牌、中文帮助、同事入门 | #119/#131/#143/#243/#277 | brand/help/profile 包 | 无须因此 fork core |
| 持久 Bot 与长期记忆/下一轮模型 | #242/#254/#265/#306/#310 | Bot 产品层 plugin | 利用 DSH Session，别再维护另一套 LLM loop |
| 计划批准/步骤模型/协作 | #241/#242/#265/#310/#315 | task/approval/UI plugin | DSH subagent/Team DAG 可复用 |
| 独立时区日程及管理 | #278/#302/#306/#315 | Host scheduler + durable store + UI | 不是一个 preset 就能完成 |
| Fleet 多模型意见 | #295 及关联直接提交 | 精确 route 的 spawn backend + coordinator/UI | 保留指定模型、只读、回收等要求 |
| 执行前重试与结果通知 | #240/#242 | Host plugin/外部投递服务 | 与 LLM retry 分开，避免重复副作用 |
| 低打扰自愿反馈 | 候选 #330 | UI/preferences plugin | 可选，非迁移前置 |

DSH 提供 out-of-tree bundle/profile 安装机制，但“可做插件”不代表把 Python 文件包一下就行；涉及数据模型、事件和 UI 的部分仍需实现。[官方插件打包说明](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish)

## 第二类：建议拥有自己的发行层；暂无必须 fork core 的项目

| 自有部分 | 相关历史 | 为什么应自己拥有 | 是否需要 fork DSH core |
|---|---|---|---|
| 依赖版本、bundle/profile、品牌、默认场景与中文入门 | #119/#131/#132/#143/#243 | 面向自己的使用方式和同事分发 | 没有必要证据 |
| MMS 启动器、账号/环境隔离、服务发现、安装 | #152/#164/#189/#204/#215/#231/#292 | DSH 只是被启动的另一个 harness | 没有必要证据 |
| 安全更新、真实版本、回滚、Stable/Preview 策略 | #137/#195/#198/#266/#299/#313/#315/#327/#338/#339 | 自有组合需要一起验证和发版 | 没有必要证据 |

这里“自己的发行”可以是单独的插件/配置仓库，不等于复制 DSH monorepo。普通 provider 配置、persona、品牌替换、独立 effort UI 都已有可调查的扩展面。

**只有必要需求的 spike 确认没有扩展入口，才为那个具体缺口维护小 patch/fork。** 先记录受影响包、上游接口缺口和退出条件；不预设“所有需求都能插件化”，也不预设“必须魔改核心”。

## 第三类：可以不再迁移、或满足条件后退役的内容

| 内容 | 可以丢掉的范围 | 不能一并丢掉的东西 |
|---|---|---|
| 纯 release stamp、旧生成 bundle、重复 main/dev 合流 | 不搬入新 runtime；历史留档 | 版本真值、可回滚和来源追溯 |
| 已被替代的更新原型 #125、猜测性握手超时 #247、旧发布候选 #245/#253/#255/#261 | 不复活旧候选 | 已被后续实现修好的需求 |
| 原生 OS 文件夹 picker #250/#251 | 旧 WinForms/osascript 与显示/超时补丁；#307 已换树 | 手机浏览主机目录和路径安全 |
| 已退休的全局 skill/hook 强装、token-saver、legacy 默认写根 | 保持退休，不迁移 | 会话技能、真实配置保护 |
| 已被统一 resolver 替代的模型名/窗口常量补丁 | 不复制早期 K3 等互相覆盖的常量 | capability provenance、人工覆盖与消费者一致性 |
| 通用聊天 UI、流式状态、基础模型菜单、附件预览 | **目标 DSH 真实验收通过后**，退出重复实现 | 失败可见、焦点/移动端、真实模型生效等要求 |
| Pi RPC→Pilot 事件翻译、重复 queue/session mirror | **正式不再用 Pi 作为该 Web 执行层后**，退出对应 adapter | 旧历史可读、不中断现有会话、取消/恢复语义 |
| 全套自研 LLM loop/通用子代理 plumbing 的继续扩建 | 新工作优先研究上游能力，避免重复做底层 | 用户需要的 Bot、日程、Fleet 产品层 |
| 旧页面 selector、CSS 补丁和实现绑定测试 | DSH 页面替换后不照抄 | 用户行为用例、mutation 和真实调用链验证 |

**不能归为抛弃：** 多 CLI MMS launcher、账号隔离、协议/cache 合同、Recipe、用户明确要的 Fleet，以及真实失败案例。这些或留 MMS，或做 plugin，不能只因为“上游也叫 agent”删除。

## PR 与合并历史中容易误读的地方

- **#295 与 #320 均 MERGED。** Fleet 最终 PR 的 first-parent delta 只有收尾文件，主要实现/修复已经沿直接提交落入历史；台账关联 `5707bb07`、`789d45ba` 等，不遗漏。
- **CLOSED 不等于未采用。** #122、#167、#249、#312、#316、#318、#319、#321 有吸收/替代或另线发布记录；逐 PR 表分别说明。#247 则是没有成立证据的候选，属于不同情况。
- **#308 仍按实验处理，未纳入已交付能力。** 本次不改变其状态，不合入。
- **#242 曾落入 dev，#262 又撤销，#274 后 dev 进入 5.x。** 所以 merge commit 出现在 main 祖先中，不证明 main 现在有 Bot。当前 main/dev 的产品边界要看净内容。
- **#278 标题里的“后端，不要合”是旧说明。** 实际合并内容已包含 #302/#306。不能拿历史标题代替 merge delta。
- **#313/#315/#335/#336 等含真实修复。** 不能因为写了 release 就全归为版本号改动。
- **快照 OPEN 为 #330/#337/#340/#341/#342。** 恢复功能 #341/#342 是候选，报告不把后续其他 agent 可能推进的状态写成此次已验证。

## 哪条接法最值得先验证

三条路线的改动量不同，不能混称“接入 DSH”：

1. **MMS 启动 DSH 自己的 CLI/Web。** MMS 管账号、隔离和版本，DSH 管自己的会话/UI。这最容易验证“我们的真实通道能否正确跑 DSH”，但不会自动继承 Pilot 所有界面与历史。
2. **保留 Pilot UI，DSH 作为第二个驱动。** SDK/ACP 可以提供连接入口，但 stream、approval、model、effort、steer、BTW、resume、artifact、worker 必须逐一映射。#308 的经验只证明已有 adapter 思路，不能证明 DSH 无缝可接。
3. **自有 DSH composition，逐步替代通用 Pilot 部分。** 长期可能减少重复维护；要承担插件、数据和用户路径迁移。现在还没有运行证据决定走到这一步。

建议先只验证路线 1，再用 **Recipe** 验证路线 3 的一个真实增量，同时用 **#295 Fleet 的负向用例**检查能力边界。这样能分别回答“通道可用吗”“独有场景能加吗”“权限/模型语义能守住吗”。失败时保留现有 Pilot；通过才讨论迁移下一块。

不把这份建议当已启动 spike。此次没有安装 DSH、没有用真实 Key 跑模型、没有迁移配置或关掉现有功能。

## 完整台账与审阅深度

| 文件 | 内容 |
|---|---|
| [交互筛选页](index.html) | 按 PR/merge/直接提交、分类、状态、能力或路径搜索 |
| [能力对照](CAPABILITIES.md) | 25 类能力的当前语义、DSH 接口、差异和验收条件 |
| [逐 PR 表](PR-INVENTORY.md) / [CSV](PR-INVENTORY.csv) | 全 198 条，各有独立判断，完整文件列表在 CSV/JSON |
| [逐 merge 表](MERGE-INVENTORY.md) / [CSV](MERGE-INVENTORY.csv) | 全 221 节点、parents、真实 first-parent 文件差异 |
| [独立提交表](DIRECT-COMMITS.md) / [CSV](DIRECT-COMMITS.csv) | 51 条未归入所收集 PR 引入范围的提交，单独分类 |
| [全部 commit CSV](ALL-COMMITS.csv) | 702 个唯一提交与 PR 引入范围关联 |
| [机器可读总表](inventory.json) / [覆盖检查](coverage.json) | 固定快照、去重计数、分类和限制 |
| [逐 PR 原始判断](classification.tsv) / [生成脚本](build_report.py) | 人工判断与可重建视图 |

**实际做了什么**：枚举 GitHub 全状态 PR，核对标题/说明/变更路径；提取已合并 PR 的实际 merge delta，而非只信 PR body；读取关键行为的 diff/现有源码、关闭原因和 DSH 官方文档及关键接口源码；逐 PR 分类；列出全部 merge 父提交及净差异；单独评估 51 条遗漏于 PR 范围的提交。

**没有做什么**：没有逐行审计全部 702 个 commit，没有重演每一次冲突解决，没有运行 DSH/迁移原型，也没有重跑整个 MMS 产品回归。因此本报告不签发“全部 merge 无误”“所有功能 ready”“迁移无损”的结论。每一条都有记录，不等于每一行代码都做过运行验证。

原始 PR bodies、GitHub patches 和 DSH source 只保留于本次任务的 ignored evidence 目录 `.stride-output/dsh-audit/`。输出表只包含公开代码元数据与分析，不复制真实配置或凭据。

## 固定基线与复现边界

- 任务 `8b76aee15b3c41f7`，attempt `20feb08e14554d51`；独立 worktree，不覆盖原任务其他 active attempt。
- 快照时间：2026-09-18 11:47:44 +08；PR 至 #342：176 MERGED、17 CLOSED、5 OPEN。
- v4 初始实现前：`0d342c7f99ded8939e436edb489e114d9d40db76`；v4.0.0：`e38e2d7cdb6bad4b126d32632a7cc936a1db5523`。范围包括 #111 的初始实现，不从 tag 后才开始算。
- main：`54d3ff991a2e332563c643cdfc7300c5bb4c52d5`（4.23.5）；dev：`afd5575e3971c782d3d4f1f6dbce547cc4778ae8`（5.1.8）。
- DSH：`ddefc45fbc7f8e46dd73185e68295696d1297887`（0.1.6-alpha.2）。接口判断针对这个版本，不能替未来版本担保。
- Git 范围是 main/dev 在 v4 初始前基线之后的并集；排除基线已存在提交并按完整 SHA 去重。PR #111 以前没有 merge SHA 落入此范围的条目。序号缺口是 issue 等，不是漏掉 PR。
- commit 的 `primaryPr` 取包含它的最小 merge 引入范围；这是便于导航的关联，不是作者归属、原创归属或 runtime 验证证明。
