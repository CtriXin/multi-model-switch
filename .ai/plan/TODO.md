# TODO

## Urgent + Important
- [ ] 观察新护栏文档执行后的实际效果，补齐容易被绕开的高风险路径 (source: @codex, created: 2026-03-14)
- [x] 增加独立诊断脚本，验证 provider/account 连通性、模型 chat 可用性和 Claude 路径兼容性 (source: @codex, created: 2026-03-14, completed: 2026-03-15)

## Important + Not Urgent
- [ ] 将主启动链路补成更明确的回归清单，后续改动可直接对照验证 (source: @codex, created: 2026-03-14)
- [ ] 评估并设计 `skill` 调用临时会话时的可选 model 能力，避免只能走固定默认模型 (source: @codex, created: 2026-03-14)
- [ ] 评估是否需要给 `codex` 增加 `Anthropic messages` bridge，以承载 `agent_only` 型 provider (source: @codex, created: 2026-03-15)
- [ ] route_learned.json 淘汰策略：加上限（如 200 条）+ LRU 淘汰 + 文件锁防并发写入 (source: @claude, created: 2026-03-15, from: agent-discuss feedback)
- [ ] 智能路由实时状态展示：在 Claude 运行时显示当前 tier (light/medium/heavy) 和实际使用的 model (source: @claude, created: 2026-03-15)

## Urgent + Not Important
- [ ] 用户按计划手动推进 `mms skill run` 最小入口后，回填实际偏差与新约束 (source: @codex, created: 2026-03-14)

## Neither
- [ ] 评估是否需要补一个显式命令别名，例如 `mms run --auto-model`，避免 hook 语义过隐式 (source: @codex, created: 2026-03-14)
