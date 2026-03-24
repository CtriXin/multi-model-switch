# MMS Claude Session 持久化与演进方案

## 背景

当前 `mms` 已经支持：

- `Claude` 多账号隔离
- `Codex` / `Gemini` 官方账号入口
- `官方桥接` 与 provider/gateway 并存

但在 `Claude` 官方 CLI 的真实使用里，还存在两个长期问题：

1. 直接使用全局 `claude` 并切换账号时，`resume`/历史视图可能出现“像丢了一样”的体验
2. 即使历史没有真正丢失，原生 `resume` 列表也通常只显示最后一句或最后一轮，难以判断哪个 session 才是要继续的那个

这两个问题叠在一起，导致单靠官方 `resume` 很难稳定承担“长期工作记忆”的角色。

本方案的目标不是修改官方 `Claude CLI` 本体，而是给 `mms` 启动的 `Claude` 增加一层可控的持久化与索引层：

- 只要通过 `mms` 启动，session 历史就不再受全局账号切换影响
- session 不仅“不丢”，还要“找得到”“看得懂”“能清理”

---

## 问题定义

### 现状问题

当前 `Claude` 相关状态，实际上混合了两种完全不同的语义：

- `账号态`
  - 登录态
  - onboarding/用户偏好
  - 与账号强绑定的本地状态
- `历史态`
  - `history.jsonl`
  - `sessions/`
  - `transcripts/`
  - `file-history/`
  - 与 resume/继续工作相关的持久化记录

如果这两类状态继续耦合在同一套全局目录里，就会出现两个结果：

- 切账号会影响历史视图
- 想做 `mms` 自己的长期记忆治理时，没有清晰边界

### 用户真正需要的能力

对 `mms` 而言，真正需要托底的是：

- 通过 `mms` 启动的 `Claude` session，不因全局 `claude` 切账号而丢
- 用户能在列表里快速判断“这个 session 是不是我要的”
- 老历史可以逐步摘要、归档、清理，而不是无限膨胀

---

## 目标与非目标

## 目标

- 为 `mms` 启动的 `Claude` 提供独立、稳定的 session 历史层
- 把 `账号态` 和 `历史态` 明确拆开
- 增加一层 `mms` 自己的 session summary index
- 为后续 `summarize/archive/prune` 打基础
- 尽量不破坏官方 `Claude CLI` 的原生 `resume` 能力

## 非目标

- 不修改官方 `Claude CLI` 本体
- 不保证“直接运行全局 `claude` 产生的所有历史”都自动纳入 `mms`
- 不在第一阶段就重写 `resume` 交互
- 不直接压缩/篡改官方原始 session 文件作为唯一历史来源

---

## 设计原则

### 1. 账号态与历史态必须解耦

`账号态` 继续按 `account.home_dir` 隔离；`历史态` 由 `mms` 单独托管。

### 2. 先托底“不丢”，再解决“好找”

第一阶段先保证历史不再因为切账号而看起来消失；第二阶段再补 summary/index。

### 3. 原始 session 是运行事实层，不直接拿来做 aggressive compression

原始 `sessions/transcripts/history.jsonl` 仍然保留，用于兼容官方 `resume`。  
摘要、归档、清理要建立在额外的索引层和归档层上，而不是直接改写原始层。

### 4. project-scoped 优先于全局混放

如果 `mms` 自己托管历史，应该按项目隔离，而不是继续把所有仓库混在一份全局目录里。

### 5. 先做最小可用语义，不一次性做成“知识库系统”

阶段一只解决稳定性和可辨识性；高级检索、跨项目聚合、向量索引等能力都放后面。

---

## 总体方案

建议把 `mms` 管理下的 `Claude` 状态分成四层：

### 1. Account State Layer

作用：

- 承载账号相关状态
- 与登录身份绑定
- 保持现有 `account.home_dir` 语义

典型内容：

- `.claude.json`
- `.credentials.json`
- 其他明确与账号身份绑定的配置

### 2. Raw Session Layer

作用：

- 承载原始 `Claude` session/resume 所需文件
- 保证原生 `resume` 仍可工作

建议托管内容：

- `history.jsonl`
- `sessions/`
- `transcripts/`
- `file-history/`
- 视实际行为再评估是否需要 `projects/`

### 3. Session Summary Index Layer

作用：

- 给每个 session 生成可辨认的摘要卡片
- 解决“只看最后一句根本不知道这是不是我要的 session”的问题

建议字段：

- `session_id`
- `project_key`
- `title`
- `task_summary`
- `status`
- `last_active_at`
- `touched_files`
- `keywords`
- `next_step`
- `source_account_id`
- `source_cli`

### 4. Archive & Retention Layer

作用：

- 管理老 session 的体积增长
- 保留长期记忆，但不让活跃层越来越重

建议内容：

- `archives/`
- `summaries/`
- `retention_state.json`

---

## 存储布局建议

不建议把新历史层直接放进仓库根目录；更稳的做法是放到 `mms` 自己的 project-scoped 全局目录：

```text
~/.config/mms/projects/<project-hash>/claude/
  raw/
    history.jsonl
    sessions/
    transcripts/
    file-history/
  summary/
    session_index.json
    sessions/<session-id>.summary.json
  archive/
    raw/
    summary/
  state/
    retention.json
    metadata.json
```

其中：

- `<project-hash>` 由仓库真实路径生成，避免重名
- 必要时可在 `metadata.json` 保存原始项目路径与展示名

这样做的好处：

- 不污染 git 仓库
- 又能按项目稳定隔离
- 为未来增加 `mms session` 子命令保留清晰入口

---

## 启动时的目录映射策略

`mms claude --account <id>` 启动时，目录策略应改为：

### 继续按账号隔离的部分

- `.claude.json`
- `.credentials.json`
- 其他和登录身份直接相关的文件

### 切到 `mms` project-scoped 持久化层的部分

- `history.jsonl`
- `sessions/`
- `transcripts/`
- `file-history/`

### 继续保持系统级真实上下文的部分

- `.local`
- `Library`
- 其他 macOS/CLI 运行时强依赖的系统目录

结果语义：

- 账号切换只影响“你是谁”
- 历史层决定“你之前在这个项目里做过什么”
- 同一个项目下，通过 `mms` 启动的 session 历史持续可见

---

## 为什么不直接全量 symlink 全局 `~/.claude`

表面上把全局 `~/.claude` 整体软链进来最省事，但这条路不能真正解决问题：

- 全局手动切账号依然会干扰 `mms`
- 账号态和历史态继续耦合
- 后面很难做按项目的索引与清理
- 无法稳定解释“为什么这个 session 会出现在这里”

所以，真正的解决方案不是“更多 symlink”，而是“分层与重新托管”。

---

## Session Summary Index 设计

原生 `resume` 最大的问题，不是没有历史，而是**难以判断哪条历史值得继续**。

因此 `mms` 需要额外维护一层更可读的索引：

### 建议展示信息

- 项目名 / 仓库路径
- 一句话主题
- 最近关键决策
- 当前阶段
  - `定位中`
  - `实现中`
  - `待验证`
  - `已收尾`
- 最近涉及的文件
- 最后活跃时间
- 账号来源
- 可选标签

### 可能的生成时机

- session 启动时创建初始 metadata
- 每次 `mms` 退出子进程后做轻量补写
- 或者在专门的 `mms session summarize` 命令里批处理

### 为什么要额外一层 index

因为官方原始文件是“运行记录”，不是“面向检索的工作摘要”。  
这层能力如果没有，哪怕历史不丢，用户仍然会陷入“每次都得点进去看”的低效循环。

---

## summarize / archive / prune 的演进方向

这是后续第二阶段和第三阶段的关键能力。

### 原则

- 不直接把原始 session 压缩成摘要后覆盖原文件
- 先生成摘要，再归档，再删除老原始记录
- 删除动作必须依赖“已有摘要/已有归档”

### 建议命令形态

```bash
mms session status claude
mms session summarize claude --recent 7d
mms session archive claude --older-than 30d
mms session prune claude --older-than 90d
```

### 典型流程

1. 最近活跃的 session 保留在 `raw/`
2. 定期生成 summary index
3. 超过阈值的旧 session 移到 `archive/raw/`
4. 再过更长时间，只保留 summary，删除 archive 里的原始 transcript

### 可支持的清理维度

- 按时间
- 按数量
- 按目录总大小
- 按“是否已有摘要”

### 不建议的做法

- 直接改写 `history.jsonl`
- 直接删 `sessions/` 而不先保留摘要
- 把“摘要层”当成“原生 resume 的直接替代”

---

## 分阶段落地建议

## Phase 1: Persistence

目标：

- 先解决“通过 `mms` 启动的 `Claude` session 不丢”

范围：

- 引入 project-scoped raw session storage
- 调整 launcher 的 `.claude` 目录映射
- 保持账号态继续隔离

交付结果：

- 全局切账号不再影响 `mms` 的项目历史

## Phase 2: Discoverability

目标：

- 解决“session 列表看不懂”

范围：

- 为 session 生成 metadata
- 提供 `mms session ls/status` 的最小读接口

交付结果：

- 用户不必每次都靠官方 `resume` 猜 session

## Phase 3: Retention

目标：

- 控制体积增长

范围：

- `summarize`
- `archive`
- `prune`
- retention policy

交付结果：

- 历史既可保留，也能长期治理

## Phase 4: Advanced Layer

可选增强：

- 更强的全文检索
- 跨项目聚合视图
- 结合 `mms chat/discuss` 的统一 session 浏览
- 把 `Codex` / `Gemini` 纳入同一套 session metadata 体系

---

## 风险与注意事项

### 1. 与官方 `Claude CLI` 内部文件格式耦合

如果上游 CLI 未来更改 `sessions/` 或 `history.jsonl` 的格式，`mms` 需要尽量把自己限制在“托管目录”和“外挂索引层”，不要深度侵入文件语义。

### 2. session 来源归属不完全可逆

如果历史已经在全局目录里混过一段时间，后续无法可靠地自动拆分回不同账号。  
因此迁移策略应是“保留旧历史 + 从新策略开始收敛”，而不是承诺无损回填。

### 3. 体积增长是真问题，但不是第一阶段阻塞点

如果没有 retention 策略，目录一定会持续增长；但这不应阻止第一阶段先解决“不丢”的稳定性问题。

### 4. 需要避免把实现做成另一个“隐藏的默认全局行为”

`mms` 自己托管历史必须是清晰、可解释、可迁移的语义，而不是再隐式依赖另一套难理解的目录。

---

## 建议补充的 TODO

## Urgent + Important

- 为 `mms` 启动的 `Claude` 引入 project-scoped 历史仓，确保全局切账号后 `resume/session` 不丢

## Important + Not Urgent

- 为 `mms` 托管的 `Claude` session 生成 summary index，解决原生 `resume` 列表难以辨认的问题
- 设计 `summarize/archive/prune` 机制，支持近期摘要、老会话归档和长期清理

---

## 结论

这件事的本质，不是“要不要再多做一点 symlink”，而是：

- 把 `Claude` 的 `账号态` 与 `历史态` 正式拆开
- 让 `mms` 对自己启动的 session 历史承担托底责任
- 在“不丢”之上，补齐“好找”和“可治理”

如果这条线不做，后面无论继续叠多少账号、bridge、provider，用户仍然会反复遇到：

- 换账号后不确定历史还在不在
- 列表里看不出哪个 session 才是要的
- 历史越来越多，却没有稳定的摘要与归档手段

因此这不是锦上添花，而是 `mms` 在多账号、多入口场景下的一条必要稳定性演进路线。
