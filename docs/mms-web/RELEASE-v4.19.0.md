# v4.19.0 · 旁问直答与消息控制

## Pilot 旁问

- **`/btw` 直接回答当前问题**：旁问使用当前 session 的状态快照或 session-owned route，答案留在旁问卡片中，不写入主任务 transcript，也不改变主任务队列和 runtime。
- **状态与模型来源可见**：卡片显示回答来源、上下文 revision、路由和失败原因；没有可用模型时明确失败，不伪造 endpoint 或成功结果。
- **审批期间仍然可问状态**：主任务等待 approval 时，状态旁问仍可回答；`steer` 不绕过审批，返回明确的 `APPROVAL_PENDING`。

## 消息控制

- **`followUp` 与 `steer` 分开**：follow-up 按 lane 排队；steer 在当前工具步骤完成后，通过 Pi 原生 steer 边界送达。
- **`interrupt` 是明确停止路径**：停止会处理中断审批、清理队列并保留已经完成的历史；未送达消息显示为 interrupted 或 cancelled，取决于实际操作。
- **队列可读、可控、可恢复**：支持 steering/follow-up lane 展示、promote、remove、reorder，并在恢复或进程退出时准确标记无法送达的消息。
- **请求幂等**：重复 request 不重复写入 wire command；不同 mode 属于不同请求指纹。

## 升级须知

- 本次包含 Pilot 前端、session backend、消息控制和静态 bundle 更新。
- 升级前建议等待正在执行的任务结束；更新期间 Pilot 会重启，页面会自动刷新。
- 已有 session history、旁问记录和队列结果保留在原 state-root；真实配置、账号和 API key 不会被更新流程改写。

## 验证范围

- 完整 `mms_web` 回归、frontend tests、compile/build、approval-waiting HTTP smoke、OpenAI-only transport smoke、Pi wire steer/interrupt smoke 和 normal URL bundle smoke 均通过。
- 本版仍只宣传 Pi Web adapter；Grok、Claude、Codex、OpenCode 的统一 harness 接入不包含在本版。
