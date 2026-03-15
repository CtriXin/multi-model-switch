# TODO

## Urgent + Important
- [x] `apps/web-v2` 锦囊团升级为完整“角色委员会”：首屏 Hero + 角色矩阵 + 独立 committee 模型池 + 广播/辩论/委员会三种真实运行模式。(source: @user, created: 2026-03-15, completed: 2026-03-15)
- [x] 统一 `apps/web-v2` 输入区基线：`ModelChipBar` / `InputBar` / `Advisors` 底部输入区收口到同一条 `max-w-5xl + px-4` 容器，并对齐 textarea 与发送按钮位置。 (source: @user, created: 2026-03-15, completed: 2026-03-15)
- [x] 修复 `apps/web-v2` 对话页卡片布局：移动端 carousel 切换后不再保留上一张卡片的高度占位；macOS grid 卡片统一固定高度，超长内容改为卡片内滚动。 (source: @user, created: 2026-03-15, completed: 2026-03-15)
- [x] ~~**[P0]** Summarizer + Judge Tier 1/2：chat 模式所有模型回答完成后自动调用 evaluator，输出 共识/分歧/风险/建议行动。Tier 2 检测冲突度高时加入交叉审查。evaluator 从未参与模型中按 tier 降序选。前端加「决策总结」卡片。~~ (completed: 2026-03-15)
- [x] ~~**[P0]** Rollup 环节：Discuss 完成后手动触发，由第三方模型综合所有观点生成唯一可落地行动计划。输出 final_plan/key_rationale/tradeoffs/risks/next_steps。支持用户自选 Rollup 模型（高级）。Discuss 结果页下方按钮 + 智能提示。~~ (completed: 2026-03-15)
- [x] ~~**[P0]** 锦囊团 Phase 1：12 预设角色 + 广播模式 + 立场轴防漂移。~~ (completed: 2026-03-15)
- [x] ~~**[P0]** 锦囊团 Phase 2：委员会模式（系统级汇总）— 广播输出后自动或手动触发结构化收敛结论 + 各立场贡献标注。~~ (source: @user, created: 2026-03-15, completed: 2026-03-15)
- [ ] **[P0]** Context 策略：继续对话时支持三种 context 模式 — ① 中立总结（默认，省 token 且客观）② 仅选中回答 ③ 全量原始回答。前端在输入框上方显示 context chip 可切换，后端拼 prompt 时按 mode 取不同内容。(source: @claude, created: 2026-03-15)
- [ ] 观察新护栏文档执行后的实际效果，补齐容易被绕开的高风险路径 (source: @codex, created: 2026-03-14)
- [x] ~~Provider 配置 + API Key 管理 + 真实 API 接入（keychain/api/provider store/chat/discuss 全链路）~~ (completed: 2026-03-15)
- [x] ~~SettingsView Provider 配置 UI + ModelsView 动态适配~~ (completed: 2026-03-15)
- [x] ~~Discuss depth 参数 (full/panel/quick) 前端实现~~ (completed: 2026-03-15)
- [x] ~~增加独立诊断脚本，验证 provider/account 连通性、模型 chat 可用性和 Claude 路径兼容性~~ (source: @codex, created: 2026-03-14, completed: 2026-03-15)

## Important + Not Urgent
- [ ] 与另一个 agent 同步共享入口文件：`src/router.ts`、`src/components/layout/Sidebar.vue`、`src/views/SettingsView.vue`、`src/views/SetupGuide.vue`，把“角色委员会”入口命名、setup 串联和首屏文案合并到统一体验。(source: @codex, created: 2026-03-15)
- [ ] 锦囊团 Phase 3：自定义角色 + 辩论模式（三轴坐标编辑 + 核心信念 + 绑定模型；多轮反驳补充）。(source: @user, created: 2026-03-15)
- [ ] 锦囊团 Persona 漂移防护增强：每轮强制重注入完整 Persona 定义 + "你的立场不因他人反对而改变"。(source: @user, created: 2026-03-15)
- [ ] 锦囊团 UX 分层：普通用户用预设、高级用户自定义三轴、团队用户保存角色组合（技术/商业/自定义激活子集）。(source: @user, created: 2026-03-15)
- [ ] Judge Tier 3 — Committee / Deep Review：多轮对抗评估，最高可靠性最高成本。等核心闭环验证后再加。(source: @user, created: 2026-03-15)
- [ ] Single-model compatibility：角色分离（Planner/Critic/Judge）、blind self-evaluation、adversarial prompting。作为多模型多样性的替代方案。(source: @user, created: 2026-03-15)
- [ ] 会话持久化、模型搜索筛选、导出对话等前端体验细节 (source: @claude, created: 2026-03-15)
- [ ] 在 `packages/contracts` 固化 session/schema/endpoint 契约，确保 mock 和 real adapter 形状一致 (source: @codex, created: 2026-03-15)
- [ ] 将主启动链路补成更明确的回归清单，后续改动可直接对照验证 (source: @codex, created: 2026-03-14)
- [ ] 评估并设计 `skill` 调用临时会话时的可选 model 能力，避免只能走固定默认模型 (source: @codex, created: 2026-03-14)
- [ ] 评估是否需要给 `codex` 增加 `Anthropic messages` bridge，以承载 `agent_only` 型 provider (source: @codex, created: 2026-03-15)
- [ ] route_learned.json 淘汰策略：加上限（如 200 条）+ LRU 淘汰 + 文件锁防并发写入 (source: @claude, created: 2026-03-15, from: agent-discuss feedback)
- [ ] 智能路由实时状态展示：在 Claude 运行时显示当前 tier (light/medium/heavy) 和实际使用的 model (source: @claude, created: 2026-03-15)

## Urgent + Not Important
- [ ] 为新会话补一份最短启动指引，约束先读 `.ai/plan/current.md` 等文档 (source: @codex, created: 2026-03-15)

## Neither / Deferred
- [ ] **Discuss → Rollup → Final Judge → Output** 全链路：用于高风险场景的四阶段决策流水线。Discuss 辩论 → Rollup 综合 → Judge 审查 → 最终输出。(source: @user, created: 2026-03-15)
- [ ] Gateway model slot 共存模式（用户选模式 vs 自动匹配模式）(source: @claude, created: 2026-03-15)
- [ ] OAuth Plan 用量查询 per-model (source: @claude, created: 2026-03-15)
- [ ] Model Pricing DB 自动更新（从 OpenRouter 拉取）(source: @claude, created: 2026-03-15)
- [ ] 评估是否需要 `mms run --auto-model` 显式命令别名 (source: @codex, created: 2026-03-14)
