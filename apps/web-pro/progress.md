# Progress

## 2026-03-15

- 读取 `DiscussPane.vue`、`stores/discuss.ts`、`api/mock.ts`、`contracts`。
- 确认功能落点为现有 `Discuss` 页面升级，而非新增独立产品壳。
- 开始设计角色委员会的数据结构与模拟输出。
- 新增 `src/features/committee.ts`，定义 12 个预设角色、3 种模式与 mock 生成逻辑。
- 重写 `src/stores/discuss.ts` 与 `src/views/DiscussPane.vue`，接入角色选择、模式切换、辩论回应和委员会汇总。
- 更新 `SummaryCard`、`ReviewCard`、`PhaseSection` 与首页文案。
- 执行 `npm run build` 并通过。
- 将 `committee` 进一步升级为可追溯结构化输出，新增共识、分歧、建议动作、少数派意见四类结果。
- 调整 `Discuss` 页视觉，降低独立概念页强度，回归现有项目的浅色卡片和灰阶层级。
- 再次执行 `npm run build` 并通过。
- 将模型池分配从简单轮转升级为“角色职责优先级 + 模型标签匹配 + 复用惩罚”的自动分配策略。
- 在 `Discuss` 空状态新增轻量的“查看分配”折叠面板，保持最小交互但让分配逻辑可解释。
- 再次执行 `npm run build` 并通过。
- 新增 `委员会包` 层，覆盖产品、运营、设计三类任务域。
- 将 `猜你喜欢` 预设改造成包内预设，并把预设命名改成更贴近真实工作需求的组合。
- 再次执行 `npm run build` 并通过。
