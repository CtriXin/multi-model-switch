# newapi + CRS 多账号 Sticky Session 配置方案

> 更新时间：2026-03-25
> 目标读者：需要把 `newapi` 作为统一入口、把 `CRS` 作为下游 OpenAI OAuth 承载层的同事

## 目标

要实现的不是“永远固定一个账号”，而是：

- 新 session 第一次进入时，可以在多个 OpenAI 账号之间动态分配
- 同一个 session 进入后，要稳定粘到同一个 OpenAI 账号
- 只有新 session、主动 drain、或账号异常时，才切到别的账号

## 结论先说

当前最稳、最容易运维、也最容易解释的问题分层是：

1. `CRS API key` 只绑定一个固定的 OpenAI OAuth 账号
2. `newapi channel` 只使用一把固定的 `CRS API key`
3. 同模型能力建多条 `newapi channel`
4. 把这些 channel 放进同一个 `group`
5. 开启 `channel_affinity`，让同一 session 粘到首次成功的 channel

这样粘住的其实是 `channel`，但因为一条 `channel` 背后只接一把 `CRS key`，而一把 `CRS key` 又只绑定一个 OpenAI 账号，所以最终效果就是“当前 session 粘住一个 OpenAI 账号”。

## 不推荐的做法

不要用下面这种结构：

- 一把 `CRS key`
- 这把 key 绑定 `group:*`
- 再让 `CRS` 内部 scheduler 动态选 OpenAI 账号

原因：

- `newapi` 只能稳定粘 `channel`
- 它粘不住 `CRS` 里 `group:*` 内部的具体账号
- 这样即使 `newapi` sticky 生效，`CRS` 内部仍可能把同一 session 派到不同 OpenAI 账号
- 上下文、prompt cache、response storage 都会变得不稳定

## 推荐拓扑

以 3 个 OpenAI 账号为例：

### CRS 层

- `crs-key-codex-a` -> 绑定 `openai-account-a`
- `crs-key-codex-b` -> 绑定 `openai-account-b`
- `crs-key-codex-c` -> 绑定 `openai-account-c`

规则：

- 一把 key 只绑一个账号
- 不要绑 `group:*`
- 不要在活跃 session 期间随意把 key 改绑到别的账号

### newapi 层

- `channel: crs-codex-a`
  - `base_url = http://.../openai`
  - `api_key = crs-key-codex-a`
- `channel: crs-codex-b`
  - `base_url = http://.../openai`
  - `api_key = crs-key-codex-b`
- `channel: crs-codex-c`
  - `base_url = http://.../openai`
  - `api_key = crs-key-codex-c`

然后把这些 channel 放进同一个可对外暴露的模型组，例如：

- `group = codex_pool`

对外同事只打：

- `newapi -> group codex_pool`

## 权重和切流建议

首次分配由 `weight` / `priority` 决定。

推荐规则：

- 主账号：`weight` 高一点
- 备账号：`weight` 中等
- 保底账号：`weight` 低一点

例如：

- `crs-codex-a`: `weight = 10`
- `crs-codex-b`: `weight = 6`
- `crs-codex-c`: `weight = 3`

## 账户快满时怎么做

要区分“新 session 切流”和“老 session 维持”。

### 只想让新 session 不再进入某账号

做法：

- 把对应 channel `weight` 调低到 `0`
- 或直接 `disable channel`

效果：

- 已经粘住该 channel 的旧 session，仍可能继续使用
- 新 session 不再分配到这条 channel

### 想彻底 drain 某账号

做法：

1. 先把对应 channel `weight = 0`
2. 等待已有 session 自然结束
3. 再停用该 channel 或改绑 CRS key

不要直接把：

- `crs-key-codex-a`

从 `openai-account-a` 硬切到 `openai-account-b`

否则已经 sticky 到该 channel 的 session 会在不中断 session key 的前提下，被你静默换到底层账号，最容易出现上下文错位。

## newapi 必须注意的配置点

这是本轮已经踩过的坑。

### 1. `pass_through_body_enabled` 必须是 `false`

如果对应 channel 开了：

- `setting.pass_through_body_enabled = true`

会导致 `newapi` 跳过 `ApplyParamOverrideWithRelayInfo(...)`，从而让下面这些能力全部失效：

- `pass_headers`
- `sync_fields`
- `header -> json` 映射

本轮 live 排障已经确认，这正是 `xin(4001)` 之前 header 透传失效的真实根因。

### 2. `pass_headers` 要补齐 Codex 关键头

至少应包含：

- `User-Agent`
- `Originator`
- `Session_id`
- `X-Session-Id`
- `OpenAI-Beta`

### 3. `sync_fields` 需要把 session 信息写到 body

当前 `newapi` 的 `channel_affinity` 默认更偏向从请求体取 key source。

因此要确保：

- `header:session_id -> json:prompt_cache_key`

这一类映射能生效。

### 4. `Claude metadata.user_id` 必须保持“字符串”格式

这次 live 排障确认，真实 `Claude CLI` 发的是：

- `metadata.user_id = "{\"device_id\":\"...\",\"account_uuid\":\"...\",\"session_id\":\"...\"}"`

不是：

- `metadata.user_id = { ... }`

如果中间层把它改成对象：

- 上游会直接报 `metadata.user_id: Input should be a valid string`
- `channel_affinity` 即使仍能取到值，语义也已经偏离真实 `Claude CLI`

因此 `Claude -> newapi -> CRS` 的稳定要求里，要额外加一条：

- 不要把 `metadata.user_id` 从 string 改写成 object

## Sticky 的真实边界

`newapi channel_affinity` 粘的是：

- `channel`

不是：

- `CRS 内部 openaiAccountId`

也不是：

- `OpenAI 官方 response id`

所以要得到真正稳定的“账号粘连”，必须满足下面三层都稳定：

1. `MMS / client` 把 session 相关头带到 `newapi`
2. `newapi` 用这些信息稳定选中同一条 `channel`
3. `channel` 背后的 `CRS key` 始终绑定同一个 OpenAI 账号

## 建议命名

建议直接把“用途 + 账号槽位”编码进名字里，方便运维：

- `crs-codex-a`
- `crs-codex-b`
- `crs-codex-c`
- `crs-chat-base-a`
- `crs-chat-base-b`

对应 CRS key 也统一：

- `crs-key-codex-a`
- `crs-key-codex-b`
- `crs-key-codex-c`

## 推荐运维规则

- 不要让一把 `CRS key` 绑定 `group:*`
- 不要在活跃 session 上直接改 key 绑定关系
- 某账号异常时，优先调低 `weight` 或禁用 channel
- 需要迁移时，用“新 channel + 新 key + 新账号”替代“原 channel 改绑新账号”
- 任何 sticky 问题先查三层：`MMS -> newapi`、`newapi distributor`、`CRS key -> account`

## 最小验证清单

### 验证 header 透传

在 `CRS` 日志里确认看到：

- `User-Agent: codex_*`
- 不再是 `python-httpx/...` 或 `Go-http-client/1.1`

### 验证 sticky 生效

连续三次同一 session 请求，确认：

- `newapi` 命中同一条 channel
- `CRS` 日志看到同一把 API key
- `CRS` 日志看到同一个绑定账号
- `Claude` 场景下，确认 `metadata.user_id` 在日志里仍是字符串，不是对象

### 验证切流

把某条 channel `weight = 0` 后确认：

- 旧 session 还能继续
- 新 session 会落到别的 channel

## 当前已确认的现网事实

截至 2026-03-25：

- `xin(4001)` 背后是定制版 `newapi`
- 之前 header 透传失败的真正原因是 `pass_through_body_enabled=true`
- 修正为 `false` 后，下游 private `CRS` 已重新识别为 `codex_cli_rs/...`
- 当前 `new-api-relay` 已先临时绑到单账号 `charlotte`

同日额外 live 结论：

- `Claude -> newapi(4001) -> CRS` 已确认 sticky 生效
- 固定 `session_id = sess-sticky-claude-001` 连续 3 次请求，CRS 都落到同一个账号 `claude-official`
- 但最小 `hi` 请求的 `usage` 为：
  - `input_tokens = 22`
  - `cache_creation_input_tokens = 0`
  - `cache_read_input_tokens = 0`

这说明：

- sticky 生效不等于一定会看到 `cache read`
- `Claude` 的 prompt cache 是否命中，还取决于上游是否认为这批请求满足缓存条件

这是短期兜底，不是长期最优结构。

长期还是建议按本文档拆成：

- 多 `CRS key`
- 多 `newapi channel`
- 单 key 单账号
- `channel_affinity` 做 session sticky
