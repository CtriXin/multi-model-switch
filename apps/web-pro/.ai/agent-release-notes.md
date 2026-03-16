## 2026-03-15 角色委员会功能

- timestamp: 2026-03-15
- agent: Codex
- landed commit/tag/release: none
- changed file scope: `src/views/DiscussPane.vue`, `src/stores/discuss.ts`, `src/components/SummaryCard.vue`, `src/components/ReviewCard.vue`, `src/components/PhaseSection.vue`, `src/views/HomePane.vue`, `src/features/committee.ts`
- concise landed summary: 将现有 Discuss 升级为 AI 角色委员会，加入 12 个预设角色、广播/辩论/委员会 3 种模式，以及系统汇总输出。
- reusable release-note bullets:
  - 新增 12 个具备固定世界观与立场轴的 AI 角色
  - 支持广播模式、辩论模式、委员会模式三种运行方式
  - 委员会模式可输出带贡献标注的系统级结论
- validation run and result: `npm run build` passed

## 2026-03-15 委员会收敛增强

- timestamp: 2026-03-15
- agent: Codex
- landed commit/tag/release: none
- changed file scope: `src/features/committee.ts`, `src/stores/discuss.ts`, `src/views/DiscussPane.vue`
- concise landed summary: 强化委员会模式的可追溯收敛输出，并把 Discuss 页样式收回到项目统一视觉语言。
- reusable release-note bullets:
  - 委员会模式新增共识、主要分歧、建议动作、少数派意见四类结构化结果
  - 每条委员会结论都标注对应角色来源，便于追溯判断依据
  - Discuss 页面样式与现有项目卡片体系保持统一
- validation run and result: `npm run build` passed

## 2026-03-15 模型自动分配优化

- timestamp: 2026-03-15
- agent: Codex
- landed commit/tag/release: none
- changed file scope: `src/features/committee.ts`, `src/stores/discuss.ts`, `src/views/DiscussPane.vue`
- concise landed summary: 将模型池分配从顺序轮转升级为职责驱动的自动分配，并加入轻量可视化说明。
- reusable release-note bullets:
  - 关键角色会优先分配更强模型，中枢和补充角色按能力标签自动匹配
  - 用户仍只需要选择模型池，系统会自动完成角色分配
  - 支持在 Discuss 页面查看当前角色到模型的自动分配结果
- validation run and result: `npm run build` passed

## 2026-03-16 委员会包扩展

- timestamp: 2026-03-16
- agent: Codex
- landed commit/tag/release: none
- changed file scope: `src/features/committee.ts`, `src/views/DiscussPane.vue`
- concise landed summary: 在现有 12 角框架上新增产品、运营、设计三类委员会包，并将猜你喜欢改为包内预设。
- reusable release-note bullets:
  - 新增产品委员会、运营委员会、设计委员会三类任务委员会包
  - 将猜你喜欢升级为按委员会包组织的常用角色组合
  - 新的预设命名更贴近需求解析、活动复盘、视觉评审等真实工作场景
- validation run and result: `npm run build` passed
