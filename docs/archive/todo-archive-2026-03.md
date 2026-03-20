# TODO Archive - 2026-03

## Archived 2026-03-14
- [x] 评估命令/skill 触发的自动模型切换方案，确认适合放在启动前 hook 还是会话内切换 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 落地自动模型路由的阶段计划，覆盖临时会话调用 skill 与可选 model 的接口要求 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 梳理 `mms --export`、runtime 选择、`launch_codex` 之间的边界，避免把自动切换错误设计成纯 shell export (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 用 `agent-discuss` 的 packet discipline 压缩“轻中重任务定义”问题，形成可执行的 auto-routing 约束草案 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 记录轻中重 v0 分层、白名单/黑名单与 guardrail，供后续手动执行实现 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 记录用户提到的 `opus -> codex` 降级用例，作为后续 auto-routing 的最小验收样例 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 起草一份 agent 变更护栏文档，约束高风险改动不得直接扰动主启动链路 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 在 `AGENTS.md` 挂接护栏文档，使后续 agent 改动前先读取约束 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 抽取 MMS 核心稳定面清单，覆盖场景选择、模型选择、runtime/source 决策、bridge、配置与账号隔离 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 将本次“模型选择与实际启动不一致”的事故沉淀为文档中的反例约束 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 为 Claude 增加更强的仓库级行为约束，限制其直接改动主启动链路 (source: @codex, created: 2026-03-14, completed: 2026-03-14)
- [x] 对齐 `agent-rules` 的本地启动入口结构，并补上迭代后询问是否提交的门禁 (source: @codex, created: 2026-03-14, completed: 2026-03-14)

## Archived 2026-03-19
- [x] 修复设置页切换 demo provider 后模型列表需刷新才同步的问题 (source: @codex, created: 2026-03-19, completed: 2026-03-19)
- [x] 排查 `/models` 路由仍请求 4000 端口的根因并修复 (source: @codex, created: 2026-03-19, completed: 2026-03-19)
- [x] 回归验证模型列表加载与 SparkRing provisioning 的端口迁移逻辑 (source: @codex, created: 2026-03-19, completed: 2026-03-19)
- [x] 记录本轮修复涉及的本地 release note 上下文 (source: @codex, created: 2026-03-19, completed: 2026-03-19)

## Archived 2026-03-20
- [x] `apps/web-v2` Provider 多账户账户池：同一 provider 支持多个账户与默认账户，设置页改为按账户配置 key，真实请求失败时在同 provider 可用账户间自动 fallback。 (source: @user, created: 2026-03-16, completed: 2026-03-16)
- [x] `apps/web-v2` 真实 API 体验收口：随机按钮改成“换一组”并支持重复重掷、失败模型按错误类型当天临时隐藏、`<think>` 默认隐藏、聊天支持终止并编辑恢复草稿、锦囊团结论支持 markdown 展开查看。 (source: @user, created: 2026-03-16, completed: 2026-03-16)
- [x] `apps/web-v2` 锦囊团升级为完整“角色委员会”：首屏 Hero + 角色矩阵 + 独立 committee 模型池 + 广播/辩论/委员会三种真实运行模式。 (source: @user, created: 2026-03-15, completed: 2026-03-15)
- [x] 统一 `apps/web-v2` 输入区基线：`ModelChipBar` / `InputBar` / `Advisors` 底部输入区收口到同一条 `max-w-5xl + px-4` 容器，并对齐 textarea 与发送按钮位置。 (source: @user, created: 2026-03-15, completed: 2026-03-15)
- [x] 修复 `apps/web-v2` 对话页卡片布局：移动端 carousel 切换后不再保留上一张卡片的高度占位；macOS grid 卡片统一固定高度，超长内容改为卡片内滚动。 (source: @user, created: 2026-03-15, completed: 2026-03-15)
- [x] **[P0]** Summarizer + Judge Tier 1/2：chat 模式所有模型回答完成后自动调用 evaluator，输出 共识/分歧/风险/建议行动。Tier 2 检测冲突度高时加入交叉审查。evaluator 从未参与模型中按 tier 降序选。前端加「决策总结」卡片。 (completed: 2026-03-15)
- [x] **[P0]** Rollup 环节：Discuss 完成后手动触发，由第三方模型综合所有观点生成唯一可落地行动计划。输出 final_plan/key_rationale/tradeoffs/risks/next_steps。支持用户自选 Rollup 模型（高级）。Discuss 结果页下方按钮 + 智能提示。 (completed: 2026-03-15)
- [x] **[P0]** 锦囊团 Phase 1：12 预设角色 + 广播模式 + 立场轴防漂移。 (completed: 2026-03-15)
- [x] **[P0]** 锦囊团 Phase 2：委员会模式（系统级汇总）— 广播输出后自动或手动触发结构化收敛结论 + 各立场贡献标注。 (source: @user, created: 2026-03-15, completed: 2026-03-15)
- [x] Provider 配置 + API Key 管理 + 真实 API 接入（keychain/api/provider store/chat/discuss 全链路） (completed: 2026-03-15)
- [x] SettingsView Provider 配置 UI + ModelsView 动态适配 (completed: 2026-03-15)
- [x] Discuss depth 参数 (full/panel/quick) 前端实现 (completed: 2026-03-15)
- [x] 增加独立诊断脚本，验证 provider/account 连通性、模型 chat 可用性和 Claude 路径兼容性 (source: @codex, created: 2026-03-14, completed: 2026-03-15)
