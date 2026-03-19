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
