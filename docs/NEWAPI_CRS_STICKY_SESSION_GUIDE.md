# newapi + CRS 多账号 Sticky Session 配置方案

> 更新时间：2026-03-26
> 目标读者：需要把 `newapi` 作为统一入口、把 `CRS` 作为下游 OpenAI OAuth 承载层的同事

---

## 2026-03-26 服务器验证更新

> 以下内容基于对 `82.156.121.141` 生产服务器的实际登录验证，包括 CRS 源码阅读、Redis 数据查验、newapi 数据库查询和实际请求测试。

### 结论变更：推荐 CRS 做 sticky，而非 newapi 多 channel

经过服务器验证，原文档中"不推荐"的 CRS group sticky 方案实际上**已经在 Claude 链路稳定运行**，且 CRS 的 sticky 实现比预期更完备。**现在推荐 CRS 负责 sticky，newapi 只做透传。**

原因：

1. **CRS 直接感知账号状态** — 限流、异常时自动摘除重选，newapi 只能等下游返回错误
2. **运维成本低一个量级** — 加减账号只需操作 CRS group，不需要创建 key/channel/param_override
3. **已有生产验证** — Claude 链路已在此模式下稳定运行

### 现网服务器拓扑确认

```
容器                                    端口         状态
new-api-custom                         :4001        Up
claude-relay-service-claude-relay-1    :3000        Up (healthy)
new-api-original                       :4000        Up
postgres                               :5432        Up
redis (newapi)                                      Up
claude-relay-service-redis-1 (CRS)                  Up
```

### newapi channel 现网配置（DB 查询确认）

| ID | Name | base_url | pass_through_body_enabled | param_override | status |
|----|------|----------|--------------------------|----------------|--------|
| 8 | CRS-Codex (GPT-Coding) | `http://172.19.0.1:3000/openai` | `false` | `pass_headers` + `sync_fields` | 启用 |
| 10 | CRS-Codex-Chat-5.4-only | `http://172.19.0.1:3000/openai` | `false` | 无（靠 channel_affinity 自动注入） | 停用(status=2) |
| 11 | CRS-Codex-Chat-Base | `http://172.19.0.1:3000/openai` | `false` | `pass_headers` + `sync_fields` | 启用 |
| 12 | CRS-Claude | `http://172.19.0.1:3000/claude` | `false` | 无（靠 channel_affinity 自动注入） | 启用 |

所有 CRS channel 使用**同一把 CRS key** `cr_bb46...`（name: `new-api-relay`）。

channel 8 和 11 的 `param_override` 内容：
```json
{
  "operations": [
    {"mode": "pass_headers", "value": ["User-Agent", "Originator", "Session_id", "X-Session-Id", "OpenAI-Beta"]},
    {"mode": "sync_fields", "from": "header:session_id", "to": "json:prompt_cache_key"}
  ]
}
```

channel 10 和 12 虽然没有手动配 `param_override`，但 **`channel_affinity` 规则在匹配时会自动注入 `ParamOverrideTemplate`**（见下方源码分析），所以 header 透传仍然生效。

### newapi channel_affinity 源码确认

位置：`/opt/new-api/src/newapi-src/setting/operation_setting/channel_affinity_setting.go`

数据库中**无覆盖配置**（`options` 表无 `channel_affinity` 相关行），全部走源码默认值：

```
enabled:            true
switch_on_success:  true
max_entries:        100,000
default_ttl_seconds: 3600
```

默认规则：

| 规则名 | 模型匹配 | 路径匹配 | key_source | 自动注入 header |
|--------|---------|---------|------------|----------------|
| `codex cli trace` | `^gpt-.*$` | `/v1/responses` | `gjson:prompt_cache_key` | Originator, Session_id, User-Agent, X-Codex-Beta-Features, X-Codex-Turn-Metadata |
| `claude cli trace` | `^claude-.*$` | `/v1/messages` | `gjson:metadata.user_id` | X-Stainless-*, User-Agent, X-App, Anthropic-Beta, Anthropic-Version 等 |

关键机制：`channel_affinity` 的 `ParamOverrideTemplate` 会与 channel 自身的 `param_override` **合并**（`mergeChannelOverride`），所以即使 channel 没配 `param_override`，只要 affinity rule 匹配了也会自动注入 `pass_headers`。

### CRS key 绑定关系（Redis 查询确认）

API key: `new-api-relay` (ID: `dd1d33a7`)

| 平台 | 绑定方式 | 绑定值 |
|------|---------|--------|
| Claude | `group:claude` | group `1e88fabe`，成员：fish, 尼日利亚 |
| Gemini | `group:gemini` | group `12e31ab4`，成员：1 个账号 |
| ~~OpenAI~~ | ~~单账号 `charlotte`~~ | ~~`ba317690`~~ |
| OpenAI（已改） | `group:openai` | group `088b2996`，成员：songxin.jack, jas, aaron, sean, charlotte（5 个账号） |

**2026-03-26 操作记录**：将 `openaiAccountId` 从 `ba317690`（charlotte 单账号）改为 `group:088b2996-2468-4368-b0e5-6adac17e2a26`（openai group）。

执行命令：
```bash
docker exec claude-relay-service-redis-1 redis-cli hset \
  'apikey:dd1d33a7-6ab9-477b-a126-ef1bf978fe69' \
  openaiAccountId 'group:088b2996-2468-4368-b0e5-6adac17e2a26'
```

### CRS sticky session 实现分析（源码阅读）

CRS 有完整的 sticky session 实现，**三条链路（OpenAI/Claude/Gemini）各自独立**：

#### OpenAI 链路

- 入口：`/app/src/routes/openaiRoutes.js`
- Scheduler：`/app/src/services/scheduler/unifiedOpenAIScheduler.js`
- session hash 提取优先级：
  1. `req.headers['session_id']`
  2. `req.headers['x-session-id']`
  3. `req.body?.session_id`
  4. `req.body?.conversation_id`
  5. `req.body?.prompt_cache_key`
- 提取到的值经 SHA256 hash 后作为 sticky key
- Redis key：`unified_openai_session_mapping:{hash}`
- TTL：`config.session.stickyTtlHours`（默认 1 小时）

调度逻辑（`selectAccountForApiKey`）：
1. 如果 key 绑了 `group:xxx`，走 `selectAccountFromGroup(groupId, sessionHash, ...)`
2. 如果有 sessionHash，先查 Redis 映射 → 命中则复用（+ TTL 续期）→ 未命中则从 group 选新账号
3. 选新账号时按 priority 排序（`sortAccountsByPriority`）
4. 限流检测：`_ensureAccountReadyForScheduling` 检查 Redis 限流标记 + schedulable 状态
5. 限流时自动删除映射，重选账号

#### Claude 链路

- 入口：`/app/src/routes/openaiClaudeRoutes.js`
- Scheduler：`/app/src/services/scheduler/unifiedClaudeScheduler.js`（结构类似）
- session hash 提取：`/app/src/utils/sessionHelper.js`
  1. **最高优先级**：从 `metadata.user_id` 提取 `session_id`（通过 `metadataUserIdHelper`）
  2. 次级：带 `cache_control: {"type": "ephemeral"}` 的内容 hash
  3. Fallback：system 内容 hash → 第一条消息 hash
- `metadataUserIdHelper.js` 兼容两种格式：
  - 新格式 (v2.1.78+)：`{"device_id":"...","account_uuid":"...","session_id":"..."}`
  - 旧格式：`user_{deviceId}_account_{accountUuid}_session_{sessionId}`
- Redis key：`unified_claude_session_mapping:{session_id}`
- 注意：Claude 链路直接用提取的 `session_id`（UUID 格式），不做额外 hash

### Redis 实时数据验证（2026-03-26 15:52 UTC+8）

#### newapi 侧（redis 容器）

```
# channel_affinity 缓存
new-api:channel_affinity:v1:codex cli trace:coding:019d2876-... → 11  (channel 11, TTL ~500s)
new-api:channel_affinity:v1:claude cli trace:coding:{...}      → 12  (channel 12)
```

#### CRS 侧（claude-relay-service-redis-1 容器）

```
# OpenAI sticky（改 group 后新产生）
unified_openai_session_mapping:8932e14e... → {"accountId":"ef732306-...","accountType":"openai"}
unified_openai_session_mapping:88e33cc6... → {"accountId":"dbce190b-...","accountType":"openai"}  # aaron

# Claude sticky（一直在工作）
unified_claude_session_mapping:8654082f-3fdb-406a-8be7-5e4610e6910c
  → {"accountId":"38d395ef-...","accountType":"claude-official"}  # fish
  TTL: 2854s
```

### 测试请求验证

```bash
# OpenAI Codex 请求（改 group 后）
curl -X POST http://127.0.0.1:3000/openai/v1/responses \
  -H 'Authorization: Bearer cr_bb46...' \
  -H 'Session_id: test-sticky-openai-group-001' \
  -H 'User-Agent: codex_cli_rs/0.1.0' \
  -d '{"model":"gpt-5.4","stream":true,"input":[...],"instructions":"be brief","prompt_cache_key":"test-sticky-openai-group-001"}'
# 结果：成功返回 response.created，CRS 从 openai group 中选择账号并建立 sticky 映射
```

CRS 日志确认：
```
🎯 API key new-api-relay is bound to group 088b..., selecting from group
👥 Selecting account from group: openai (openai)
🎯 Created new sticky session mapping: ... for session test-sticky-openai-group-001
```

### 两层 sticky 并存关系

当前 newapi 和 CRS 的 sticky **同时在工作**，但职责不同：

```
newapi channel_affinity          CRS unified scheduler
        ↓                              ↓
粘到 channel（如 12）              粘到账号（如 fish）
key: gjson 从 body 取             key: session_id 从 header/body 取
存 Redis (newapi redis)           存 Redis (CRS redis)
TTL: 3600s                        TTL: 3600s (1h)
```

在单 channel + group 模式下，newapi 的 channel_affinity 实际上是"空转"（只有一条 channel 可选），**真正有效的 sticky 是 CRS 层的**。

---

## 目标

要实现的不是"永远固定一个账号"，而是：

- 新 session 第一次进入时，可以在多个 OpenAI 账号之间动态分配
- 同一个 session 进入后，要稳定粘到同一个 OpenAI 账号
- 只有新 session、主动 drain、或账号异常时，才切到别的账号

## 当前推荐方案：CRS group sticky

> 2026-03-26 更新：经服务器验证后，推荐此方案替代原方案。

### 架构

```
client → newapi (channel) → CRS (single key, group:xxx) → OpenAI account
                                     ↑
                              CRS scheduler 负责：
                              1. session → account 映射
                              2. 限流自动摘除
                              3. 新 session 按优先级分配
```

### 配置方式

1. CRS 侧：一把 key 绑定 `group:xxx`（group 包含多个 OpenAI 账号）
2. newapi 侧：一条 channel 指向 CRS，确保 header 透传即可
3. CRS scheduler 自动完成：session hash 提取 → Redis 映射 → 粘性路由

### 为什么比原方案更好

| | CRS group sticky（当前推荐） | newapi 多 channel（原方案） |
|---|---|---|
| 运维复杂度 | 低 — 一条 channel，一把 key | 高 — N 条 channel，N 把 key |
| 账号感知 | CRS 直接知道限流/异常，自动摘除重选 | newapi 只知道 channel 返回错误 |
| 加减账号 | CRS group 里增删成员即可 | 要建 key + channel + param_override + group |
| 可观测性 | CRS 日志直接打出账号名和 sticky 命中 | 要关联 newapi channel ID + CRS 日志 |
| prompt cache | 同 session 粘同账号 | 同效果 |

### newapi 透传要求（不需要特殊设置）

只要满足以下条件，newapi 就是纯透传，不需要额外配置：

1. `pass_through_body_enabled = false`（当前所有 CRS channel 已满足）
2. header 透传生效 — 有两种途径：
   - channel 自身配了 `param_override.pass_headers`（channel 8, 11）
   - channel_affinity 规则匹配后自动注入 `ParamOverrideTemplate`（channel 10, 12）
3. `metadata.user_id` 不被改写成对象

当前所有 channel 均已满足，**不需要做任何改动**。

### 账号管理

#### 加新账号

在 CRS 管理面板把新账号加入对应 group 即可。新 session 会自动被分配到新账号。

#### 摘除异常账号

CRS 自动处理：
- 限流时自动删除 sticky 映射，重选其他账号
- 也可以手动在 CRS 管理面板将账号设为 `not schedulable`

#### 查看当前 sticky 映射

```bash
# OpenAI
docker exec claude-relay-service-redis-1 redis-cli keys 'unified_openai_session_mapping:*'

# Claude
docker exec claude-relay-service-redis-1 redis-cli keys 'unified_claude_session_mapping:*'

# 查看具体映射到哪个账号
docker exec claude-relay-service-redis-1 redis-cli get 'unified_openai_session_mapping:{hash}'
```

---

## ~~原方案：newapi 多 channel sticky~~（已不推荐）

> 以下为原始文档内容，保留供参考。经 2026-03-26 服务器验证后，此方案不再推荐，原因见上方。

### ~~结论先说~~

~~当前最稳、最容易运维、也最容易解释的问题分层是：~~

1. ~~`CRS API key` 只绑定一个固定的 OpenAI OAuth 账号~~
2. ~~`newapi channel` 只使用一把固定的 `CRS API key`~~
3. ~~同模型能力建多条 `newapi channel`~~
4. ~~把这些 channel 放进同一个 `group`~~
5. ~~开启 `channel_affinity`，让同一 session 粘到首次成功的 channel~~

~~这样粘住的其实是 `channel`，但因为一条 `channel` 背后只接一把 `CRS key`，而一把 `CRS key` 又只绑定一个 OpenAI 账号，所以最终效果就是"当前 session 粘住一个 OpenAI 账号"。~~

### ~~不推荐的做法~~

> 2026-03-26 注：此节原始结论已被推翻。CRS 的 group sticky 实现是完备的，并非"不推荐"。

~~不要用下面这种结构：~~

- ~~一把 `CRS key`~~
- ~~这把 key 绑定 `group:*`~~
- ~~再让 `CRS` 内部 scheduler 动态选 OpenAI 账号~~

~~原因：~~

- ~~`newapi` 只能稳定粘 `channel`~~
- ~~它粘不住 `CRS` 里 `group:*` 内部的具体账号~~
- ~~这样即使 `newapi` sticky 生效，`CRS` 内部仍可能把同一 session 派到不同 OpenAI 账号~~
- ~~上下文、prompt cache、response storage 都会变得不稳定~~

**实际验证结果**：CRS 内部有完整的 `unified_*_session_mapping` 机制（Redis 持久化 + TTL 续期 + 限流自动摘除），只要 session 标识头（`session_id` / `metadata.user_id`）能透传到 CRS，CRS 就能稳定粘到同一个账号。所谓"CRS 内部仍可能把同一 session 派到不同账号"的担忧不成立。

### ~~推荐拓扑~~

~~以 3 个 OpenAI 账号为例：~~

#### ~~CRS 层~~

- ~~`crs-key-codex-a` -> 绑定 `openai-account-a`~~
- ~~`crs-key-codex-b` -> 绑定 `openai-account-b`~~
- ~~`crs-key-codex-c` -> 绑定 `openai-account-c`~~

~~规则：~~

- ~~一把 key 只绑一个账号~~
- ~~不要绑 `group:*`~~
- ~~不要在活跃 session 期间随意把 key 改绑到别的账号~~

#### ~~newapi 层~~

- ~~`channel: crs-codex-a`~~
  - ~~`base_url = http://.../openai`~~
  - ~~`api_key = crs-key-codex-a`~~
- ~~`channel: crs-codex-b`~~
  - ~~`base_url = http://.../openai`~~
  - ~~`api_key = crs-key-codex-b`~~
- ~~`channel: crs-codex-c`~~
  - ~~`base_url = http://.../openai`~~
  - ~~`api_key = crs-key-codex-c`~~

~~然后把这些 channel 放进同一个可对外暴露的模型组，例如：~~

- ~~`group = codex_pool`~~

~~对外同事只打：~~

- ~~`newapi -> group codex_pool`~~

### ~~权重和切流建议~~

~~首次分配由 `weight` / `priority` 决定。~~

~~推荐规则：~~

- ~~主账号：`weight` 高一点~~
- ~~备账号：`weight` 中等~~
- ~~保底账号：`weight` 低一点~~

~~例如：~~

- ~~`crs-codex-a`: `weight = 10`~~
- ~~`crs-codex-b`: `weight = 6`~~
- ~~`crs-codex-c`: `weight = 3`~~

### ~~账户快满时怎么做~~

~~要区分"新 session 切流"和"老 session 维持"。~~

#### ~~只想让新 session 不再进入某账号~~

~~做法：~~

- ~~把对应 channel `weight` 调低到 `0`~~
- ~~或直接 `disable channel`~~

~~效果：~~

- ~~已经粘住该 channel 的旧 session，仍可能继续使用~~
- ~~新 session 不再分配到这条 channel~~

#### ~~想彻底 drain 某账号~~

~~做法：~~

1. ~~先把对应 channel `weight = 0`~~
2. ~~等待已有 session 自然结束~~
3. ~~再停用该 channel 或改绑 CRS key~~

~~不要直接把：~~

- ~~`crs-key-codex-a`~~

~~从 `openai-account-a` 硬切到 `openai-account-b`~~

~~否则已经 sticky 到该 channel 的 session 会在不中断 session key 的前提下，被你静默换到底层账号，最容易出现上下文错位。~~

---

## newapi 必须注意的配置点

> 以下内容仍然适用，无论使用哪种 sticky 方案。

这是本轮已经踩过的坑。

### 1. `pass_through_body_enabled` 必须是 `false`

如果对应 channel 开了：

- `setting.pass_through_body_enabled = true`

会导致 `newapi` 跳过 `ApplyParamOverrideWithRelayInfo(...)`，从而让下面这些能力全部失效：

- `pass_headers`
- `sync_fields`
- `header -> json` 映射
- `channel_affinity` 的 `ParamOverrideTemplate` 自动注入

本轮 live 排障已经确认，这正是 `xin(4001)` 之前 header 透传失效的真实根因。

**2026-03-26 DB 确认**：channel 8/10/11/12 全部为 `false`。

### 2. `pass_headers` 要补齐 Codex 关键头

至少应包含：

- `User-Agent`
- `Originator`
- `Session_id`
- `X-Session-Id`
- `OpenAI-Beta`

**注意**：即使 channel 没有手动配 `param_override`，`channel_affinity` 的规则匹配后会自动注入对应的 `pass_headers`。当前 codex 规则自动注入：`Originator, Session_id, User-Agent, X-Codex-Beta-Features, X-Codex-Turn-Metadata`。Claude 规则自动注入：`X-Stainless-*, User-Agent, X-App, Anthropic-Beta, Anthropic-Version` 等。

### 3. `sync_fields` 需要把 session 信息写到 body

当前 `newapi` 的 `channel_affinity` 默认更偏向从请求体取 key source。

因此要确保：

- `header:session_id -> json:prompt_cache_key`

这一类映射能生效。

**补充说明**：这个映射对 CRS group sticky 方案也有意义。CRS 的 OpenAI 链路会从 `req.body?.prompt_cache_key` 提取 session hash（优先级第 5），所以 `sync_fields` 确保了 header 里的 session_id 能通过 body 到达 CRS。不过如果 header 透传正常（`Session_id` 直接到达 CRS），CRS 会从 `req.headers['session_id']`（优先级第 1）取值，`sync_fields` 此时是冗余保险。

### 4. `Claude metadata.user_id` 必须保持"字符串"格式

这次 live 排障确认，真实 `Claude CLI` 发的是：

- `metadata.user_id = "{\"device_id\":\"...\",\"account_uuid\":\"...\",\"session_id\":\"...\"}"`

不是：

- `metadata.user_id = { ... }`

如果中间层把它改成对象：

- 上游会直接报 `metadata.user_id: Input should be a valid string`
- `channel_affinity` 即使仍能取到值，语义也已经偏离真实 `Claude CLI`
- CRS 的 `metadataUserIdHelper.js` 解析也会失败（它 `JSON.parse` 的前提是输入为 string）

因此 `Claude -> newapi -> CRS` 的稳定要求里，要额外加一条：

- 不要把 `metadata.user_id` 从 string 改写成 object

## Sticky 的真实边界

### newapi 层

`newapi channel_affinity` 粘的是：

- `channel`

不是：

- `CRS 内部 openaiAccountId`

也不是：

- `OpenAI 官方 response id`

### CRS 层

CRS `unified_*_scheduler` 粘的是：

- `accountId`（具体的 OpenAI/Claude/Gemini 账号）

粘性 key：

| 链路 | key 来源 | Redis key 格式 |
|------|---------|---------------|
| OpenAI | `session_id` header → SHA256 hash | `unified_openai_session_mapping:{hash}` |
| Claude | `metadata.user_id` → 提取 `session_id`（UUID，不 hash） | `unified_claude_session_mapping:{session_id}` |

### 当前推荐方案下的 sticky 链路

```
1. client 把 session 标识带到 newapi（header 或 body）
2. newapi 透传 header 到 CRS（pass_headers / channel_affinity 自动注入）
3. CRS 从 header/body 提取 session hash
4. CRS Redis 查询映射 → 命中则粘到同一账号 → 未命中则选新账号并建立映射
```

~~所以要得到真正稳定的"账号粘连"，必须满足下面三层都稳定：~~

~~1. `MMS / client` 把 session 相关头带到 `newapi`~~
~~2. `newapi` 用这些信息稳定选中同一条 `channel`~~
~~3. `channel` 背后的 `CRS key` 始终绑定同一个 OpenAI 账号~~

在 CRS group sticky 方案下，只需要两层：

1. `MMS / client` 把 session 相关头带到 `newapi`
2. `newapi` 透传 header 到 CRS，CRS 用这些信息稳定粘到同一个账号

## ~~建议命名~~

> 2026-03-26 注：在 CRS group sticky 方案下，不需要 per-account 的 channel/key 命名。

~~建议直接把"用途 + 账号槽位"编码进名字里，方便运维：~~

- ~~`crs-codex-a`~~
- ~~`crs-codex-b`~~
- ~~`crs-codex-c`~~
- ~~`crs-chat-base-a`~~
- ~~`crs-chat-base-b`~~

~~对应 CRS key 也统一：~~

- ~~`crs-key-codex-a`~~
- ~~`crs-key-codex-b`~~
- ~~`crs-key-codex-c`~~

## 运维规则（更新版）

- ~~不要让一把 `CRS key` 绑定 `group:*`~~ → 推荐用 `group:xxx` 绑定
- 不要在活跃 session 上直接改 key 绑定关系（从 group 改到单账号或反过来）
- 某账号异常时：CRS 自动摘除限流账号；也可手动在 CRS 面板设为 not schedulable
- 加新账号：在 CRS group 里添加成员即可
- ~~需要迁移时，用"新 channel + 新 key + 新账号"替代"原 channel 改绑新账号"~~
- 任何 sticky 问题先查两层：
  1. `newapi → CRS`：header 是否透传（看 CRS 日志的 `User-Agent`）
  2. `CRS sticky`：Redis `unified_*_session_mapping:*` 是否存在且指向正确账号

## 最小验证清单

### 验证 header 透传

在 `CRS` 日志里确认看到：

- `User-Agent: codex_*`
- 不再是 `python-httpx/...` 或 `Go-http-client/1.1`

### 验证 sticky 生效

连续三次同一 session 请求，确认：

- ~~`newapi` 命中同一条 channel~~ （单 channel 模式下无需验证）
- `CRS` Redis 中 `unified_*_session_mapping:*` 映射存在
- 映射指向同一个 `accountId`
- `Claude` 场景下，确认 `metadata.user_id` 在日志里仍是字符串，不是对象

```bash
# 快速验证命令
docker exec claude-relay-service-redis-1 redis-cli keys 'unified_openai_session_mapping:*'
docker exec claude-relay-service-redis-1 redis-cli keys 'unified_claude_session_mapping:*'
```

### 验证限流摘除

将某个账号标记为限流后确认：

- CRS 自动删除该账号的 sticky 映射
- 后续请求被分配到其他健康账号
- 限流解除后账号重新加入调度池

### ~~验证切流（原方案）~~

~~把某条 channel `weight = 0` 后确认：~~

- ~~旧 session 还能继续~~
- ~~新 session 会落到别的 channel~~

## 当前已确认的现网事实

截至 2026-03-26：

- `xin(4001)` 背后是定制版 `newapi`（容器 `new-api-custom`）
- 之前 header 透传失败的真正原因是 `pass_through_body_enabled=true`
- 修正为 `false` 后，下游 private `CRS` 已重新识别为 `codex_cli_rs/...`
- ~~当前 `new-api-relay` 已先临时绑到单账号 `charlotte`~~ → 已改为 `group:openai`（5 个账号）

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

2026-03-26 追加确认：

- OpenAI 链路改为 `group:openai` 后，CRS sticky 立即生效
- Redis 中出现 `unified_openai_session_mapping` 条目，映射到 group 内不同账号
- Claude 链路不受影响，`unified_claude_session_mapping` 仍正常工作
- 两层 sticky（newapi channel_affinity + CRS unified scheduler）并存运行，互不干扰

~~这是短期兜底，不是长期最优结构。~~

~~长期还是建议按本文档拆成：~~

- ~~多 `CRS key`~~
- ~~多 `newapi channel`~~
- ~~单 key 单账号~~
- ~~`channel_affinity` 做 session sticky~~

**当前结构已是推荐的长期方案**：CRS group sticky + newapi 透传。无需再拆分为多 key 多 channel。
