# TODO

## Urgent + Important
- [x] 修复 `design-play/apps/web-v2` 的 `MultiLife` 开始调查与流式叙事体验：补齐案件详情页 `handleBegin` 链路，保留段落换行，并拦截流式过程中的 `<BRIEF>` / `## 结论` 等内部草稿内容。 (source: @user, created: 2026-03-20, completed: 2026-03-20)
- [x] 同步 `apps/web-v2` 的 `MultiLife` 更新：从 `daily-challenge` worktree 合并新版多重人生交互，并修复模型分配、会话恢复、demo 输出串味等体验问题。 (source: @user, created: 2026-03-20, completed: 2026-03-20)
- [x] 收口 `apps/web-v2` play modes 导航：确认 `daily-challenge` worktree 的 `每日一辩 / 剧情冒险 / 海龟汤 / 剧情共演` 在当前分支已具备功能代码，仅补桌面侧边栏与 iOS drawer 入口，不重复迁移玩法实现。 (source: @user, created: 2026-03-20, completed: 2026-03-20)
- [x] 收口 `apps/web-v2` 好友模式行为：开启时显示并启用 `sparkring`，关闭时移除并隐藏该 provider，停止后续模型拉取请求。 (source: @user, created: 2026-03-20, completed: 2026-03-20)
- [x] 适配 `apps/web-v2` 模型列表新接口：`sparkring` 拉模型改为 `GET /api/models/info?key=xxx`，按 token 分组过滤返回。 (source: @user, created: 2026-03-20, completed: 2026-03-20)
- [x] 修复 `apps/web-v2` 聊天页单模型选择回归：选中模型后输入框应立即可用，placeholder/空态文案应切到单模型模式，并允许后续轮次继续改模型。 (source: @user, created: 2026-03-20, completed: 2026-03-20)
- [ ] **[P0]** Context 策略：继续对话时支持三种 context 模式 — ① 中立总结（默认，省 token 且客观）② 仅选中回答 ③ 全量原始回答。前端在输入框上方显示 context chip 可切换，后端拼 prompt 时按 mode 取不同内容。(source: @claude, created: 2026-03-15)
- [ ] 观察新护栏文档执行后的实际效果，补齐容易被绕开的高风险路径 (source: @codex, created: 2026-03-14)

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
