# TODO Archive Snapshot - 2026-03-18T10:30

> 此文件为 TODO.md v0.3.3 → v0.3.4 升级前的完整快照备份
> 对应 git commit: `07417ba` (baseline restore and preliminary UI consistency preparation)

---

## Q1: Urgent + Important（截至备份时 open 项）

- [ ] **[P0] [Mobile]** 每日一辩 + 认知进化追踪器 MVP：每日 AI 生成话题 → 用户选立场 → 多模型辩论 → 认知维度标注 → 观点卡保存。需要：`dailyChallengeStore.ts`、`cognitiveStore.ts`、`DailyChallengeView.vue`、话题生成 prompt、认知标注 prompt、雷达图组件。(source: @user+@claude, created: 2026-03-17)
- [ ] **[P0] [Mobile]** 知识资产沉淀层：Discuss/Committee 完成后自动保存结构化结果为知识卡片（IndexedDB），含分类、搜索、回顾。需要：`knowledgeStore.ts`、`KnowledgeView.vue`。(source: @user+@claude, created: 2026-03-17)
- [ ] **[P0]** Context 策略：继续对话时支持三种 context 模式 — ① 中立总结（默认，省 token 且客观）② 仅选中回答 ③ 全量原始回答。前端在输入框上方显示 context chip 可切换，后端拼 prompt 时按 mode 取不同内容。(source: @claude, created: 2026-03-15)
- [ ] 观察新护栏文档执行后的实际效果，补齐容易被绕开的高风险路径 (source: @codex, created: 2026-03-14)

## Q2: Important + Not Urgent（截至备份时 open 项）

- [ ] **[P1] [Mobile]** AI 辩论秀模式
- [ ] **[P1] [Mobile]** 内容消化器
- [ ] **[P1] [Mobile]** 思维盲区扫描器
- [ ] **[P1] [Mobile]** 成果打卡系统
- [ ] **[P1] [Mobile]** 场景预设入口
- [ ] 共享入口文件同步（router/Sidebar/SettingsView/SetupGuide）
- [ ] 锦囊团 Phase 3（自定义角色 + 辩论模式）
- [ ] 锦囊团 Persona 漂移防护增强
- [ ] 锦囊团 UX 分层
- [ ] Judge Tier 3 — Committee / Deep Review
- [ ] Single-model compatibility
- [ ] 会话持久化、模型搜索筛选、导出对话
- [ ] `packages/contracts` 契约固化
- [ ] 主启动链路回归清单
- [ ] Skill 临时会话 model 能力评估
- [ ] Codex Anthropic messages bridge 评估
- [ ] route_learned.json 淘汰策略

## Q3: Urgent + Not Important（截至备份时 open 项）

- [ ] 新会话最短启动指引

## Q4: Neither / Deferred（截至备份时 open 项）

- [ ] **[Workbench]** 终端渲染乱码验证
- [ ] **[Workbench]** Per-slot model 选择 UI
- [ ] **[Workbench]** Task 详情面板
- [ ] **[P2] [Mobile]** 社交共创模式
- [ ] **[P2] [Mobile]** AI 决策日记
- [ ] **[P2] [Mobile]** 历史共识回顾
- [ ] Discuss → Rollup → Final Judge → Output 全链路
- [ ] Gateway model slot 共存模式
- [ ] OAuth Plan 用量查询 per-model
- [ ] Model Pricing DB 自动更新
- [ ] `mms run --auto-model` 显式命令别名评估

---

## 统计摘要

| 象限 | 总条目（含已完成） | Open | Completed |
|------|---------------------|------|-----------|
| Q1 Urgent+Important | 8 | 4 | 4 |
| Q2 Important+NotUrgent | 23 | 17 | 6 |
| Q3 Urgent+NotImportant | 1 | 1 | 0 |
| Q4 Deferred | 11 | 11 | 0 |
| **合计** | **43** | **33** | **10** |

> 注：已完成的 10 项主要为 Workbench 相关任务（Alpha/Beta/Omega 派单系统）
