# Server Claude Cache Runbook

> 更新时间：2026-04-26
> 适用范围：服务端 `new-api` / `new-api-custom` 上所有走 `Claude-compatible /v1/messages` 的 channel

## 目的

这份文档专门记录服务端 `Anthropic prompt cache` 的排查与配置经验，供后续新增模型或新增 channel 时复用。

核心结论先写在前面：

- 如果某条 `Claude-compatible` 通道明明上游支持 cache，但经服务端转发后一直不命中，第一优先排查服务端 `new-api` channel 配置，不要先怀疑本地 `MMS`
- 是否需要修，不按“厂商名”判断，而按“这条 `/v1/messages` 转发链有没有稳定透传 `anthropic-beta` 与 `cache_control`”判断
- 对同时支持 `Anthropic` / `OpenAI-compatible` 的 provider，`Claude` 路径应优先走 `Anthropic /v1/messages`；只有这条路不通时，才退到 `OpenAI bridge`

---

## 2026-04-26 补充：`MMS` 对 dual-protocol / `newapi` 的默认兜底

### 结论

- 最稳妥的配置仍然是同时提供：
  - `anthropic_base_url`
  - `openai_base_url`
- `Claude` 应该吃 `anthropic_base_url`
- `Codex` / `Qwen` / `Kimi` 这类 `OpenAI-compatible` CLI 继续吃 `openai_base_url`

### 新增的 launcher 兜底

从 `2026-04-26` 起，`MMS` 的 `Claude launcher` 多了一层保守兜底：

- 如果 provider 声明支持 `anthropic_messages`
- 但没有显式配置 `anthropic_base_url`
- 只有 `openai_base_url = https://gateway.example.com/v1`
- 那么 `MMS` 会先把它裁成 `https://gateway.example.com`
- 再主动 probe `https://gateway.example.com/v1/messages`

如果 probe 成功：

- `Claude` 直接走 `Anthropic Messages`
- 避免直接掉进 `OpenAI bridge -> /v1/chat/completions`
- 对 `prompt cache` 更友好

如果 probe 失败：

- 保持原来的 bridge fallback
- 不会强行假设这个 root 一定支持 `Anthropic`

### 这个兜底能覆盖什么，不能覆盖什么

能覆盖：

- `newapi` / `new-api-custom`
- 这类 `shared-root gateway`
- 同一个 root 同时承载 `/v1/chat/completions` 和 `/v1/messages`

不能覆盖：

- `Anthropic` 路径和 `OpenAI` 路径本来就不同的厂商
- 例如：
  - `https://coding.dashscope.aliyuncs.com/v1`
  - `https://coding.dashscope.aliyuncs.com/apps/anthropic`

这种场景下，`MMS` 没法从 `.../v1` 自动猜出 `.../apps/anthropic`，仍然应该显式配置两条 URL。

---

## 这次排查得到的稳定结论

### 1. `bailian-direct-anthropic`

现象：

- 直连上游可命中 cache
- 经服务端转发不命中

最终生效的修复：

- `header_override` 增加：

```json
{
  "anthropic-version": "2023-06-01",
  "anthropic-beta": "{client_header:anthropic-beta}"
}
```

说明：

- 根因是服务端这条 `Ali -> Anthropic Messages` 路径没有稳定透传 `anthropic-beta`
- 本地 `MMS` 不需要改

### 2. `glm-direct`

现象：

- 直连上游可以读到 cache
- 经服务端转发时，最初读不到 cache

当前验证后保留的配置：

- `header_override`：

```json
{
  "anthropic-version": "2023-06-01",
  "anthropic-beta": "{client_header:anthropic-beta}"
}
```

- `setting` 里保留：

```json
{
  "force_format": false,
  "thinking_to_content": true,
  "proxy": "",
  "pass_through_body_enabled": true,
  "system_prompt": "",
  "system_prompt_override": false
}
```

说明：

- 这条链路除了 header 透传外，对 body 原样透传也更敏感
- 经验上，`Zhipu/GLM` 这类兼容层建议把 `pass_through_body_enabled` 一起打开

### 3. `kimi-direct`

实测结论：

- 经服务端转发本来就能命中 cache
- 当前不需要额外补 `header_override`

说明：

- 不要因为某个厂商出了问题，就默认同类 channel 全部需要补
- 先测，再决定是否加配置

---

## 新增 `Claude-compatible` channel 时的默认检查项

后续只要新增一条会走 `/v1/messages` 的 channel，至少检查这 4 件事：

1. 上游直连是否真的支持 `prompt caching`
2. 服务端转发后是否仍能看到 `cache_creation_input_tokens` / `cache_read_input_tokens`
3. `anthropic-beta` 是否从客户端透传到了上游
4. `cache_control` 是否在服务端中间转换时被吃掉或改坏

如果 1 成立、2 不成立，基本就是服务端兼容链问题。

---

## 推荐的服务端默认配置模板

### 模板 A：先补 header 透传

适合：

- 上游支持 `Anthropic beta`
- 但当前 channel adaptor 没有显式透传 `anthropic-beta`

推荐配置：

```json
{
  "anthropic-version": "2023-06-01",
  "anthropic-beta": "{client_header:anthropic-beta}"
}
```

用途：

- 让客户端传入的 `prompt-caching-2024-07-31`
- 或未来别的 `anthropic-beta`
- 能继续传到上游

注意：

- 如果该 channel 已经有别的 `header_override`，要做 merge，不要整段覆盖

### 模板 B：再补 body 原样透传

适合：

- header 补了仍然不稳定
- 或怀疑服务端 marshal / convert 过程会影响 `system.cache_control`
- 或供应商兼容层对 `ClaudeRequest` 结构较敏感

推荐配置：

```json
{
  "force_format": false,
  "thinking_to_content": true,
  "proxy": "",
  "pass_through_body_enabled": true,
  "system_prompt": "",
  "system_prompt_override": false
}
```

注意：

- 不要无脑给所有 channel 都开 `pass_through_body_enabled`
- 优先在实测失败的 channel 上开

---

## 推荐排查顺序

### 第一步：先测上游直连

目标：

- 证明“上游本身支持 cache”

如果上游直连都不支持，就不要继续查服务端转发层。

### 第二步：再测经服务端转发

目标：

- 用相同 payload 打服务端 `/v1/messages`
- 看 `usage` 里的 cache 字段是否还存在

判定方法：

- 第一次请求：
  - 预期 `cache_creation_input_tokens > 0`
- 第二次相同请求：
  - 预期 `cache_read_input_tokens > 0`

如果经服务端后这两个值变成 `0` 或 `null`，继续查服务端配置。

### 第三步：看服务端日志 / DB logs

重点看 `logs.other` 里的这些字段：

- `request_path`
- `request_conversion`
- `cache_creation_tokens`
- `cache_tokens`

经验判断：

- `request_path="/v1/messages"` + `request_conversion=["Claude Messages"]`
  说明链路确实走的是 `Claude-compatible`
- `cache_tokens > 0`
  说明已经读到 cache
- `cache_creation_tokens > 0`
  说明成功创建 cache

---

## 标准验证 payload

无论测哪家，尽量都用同一类 payload：

```json
{
  "model": "your-model",
  "max_tokens": 32,
  "system": [
    {
      "type": "text",
      "text": "large repeated corpus ...",
      "cache_control": { "type": "ephemeral" }
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": "Reply with OK only."
    }
  ]
}
```

请求头至少带：

```http
Content-Type: application/json
anthropic-version: 2023-06-01
anthropic-beta: prompt-caching-2024-07-31
```

注意：

- `system` 内容要足够大，否则很难观察到明显 cache 效果
- 两次请求 payload 要完全一致

---

## 当前服务端经验矩阵

| Channel | 当前状态 | 需要动作 |
|---|---|---|
| `bailian-direct-anthropic` | 已验证可用 | 保留 `anthropic-version + anthropic-beta` 的 `header_override` |
| `glm-direct` | 已验证可用 | 保留 `header_override`，并保留 `pass_through_body_enabled=true` |
| `kimi-direct` | 已验证可用 | 暂时不改 |
| `mimo-anthropic` | 未在本轮实测 | 新增或调整后按本 runbook 复测 |
| 未来新 channel | 未知 | 先直连测，再经服务端测，再决定是否补配置 |

---

## 以后新增模型 / 新增 channel 的建议流程

1. 先确认该上游是否真的支持 `Claude-compatible prompt cache`
2. 在服务端新建 channel 后，不要直接默认“已经通了”
3. 先跑两次相同 payload 的 `/v1/messages` 测试
4. 如果不命中：
   - 先补 `header_override`
   - 还不稳定再开 `pass_through_body_enabled`
5. 最后再看 `logs.other.cache_tokens` / `cache_creation_tokens` 是否匹配

---

## 不要先做的事

- 不要先改本地 `MMS`
- 不要先改模型映射
- 不要先改 provider 定义
- 不要只看 UI 显示就判断“已经有 cache”

先证明：

- 上游支持
- 服务端转发后也支持

再决定是否需要进一步改代码。

---

## 一句话版本

后面凡是新增 `Claude-compatible` 模型链路，都先按“上游直连 -> 服务端转发 -> header 透传 -> body 透传 -> logs 验证”这条路径排查；当前已确认：

- `bailian` 要补 header
- `glm` 要补 header，且建议开 `pass_through_body_enabled`
- `kimi` 当前不用补
