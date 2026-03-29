# CRS / MMS 账号绑定与加固 Runbook

> 更新时间：2026-03-29
> 目标：把 `MMS -> newapi -> CRS -> Claude OAuth accounts` 和 `MMS -> direct CRS key` 两种入口的职责讲清楚，并给出可执行的接入、验证、加固流程。

## 1. 先讲结论

这套系统长期建议采用：

- 正常业务流量：`MMS -> newapi -> CRS`
- 运维/排障流量：`MMS -> direct CRS key`

不要把所有流量都直连 `CRS`，也不要让所有人都自己手工绑账号。最稳的方式是：

- `newapi` 负责“识别是谁在用”
- `CRS` 负责“该派给哪个 OAuth 账号”
- `direct CRS key` 只保留给少量诊断入口

## 2. 谁负责什么

### 2.1 用户自己必须做的事

用户必须自己完成：

1. 在目标机器/浏览器里完成 `OAuth` 登录
2. 确保该账号在 `CRS` 后台里已经可见
3. 提供本次要使用的 `proxy / IP`

原因：

- `OAuth` 登录需要真人浏览器交互
- agent 不能替你登录第三方账号
- agent 可以在你完成登录后继续绑定、建 key、校验和接入

### 2.2 agent 可以代做的事

agent 可以代做：

1. 创建 `CRS` 直连 API key
2. 把 key 绑定到指定 Claude OAuth 账号
3. 修复新建 key 后前台列表不可见的问题（补 API Key index）
4. 在本机 `MMS` 增加/删除 provider
5. 为敏感 provider 关闭 `1M`
6. 跑 smoke 并校验 proxy 是否生效
7. 下线被封/被禁用的账号和相关 key/provider

## 3. 账号用途怎么分

不要默认“某个账号只是诊断用”。账号本身都是干活的号，真正需要区分的是入口用途：

- `private`
  - 主力独享入口
  - 适合最稳、最贵、最可控的账号
- `fishcrs`
  - 单账号直连入口
  - 适合低频直连、运维排障、备用
- `xin`
  - 聚合入口
  - 适合统一对外、后续公司侧统一接入

所以要区分的是：

- 一个账号暴露为哪个入口
- 一个入口是否允许进调度池
- 一个入口是否允许 `1M`

## 4. `1M context` 的实际策略

### 4.1 不要把 `1M` 当成全局默认

即使官方模型支持 `1M`，也不能默认所有 provider / account / relay 都安全支持。

本项目当前已验证：

- `xin`
- `fishcrs`
- `trcrs`（已删除）

都必须按“先试、再开”的策略处理。

### 4.2 当前项目规则

对下列敏感 provider：

- `xin`
- `fishcrs`
- `trcrs`（若以后恢复）

默认策略是：

1. 不追加 `[1m]`
2. 设 `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`
3. `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 固定回 `200k`
4. 不做额外 `Anthropic endpoint probe`

`private/B2` 当前保留原有 `1M` 行为，不跟这批敏感 provider 混用。

### 4.3 正确的开关方式

以后新账号不要靠感觉决定是否允许 `1M`，一律按下面流程：

1. 先直连 `haiku`
2. 再直连普通 `opus/sonnet`
3. 最后才试 `1M`
4. 一旦看到 `Extra usage required for long context requests`
   - 立刻视为“不支持 1M”
   - 后续默认走保守窗口

## 5. Proxy / 静态 IP 怎么验

### 5.1 不接受“黑盒相信”

要把“是否真的走了指定 proxy”当成绑定成功的硬条件。

至少要同时满足：

1. 账号对象里明确配置了 `proxy`
2. smoke 后 `CRS` 日志出现：
   - `Using proxy for Claude request: <expected_proxy>`
3. 如果有静态出口 IP，还要额外记录本次出口 IP

### 5.2 以后统一的校验方式

每次接新号后，都必须跑：

1. 最小 `haiku` 请求
2. 查 `CRS` 日志确认：
   - `Using proxy for Claude request: ...`
3. 再决定是否把这个账号放进调度池

如果日志里没看到 `Using proxy ...`，就视为失败。

## 6. 一个 IP 可以挂几个号

最稳：

- `1号1IP`

可接受但有风险：

- `2号1IP`

高风险：

- 多号共用 1 个 IP
- 同时高频使用
- 叠加自动重试
- 叠加 `1M`

当前可接受的运营规则：

- `B2` 和 `fish` 可共用一个 IP
- 但不要同时高频使用
- 不要在同一时段同时跑大流量
- 主力号和试验号不要一起打爆同一个出口

## 7. `newapi` 和 `CRS` 怎么分工

### 7.1 推荐结构

- 一个 `newapi` 对一个主 `CRS`
- 一个 `CRS` 管理多个 OAuth 账号
- `newapi` 负责透传用户身份
- `CRS` 负责 quota-aware 选号和 session sticky

不推荐：

- 一个 `newapi` 逻辑再分发到多个独立 `CRS`
- 多套 `CRS` 各玩各的 sticky / 绑定 / quota 逻辑

### 7.2 为什么推荐统一走 `newapi -> CRS`

因为这样：

1. 对外只有一个入口
2. 用户级身份可以在 `newapi` 注入
3. 账号调度在 `CRS` 统一处理
4. 公司和个人可以复用一套逻辑

直连 `CRS key` 仍然保留，但只给诊断和运维。

## 8. `meta/header` 到底重不重要

重要，但不是这次账号被禁用的主因。

### 8.1 绝对不能丢的

- `User-Agent`
- `x-app`
- `anthropic-version`
- `anthropic-beta`（仅在需要的链路）
- `metadata.user_id`（必须是 string）

### 8.2 为什么重要

- 这些字段影响 `newapi` / `CRS` 对客户端的识别
- 影响 sticky 和 session 命中
- 影响是否被当成真实 `Claude Code`

### 8.3 但这次主因不是它们

本轮实际证据显示，更危险的是：

1. `1M / long-context`
2. 高频 retry
3. 共用 proxy
4. 短时间重复启动

所以 `meta/header` 是“正确性约束”，不是这次封号的主按钮。

## 9. 账号被禁用/封号时怎么处理

如果看到任一类错误：

- `This organization has been disabled`
- `Account blocked`
- `403 error detected`

处理原则：

1. 立即从调度池摘掉
2. 禁用绑定的 direct key
3. 禁用/删除本机 `MMS provider`
4. 如果该账号还被其他 key 绑定，先重新绑定，再删账号

不要只做 `disable` 然后继续把它留在一堆配置里发霉。

## 10. 新账号接入 Checklist

以后每次新账号接入，按这个顺序做：

1. 用户自己完成 `OAuth`
2. 确认账号在 `CRS` 后台可见
3. 明确本次 `proxy / IP`
4. agent 创建 direct key
5. 补 `API Key index`
6. 在本机 `MMS` 增加 provider
7. 先跑 `haiku` smoke
8. 查日志确认 `Using proxy for Claude request: <expected_proxy>`
9. 再试普通 `opus/sonnet`
10. 最后才试 `1M`

## 11. 公司侧怎么复用

建议公司和个人使用：

- 同一套 `newapi -> CRS` 架构
- 同一套 identity passthrough
- 同一套 quota-aware routing
- 同一套 `1M` 试探规则

只分开：

- 账户池
- key 空间
- proxy / IP 资源

## 12. 当前已知稳定边界

截至 2026-03-29，本地已确认：

- `private`
  - 保留给 `B2`
- `fishcrs`
  - 直连 `CRS`
  - 默认禁用 `1M`
- `trcrs`
  - 已移除
- `xin`
  - 作为 `newapi -> CRS` 聚合入口
  - 默认禁用 `1M`

## 13. 一句话版本

默认走 `newapi -> CRS`，直连 key 只留给诊断；新号一律先验 proxy、再验普通窗口、最后才试 `1M`。
