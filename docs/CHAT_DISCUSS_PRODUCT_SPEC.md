# Chat + Discuss 产品方案（v1 草案）

## 1. 目标

把当前 `mms chat` / `mms discuss` 从“两个子命令”提升成一组可独立开源分享的交互能力：

- `chat`：多模型并排输出后，支持基于某一列结果继续、重开、改模型、转执行
- `discuss`：多模型收敛后，默认进入执行层，而不是继续陷入长对话
- 全程控制 token 成本与上下文膨胀
- session 可恢复、可清理、可 pin

## 2. 产品定位

这不是普通的 AI chat，也不是传统 agent orchestration。

更准确的定位是两层：

### 2.1 `chat` 的定位

`chat` 是一种 **compare-first branching chat**，进一步说也可以理解成 **role-first comparison surface**：

- 先比较多个模型 / 多个职责视角的答案
- 再从某一个答案分支继续
- 继续时可以改模型集合
- 重点是“选答案继续”，而不是“把所有历史越聊越长”
- 主视图不仅可以是模型列，也可以是 `planner@gpt-5`、`skeptic@claude`、`builder@codex` 这种 role-aware lanes

### 2.2 `discuss` 的定位

`discuss` 是一种 **decision-to-execution CLI workflow**，更进一步可定义为 **state-centric threaded deliberation**：

- 先让多个模型或多个 role 做压缩式讨论
- 再产出一个 canonical final direction
- 默认把 final direction handoff 给执行层
- 重点是“收敛并行动”，不是长期继续聊天
- 它不是 transcript-heavy 的多人群聊，而是有限回合的结构化 deliberation

## 3. 交互主路径

## 3.1 `chat` 主路径

1. 选择 provider
2. 选择 2-5 个 models
3. 输入任务
4. 并排流式输出结果
5. 进入结果后操作栏

建议键位：

- `← / →`：切换当前焦点列
- `Enter`：基于当前列继续
- `C`：基于当前列继续，并修改模型集合
- `E`：把当前列结果交给执行层
- `S`：保存 / pin 当前 session
- `R`：重新会话（保留任务，不带旧结果上下文）
- `Q` / `Esc`：退出到普通 CLI

### `Enter` 语义

`Enter` 不是“延续全部聊天历史”，而是：

- 选中当前列结果
- 生成一个压缩后的 `result brief`
- 让用户输入新的补充问题
- 用 `task + branch brief + 新补充` 继续下一轮

### `C` 语义

`C` 是 continue + change models：

- 基于当前选中列创建下一轮上下文
- 再进入模型操作菜单
- 允许：
  - 保持当前模型
  - 增加模型
  - 移除模型
  - 全量重选模型
  - 可选切换到 discuss

### `R` 语义

`R` 表示：

- 保留当前任务文本
- 清空上轮结果上下文
- 重新选择模型并重跑
- 用于“问题本身没变，但对当前结果不满意”的场景

## 3.2 `discuss` 主路径

1. 选择 provider
2. 选择 1-5 个 models
3. 输入任务
4. Phase 1 摘要发散
5. 可选 Phase 2 交叉审查
6. Phase 3 最终综合
7. 进入收尾动作栏

建议键位：

- `E`：进入执行
- `V`：查看各模型摘要 / review
- `C`：把 final 或某个摘要转成 chat 上下文
- `S`：保存 / pin session
- `R`：基于同一任务重新讨论
- `Q` / `Esc`：退出

默认主路径应该是 `E`，不是继续 discuss。

## 4. 上下文控制原则

## 4.1 绝不 transcript-first

继续时不能直接把：

- 原任务全文
- 所有模型全文
- 所有历史轮次全文

原样拼接进下一轮。

这会迅速造成：

- token 膨胀
- 模型注意力稀释
- 交互变慢
- 成本不可控

## 4.2 使用分层 state-first continuation

建议把上下文拆成 6 层，而不是混成一个大 `brief`：

- `task`：目标、约束、成功标准、当前模式
- `branch`：当前选中结果或当前工作分支的关键状态
- `evidence`：必要的依据、代码片段、日志、摘要引用
- `decision_log`：已经作出的选择及其理由
- `ruled_out`：已经否掉、除非有新 evidence 否则不要重开的方向
- `archive`：原始 transcript、旧轮次、raw outputs、调试信息

核心原则：

- 进入 prompt 的应该是“当前决策面”
- 留在 session 的应该是“可追溯材料”
- session 可以丰富，但 prompt 必须克制

## 4.3 默认进入 prompt 的内容

下一轮默认只带：

- `goal`：当前任务目标
- `task brief`：用户问题短版
- `selected result brief`：当前选中列摘要
- `branch summary`：这条分支已有的关键结论
- `delta prompt`：用户新补充
- `selected assets`：必要时附带的极少量结构化材料
- `decision_log` 中最近仍影响当前选择的决策
- `ruled_out` 中仍然有效的禁止重开项

默认不带：

- 未选中的其他列全文
- 旧轮次完整 transcript
- 原始流式输出
- 仅用于审计的 archive 内容

## 4.4 `selected result brief` 的建议结构

建议控制在一个小 envelope 内，只保留：

- answer gist
- assumptions
- decisions
- open questions
- next step
- evidence refs

不要默认保留完整推理长文。

## 4.5 token governor

内部应有一个 context budget manager（不一定暴露给用户），负责：

- 估算本轮 prompt 预算
- 给 `task` / `branch` / `active disagreements` / `evidence` 分配固定预算
- 超预算时优先压缩 `evidence` 和旧 `branch` 信息
- 在 `full / compact / minimal` 三档之间自动降级

这样做的目标不是“少带上下文”，而是“只带当前这轮真正需要的层”。

## 5. Session 生命周期

## 5.1 默认分层

建议三层：

### `ephemeral`

- 默认新 session 先放这里
- 自动清理
- 适合临时比较和试跑

### `recent`

- 用户继续过、或显式保存过的 session 升级到这里
- 保留完整 state + brief
- 适合短期恢复与二次使用

### `pinned`

- 用户显式 pin / 命名
- 不自动删除
- 适合开源示例、最佳实践、长期保留讨论

## 5.2 建议清理规则

- `ephemeral`: 72 小时自动清理
- `recent`: 保留最近 30 个完整 session
- 超出上限时：
  - 保留最近 10 个完整 session
  - 其余只保留 index / brief
- `pinned`: 永不自动删除

## 5.3 session 应保存哪些内容

建议最少保存：

- session id
- created_at / updated_at
- mode: `chat` or `discuss`
- provider
- selected models
- original task
- branch list
- active branch id
- latest final / latest selected brief
- lifecycle status: `ephemeral|recent|pinned`

chat 侧每轮可保存：

- model outputs（可截断）
- selected column
- generated branch brief

`discuss` 侧每轮可保存：

- summaries
- reviews
- final
- execution handoff brief

## 6. Branch 设计

## 6.1 一个 active branch，多条 saved branches

建议不要把多个结果同时放进主上下文。

规则：

- 当前只允许 1 条 active branch
- 其他分支作为 saved candidates 保留
- 只有用户 `Enter` / `S` 之后，当前列才升级为 branch head

## 6.2 copy-on-write

branch 不复制整份 session，只记录：

- `parent_branch_id`
- `selected_result_digest`
- `delta_prompt`
- `delta_models`
- `branch_summary`

这样节省存储，也更适合控制上下文。

## 6.3 role-aware lanes

如果引入 role，不应把它理解为“人格扮演”，而应理解为 `operating stance`：

- `planner`：偏规划、结构、分解
- `skeptic`：偏质疑、风险、反证
- `builder`：偏落地、执行、实现路径
- 可后续扩展 `reviewer` / `editor` / `executor`

role 的职责是改变“责任视角”和“输出 contract”，不是改变文风。

建议统一输出骨架：

- `claim`
- `pushback`
- `evidence_refs`
- `next_step`

这样用户比较的是思考差异，而不是写作风格差异。

## 6.4 role 是自动优先，手动可覆盖

推荐策略：

- 默认由系统自动分配 role
- 高级用户可以显式指定 role 组合
- 不要求用户每次都手工配置，避免认知负担

默认自动策略：

- `chat`（2 lanes）: `planner + skeptic`
- `chat`（3 lanes）: `planner + skeptic + builder`
- `discuss`: `2 roles + 1 synthesizer`

模型匹配建议：

- 长于结构规划的模型优先匹配 `planner`
- 长于审查与找风险的模型优先匹配 `skeptic`
- 长于执行与代码落地的模型优先匹配 `builder`
- `synthesizer` 应由当前最稳的综合模型担任

如果没有足够模型差异，也可以同一模型承担不同 role，但需要严格固定输出 schema，防止 role theater。

## 6.5 单一 canonical state writer

多 role / 多 agent 可以同时参与讨论，但不能同时写回主状态。

必须规定：

- 普通 role 只产出结构化 reply
- 只有 `synthesizer` 能写：
  - `current_direction`
  - `decision_log`
  - `ruled_out`
  - `next_step`

这样可以避免 state 污染，也更利于可续聊。

## 7. 执行层原则

## 7.1 `discuss` 默认导向执行

`discuss` 的 default success path：

- 输出 `final direction`
- 生成一份 execution handoff brief
- 交给目标 CLI（如 Claude / Codex）或本地执行流程

## 7.2 执行层不能被 UI 吞掉

后操作栏是快捷入口，不是强制入口。

必须保证：

- 可以直接退出回普通 CLI
- 用户能看到即将交给执行层的最小上下文
- handoff 是可见、可控、可取消的

## 8. 设计原则与方法论

### 8.1 借鉴 a2a，但不做人格秀

可以借鉴 a2a 的地方是“职责分离”，不是人格化表演。

更推荐的是：

- 使用 role / stance，而不是夸张 persona
- 强调不同 role 施加不同思考压力
- 让差异体现在 `claim / pushback / evidence / next_step` 上
- 不让差异只停留在语气和文风上

### 8.2 fan-out -> structured replies -> fan-in synthesis

多 agent 最合理的模式不是自由互聊，而是：

- fan-out：多个 role / model 并发生成结构化回复
- structured replies：每个 lane 输出统一 schema
- fan-in synthesis：一个 synthesizer 产出 canonical synthesis

下一轮默认只继承 canonical synthesis 与关键分歧，而不是回放全量 transcript。

### 8.3 增加 `decision_log` 与 `ruled_out`

这两个层能显著减少 token 浪费：

- `decision_log`：记录已经选了什么、为什么选
- `ruled_out`：记录哪些方向已经否掉，不应反复重开

很多系统的问题不是“记不住”，而是“反复重新讨论已经否掉的方向”。

### 8.4 可重开的是 claim，不一定是整轮

一个更少见但很有用的理念是：

- 支持 `reopen claim-X`
- 不必整轮重开
- 只重开一条关键分歧

这样能更大幅度控制 token 成本，也更适合 CLI 交互。

## 9. 开源分享价值

如果做对，这个功能不是普通“多模型对比”而已。

它更像一个新的 CLI 交互范式：

- compare-first
- branch-driven
- execution-biased
- stateful but compact
- role-aware but schema-driven

这几个点组合起来，确实有机会形成可单独开源分享的特色能力，因为它同时解决了：

- 多模型比较后如何继续
- discuss 后如何进入执行
- session 如何保留又不爆 context
- CLI 交互如何比单轮 prompt 更顺滑
- 多 role / 多 agent 如何参与但不污染主状态

## 10. 推荐实现顺序

### v1

- `chat` 后操作栏
- 键位：`←/→` `Enter` `C` `E` `S` `R` `Q`
- `selected result brief`
- `discuss` 的 execution handoff
- session 基础结构与 TTL 清理
- `task / branch / evidence / archive` 的最小分层

### v2

- role-aware lanes
- `decision_log` / `ruled_out`
- branch 浏览与切换
- 更强的模型集合编辑
- `discuss -> chat` 的回退分支
- pinned session 管理
- handoff 预览与模板化执行入口

### v3

- `reopen claim-X`
- synthesizer / canonical state writer 机制
- replay / shareable demo session
- 对外 README / product narrative / demo gif
- 开源展示样例

## 11. 当前 Todo

- 明确更垂的产品分类名称
- 继续研究同类或近似产品的交互模式
- 决定 `selected result brief` 的具体字段结构
- 决定 session 存储目录与文件格式
- 决定 `E` 的 handoff 目标和交互草案
- 决定默认 role 分配规则与手动覆盖方式
