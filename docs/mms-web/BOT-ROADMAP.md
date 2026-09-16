# MMS Bot 后续优先级

目标是把 Bot 做成真实可用的员工层，而不是在 Pilot 旁边增加一个入口。排序按“对用户体感的提升 / 对可靠性的影响 / 是否重复造轮子”决定。

## 防止退回普通多 Agent Harness

Oh My OpenCode 这类插件已经证明了“主 Agent + 规划 Agent + 执行 Agent + 专家 Agent”对单个 coding 任务有效；它的公开配置包含 Sisyphus、Prometheus、Atlas、Hephaestus 等不同角色和模型映射。MMS Bot 可以借鉴这种内部编排，但不能把每一个内部角色都暴露成一个需要用户长期管理的 Bot。

保持两层：

```text
Bot 层：长期身份、角色、记忆、调度、收件箱、用户关系
工作层：一次任务中的 planner / worker / reviewer / browser executor
```

Bot 可以调用临时工作者；临时工作者完成任务后交回结果，不自动变成新的永久 Bot。只有用户明确创建的员工才进入 Bot 列表。

如果某一版只能做到“不同 Bot 选择不同模型，然后互相 dispatch”，说明编排层做到了，但员工层还没有完成，不能把它称为最终 Bot 体验。

## P0：可靠的员工闭环

### 1. Coordinator 计划层

用户只说目标时，Coordinator 先判断：当前 Bot 是否能直接做、是否需要分工、应该派给哪些 Bot、哪些结果必须等待。路由结果要在聊天中可见，并保留计划、子任务、依赖和最终汇总的关系。

验收：给 A 一个包含两个独立子目标的请求，A 自动派给 B/C；B/C 完成后 A 自动恢复，最终只给用户一份结构化结论。

### 2. 结构化结果回执

Bot 结束时统一回报：结论、证据、改动、未完成事项和下一步。工具日志仍保存在诊断记录中，但不污染用户聊天。没有证据时明确标为未知，不能把“命令退出 0”当成业务完成。

验收：文件、截图、网页动作和子任务都有可点击的成果或明确缺失原因。

### 3. 失败恢复与幂等

让任务在等待、进程中断、服务重启、Provider 暂时不可用后可以继续；有副作用的动作必须使用 requestId 和回读确认，不自动重放未知动作。

验收：杀掉 Pi session 后继续同一个 Bot，Bot 能读取原记录，避免重复写入，并给出恢复提示。

## P1：持续工作的员工体验

### 4. Bot 级连续性

保持 Bot 身份、memory、Skill 组合和协作收件箱不变；Pi session 只是当前运行实例，可以重建或替换。支持 Bot 的暂停、恢复、轮换模型和上下文压缩。

### 5. Browser Provider

统一 `BrowserProvider` 接口。macOS 使用 Ego，Windows / Linux 使用 Web Access 连接明确授权的 Chrome / Edge CDP。Bot prompt 不感知平台差异；MMS 不复制 cookie、profile 或浏览器引擎。

### 6. 可观测但不打扰

主聊天只显示目标、状态、协作、结果和等待；需要时展开“执行详情”查看工具、Provider、耗时、模型和失败原因。默认不显示连续 CLI 过程。

## P2：规模和复用

### 7. 并发、成本和优先级

按 Bot、Provider、模型额度和任务优先级调度；对长任务给出预计等待和资源占用，避免多个 Bot 互相抢同一浏览器或 workspace。

### 8. 外部能力 adapter

只在真实瓶颈出现后接入成熟项目。Browser Use 用于浏览器任务循环参考，OpenHands SDK 用于事件和工具抽象参考，LangGraph 用于复杂状态机参考；不同时引入多套相同运行时。

## 明确不做

当前不自研浏览器引擎、操作系统级 Computer Use、云端 VM 或通用 Connector 平台。它们只有在找到可复用且能接入 MMS/Pi 的执行器后，才通过 adapter 纳入。
