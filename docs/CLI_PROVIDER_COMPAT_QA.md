# CLI / Provider 兼容性排障 Q&A

> 更新时间：2026-03-25
> 范围：`claude` / `codex` / `qwen` / `kimi` 与当前本地 provider 配置

## 背景

这轮问题最初表现为：

- `xin` / `privateopenai` 在 Codex 下使用 GPT 时返回 `502`
- 进入 `mms` 模型选择明显变慢
- 手工补模型后，provider / CLI 可见性和真实可用性不一致

排查后确认，问题并不是单一根因，而是多层问题叠加：

1. bridge fallback 缓存会把可用的 Responses provider 误锁死到 Chat Completions
2. path-prefixed gateway 的 URL 兼容不完整
3. probe 负缓存和 fallback 模型结果没有落盘，导致反复慢探测
4. Codex 交互模式下本地 `responses bridge` 起在父 Python 进程里，但随后被 `exec` 覆盖，bridge 自己先死了
5. provider 选项层会把“当前 CLI 下根本没有可选模型”的 provider 也展示出来，污染 TUI

---

## 已修复问题

### 1. `Codex + GPT + provider` 返回 502，但 gateway 本身是通的

**表象**

- `codex` 被注入到 `http://127.0.0.1:xxxxx/v1`
- 随后报 `502 Bad Gateway` / 本地 bridge 连接失败

**真实根因**

`launch_codex()` 在起本地 `responses bridge` 后，交互模式仍然直接 `exec` 成 `codex` 进程。
bridge 线程挂在原 Python 进程里，父进程一旦被 `exec` 覆盖，bridge 一起消失。

**修复**

- 文件：[mms_launchers.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_launchers.py#L1269)
- 做法：Codex 走 `responses bridge` 时强制 `force_subprocess=True`，保持父 Python 进程活着托管 bridge

**如何确认**

- 新会话下 `codex` 能访问本地 bridge `/v1/models` / `/v1/responses`
- `xin + gpt-5.4`、`privateopenai + gpt-5.4` 的真实 `codex exec` smoke 已通过

---

### 2. `privateopenai` 明明支持 `/responses`，却被错误降级到 `/chat/completions`

**表象**

- 本地看到的是 `/openai/chat/completions` 或 `/openai/v1/chat/completions`
- 实际可用链路应该是 `/openai/responses` 或 `/openai/v1/responses`

**真实根因**

- 历史 `bridge_mode_cache.json` 用字符串缓存 `privateopenai:gpt-5.4 -> chatcompletions`
- 旧逻辑会无条件信任这条旧缓存
- 一旦 fallback 到错误 path，就把本来可用的 `/responses` 路由打坏

**修复**

- 文件：[mms_bridge.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_bridge.py#L67)
- 做法：
  - fallback cache 改为带时间戳的结构
  - 不再信任历史字符串缓存
  - `/responses` 成功后自动清掉该 `(provider, model)` 的 fallback 标记
  - fallback 只在明确“不支持 Responses API”时触发

---

### 3. 进入模型选择非常慢

**表象**

- 每次进入 provider / model 选择页都会重复卡在 probe
- `provider_debug.log` 反复出现 `cached_models=None, probing...`

**真实根因**

- 之前只有“远端成功且有非空模型列表”才写 probe 文件缓存
- 失败结果、空列表、`fallback_models` 都不会落盘
- 导致每次进入选择页都要重试慢请求

**修复**

- 文件：[mms_core.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_core.py#L2358)
- 做法：
  - 增加负缓存 TTL
  - 失败/空模型结果写盘
  - `fallback_models` 结果也写盘

---

### 4. 当前 CLI 下没有任何可选模型的 provider 仍然出现在选项里

**表象**

- `qwen` / `kimi` 会出现一批空 provider
- TUI 选项不干净，影响后续交互设计

**修复**

- 文件：[mms_core.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_core.py#L3299)
- 做法：`_provider_options_for_model()` 在 `option_models` 为空时直接跳过该 provider

### 5. `Codex -> MMS -> CRS/newapi` 会丢失 Codex 标识头，导致上游把请求当成普通 `httpx` 客户端

**表象**

- 同样连续问三次 `hi`，同事后台 `input` 只有十几到几百，而本地链路经常每次都很大
- private CRS 日志里出现：
  - `ua = python-httpx/0.28.1`
  - `Non-Codex CLI request detected, applying Codex CLI adaptation`
- `cache read` / prompt cache 命中行为与同事链路明显不一致

**真实根因**

`_ResponsesProxyHandler` 以及它内部的 `chat/completions fallback` 之前只往上游转发：

- `Content-Type`
- `Authorization`

原始请求里的这些关键头全丢了：

- `User-Agent`
- `originator`
- `session_id`
- `x-session-id`
- `openai-beta`

这样一来，CRS / newapi 上游只能看到本地 bridge 发出的 `python-httpx` 请求，无法继续把它识别成原始 `Codex CLI` 客户端。

**修复**

- 文件：[mms_bridge.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_bridge.py#L51)
- 做法：
  - 为 `responses proxy` 增加白名单式 header 透传
  - 同时覆盖内部 `chat/completions fallback`
  - 只补传客户端标识头，不改现有 gateway 鉴权逻辑

**如何确认**

- private / company / newapi 的上游日志里，`ua` 应从 `python-httpx/...` 变成 `codex_*`
- `Non-Codex CLI request detected` 这类日志应消失或明显减少
- 如果上游本身支持 prompt cache / response storage，后续请求的缓存命中机会会提升

---

## Q&A

### Q1：为什么 `gateway 可达`，但 `mms / codex` 还是 502？

A：先分清是“上游可达”还是“本地 bridge 存活”。

- 上游可达：说明 provider 本身没挂
- 本地 502：通常说明 `mms -> 本地 bridge -> 上游` 这条链中间有问题

这次最关键的 502 根因不是上游，而是：

- bridge 启动在父 Python 进程里
- 交互模式把父进程 `exec` 成了 `codex`
- bridge 自己被替换掉，`codex` 再访问 `127.0.0.1:port` 当然失败

---

### Q2：为什么 `privateopenai` / `companycrsopenai` 会出现在 `claude` provider 列表里，但实际不通？

A：当前代码对 `claude` 的 provider 可见性仍然偏宽，只要 provider 声明支持 `claude` 且有模型，就可能进入选项。

但 `claude` 真正能不能通，还取决于：

- 是否真的支持 `Anthropic Messages`
- 或者在 `Anthropic` 探测失败后，是否能正确降级到 OpenAI bridge

当前已知现状：

- `privateopenai`：`claude` smoke 返回 `404 ... /openai/v1/messages`
- `companycrsopenai`：`claude` smoke 返回 `504 ... /openai/v1/messages`

这说明“可见”不等于“真兼容”。

---

### Q3：为什么 `privateopenai` 对 `codex` 能通，但对 `claude` 不通？

A：两条链路不是一回事。

- `codex` 走的是 OpenAI / Responses / Chat Completions 兼容链
- `claude` 默认优先走 Anthropic Messages 链

`privateopenai` 本质更像 OpenAI provider：

- 对 `codex` 的本地 bridge 兼容已经修好
- 对 `claude`，当前仍会落到 `Messages` 探测/直连逻辑，不一定能正确降级

---

### Q4：为什么模型选择会“第一次慢，第二次快”？

A：这是 probe 文件缓存是否命中的直接结果。

- 第一次：会真实探测 provider
- 第二次：命中文件缓存，基本就是本地读 JSON

当前已修复后，本地验证 `_provider_options_for_model(...)` 命中文件缓存时耗时约 `0.008s`。

---

### Q5：后续新 provider 出问题，先看什么？

A：先按这个顺序：

1. `provider_debug.log`
2. `bridge_error.log`
3. `bridge_mode_cache.json`
4. `~/.config/mms/cache/models_<provider>.json`

重点判断：

- 是 provider probe 慢 / 失败
- 是 Responses 被误 fallback
- 还是本地 bridge 生命周期问题

---

### Q5.1：现在这条 `private / privateopenai / newapi / CRS` 链路有没有“保险窗口”？

A：有，已经正式写进仓库规则。

入口文档：

- [AGENTS.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/AGENTS.md)
- [docs/AGENT_GUARDRAILS.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/AGENT_GUARDRAILS.md)

当前被放进保险窗口的链路：

- `MMS -> private(/claude) -> CRS`
- `MMS -> privateopenai(/openai) -> CRS`
- `MMS -> xin/newapi(4001) -> CRS`

只要改动会碰到下面任一项，就必须先确认是否会影响这条链路：

- `models_endpoint`
- `extra_models` / `hidden_models`
- probe / cache / fallback
- `channel_affinity`
- `Codex` / `Claude` header 透传
- `/claude`、`/openai`、`/responses`、`/models` 协议假设

---

### Q5.2：以后我要自己在服务器追溯、复现 smoke test，看哪份文档？

A：直接看这份 runbook：

- [docs/PRIVATE_CRS_SMOKETEST_RUNBOOK.md](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/docs/PRIVATE_CRS_SMOKETEST_RUNBOOK.md)

它已经包含：

- `private(/claude)` 的最小 `models` / `messages` smoke
- `privateopenai(/openai)` 的 `manual` 模式验证
- `xin/newapi(4001)` 的 sticky / header 验证
- CRS / newapi 的日志与数据库追溯命令

如果有人改了这条链路，却没有更新这份 runbook，默认就视为验证闭环不完整。

---

### Q6：`crs -> newapi` 这条链，最终暴露给 `Codex` 的是 `Responses` 还是 `Chat Completions`？

A：以 2026-03-25 的 live 实验和 `82.156.121.141` 机器实查结果看，`xin(4001)` 背后确实是一个定制过的 `new-api`，而且它对 `Codex` 这类 GPT 模型已经显式暴露了 `Responses` 路由。

本次确认到的事实：

- `82.156.121.141:4001` 对应容器：`new-api-custom`
- 机器上同时还跑着原版 `new-api-original`，端口是 `4000`
- 源码里明确存在 `/responses` 路由：
  - `/opt/new-api/src/newapi-src/router/relay-router.go`
  - `/opt/new-api/src/newapi-src/relay/responses_handler.go`
- 源码里还存在 `chat completions via responses` 的转换逻辑：
  - `/opt/new-api/src/newapi-src/relay/chat_completions_via_responses.go`

因此这条链路的结论不是“二选一”，而是：

- `Responses`：原生支持，`Codex` 可以直接打
- `Chat Completions`：也支持，但服务端内部可以再转成 `Responses`

这和当前 live probe 结果一致：

- `xin`（`http://82.156.121.141:4001`）：
  - `POST /responses`：`200`
  - `POST /chat/completions`：`200`
- `newapi`（`https://chat.adsconflux.xyz/openapi/v1`）：
  - `POST /responses`：能进路由，但本次返回 `402 upstream_error`
  - `POST /chat/completions`：同样能进路由，也返回 `402 upstream_error`
  - `POST /v1/...`：`404`，因为 base URL 本身已经自带 `/v1`

如果问题是“Codex 过 newapi 时应该按哪条协议理解”，当前答案是：

- 从 `Codex` 视角，应优先按 `Responses` 理解

---

### Q7：`Claude -> newapi -> CRS` 现在 sticky 到底有没有生效？

A：有，而且已经做了 live 验证。

2026-03-25 我用固定 `metadata.user_id` 连续 3 次请求：

- 入口：`http://82.156.121.141:4001/v1/messages?beta=true`
- `User-Agent: claude-cli/2.1.81 (external, sdk-cli)`
- `x-app: cli`
- `model: claude-sonnet-4-20250514`
- `metadata.user_id = "{\"device_id\":\"dev-codex-test\",\"account_uuid\":\"acct-coding-1\",\"session_id\":\"sess-sticky-claude-001\"}"`

CRS 日志确认三次都命中同一个 sticky 账号：

- `Created new sticky session mapping in group: fish ... for session sess-sticky-claude-001`
- `Using sticky session account from group: ... (claude-official) for session sess-sticky-claude-001`

同 3 次请求的 `usage` 也稳定一致：

- `input_tokens = 22`
- `cache_creation_input_tokens = 0`
- `cache_read_input_tokens = 0`

结论：

- `newapi -> CRS` 这段 `Claude sticky` 已经正常
- 但最小 `hi` 请求并不会天然出现 `prompt cache read`
- 所以“是否有 cache read”不能单独拿来判断 sticky 是否失效

---

### Q8：为什么我自己构造 `metadata.user_id` 时一开始总是 400？

A：因为 `Claude` 这里要求的是“字符串”，不是对象。

这次 live 排障踩到的真实坑是：

- 错误写法：
  - `"metadata": { "user_id": { "device_id": "...", "session_id": "..." } }`
- 正确写法：
  - `"metadata": { "user_id": "{\"device_id\":\"...\",\"session_id\":\"...\"}" }`

CRS 日志里的上游报错非常明确：

- `metadata.user_id: Input should be a valid string`

这点很关键，因为：

- `newapi channel_affinity` 默认也正是从 `gjson:metadata.user_id` 取 sticky key
- 如果格式被中间层改成 object，轻则上游 400，重则 sticky key 语义和真实 Claude CLI 不一致

---

### Q9：为什么直连 `CRS /claude` 时，有些 key 会报 `Invalid API key format`？

A：因为 `/claude` 入口先过的是 CRS 自己的 API key 校验，它要求 key 必须带本机配置的固定前缀。

本次远端实查到：

- 代码：`/app/src/services/apiKeyService.js`
- 校验逻辑：`apiKey.startsWith(this.prefix)`
- 当前 prefix：`cr_`

也就是说：

- 能否被 `newapi` 当 channel key 用
- 能否被客户端直接拿去打 `CRS /claude`

不是一回事。

当前现网 `channel 12` 的 key：

- `cr_bb46fe98ed6a160e9b233aca6a38a5195aeb510ecd5ce4bec370ebec9a08212c`

它格式上符合 `cr_` 前缀，因此可以作为 CRS 自己的 relay key。

但如果你手上拿的是：

- OAuth access token
- 其他平台生成的 bearer token
- 不带 `cr_` 前缀的中间层 key

那直接打 `/claude` 就会在 CRS 认证中间件里先被拒掉，根本还没到账号选择阶段。

---

### Q10：`Claude` 这条链除了 sticky，还有什么额外兼容点最容易出问题？

A：至少还有 4 个：

1. `User-Agent` 必须保留 `claude-cli/x.y.z` 形态。CRS 里有专门的 `ClaudeCodeValidator` 检查它。
2. `x-app`、`anthropic-beta`、`anthropic-version` 不能丢。缺任一项，都可能不再被识别为真实 `Claude Code`。
3. `metadata.user_id` 必须存在且格式合法。它既影响客户端识别，也影响 sticky key。
4. `pass_through_body_enabled` 不能开成 `true`。否则 `newapi` 的 `pass_headers` / `sync_fields` / `channel_affinity` param override 可能全部失效。

本轮修复后，`Claude -> newapi -> CRS` 的关键识别头已经能透传；当前剩余风险不在“头丢了”，而在：

- 是否用了错误格式的 `metadata.user_id`
- 是否把并不属于 CRS 的 token 拿去直连 `/claude`
- `new-api` 只是同时保留了 `Chat Completions` 兼容入口

---

### Q7：为什么同样只发一个 `hi`，后台看到的 `input` 还是很大？能不能删？

A：`hi` 本身几乎不占 token，大头来自 `Codex` 启动时自动拼进去的上下文。

当前会进入请求的主要部分：

1. `Codex CLI` 自带 `base_instructions`
   - 当前抽样 session 里约 `14101` chars
2. harness / permissions / tools schema
   - 包括 shell 工具、approval 规则、输出格式要求等
3. 全局 `AGENTS.md`
   - `~/.codex/AGENTS.md`
4. 当前项目 `AGENTS.md`
   - 本仓库 `AGENTS.md`
5. 当前会话 developer 注入的 skills 列表
   - 你本机安装了大量 skills，当前环境里会把“可用技能清单 + 触发规则”一并注入
6. 当前会话已有历史消息、图片、任务上下文

同一份抽样里，另外还能量化到：

- developer 注入约 `10754` chars
- 当前项目 `AGENTS.md` 包装消息约 `3895` chars

这也解释了为什么你后台会看到：

- `input` 很大
- 但重复问同样的话时，`cache read` 也会很大

因为真正可缓存的，恰恰是这些固定前缀。

可以安全裁剪的部分：

- `~/.codex/AGENTS.md`
  - 会全局生效；能精简，但别删掉你真正在乎的约束
- 仓库里的 `AGENTS.md`
  - 会随项目注入；可以缩短 bootstrap 描述，减少重复规则
- 未使用的 skills
  - 当前本机 skills 很多，而且有跨目录重复项；删掉不用的 skill，session 里的技能列表会变短

不建议动的部分：

- `Codex CLI` 自带 `base_instructions`
  - 这是 CLI/harness 自带，不是 MMS 自己额外塞的
- tools schema / approval 规则
  - 少了这些，agent 基本就没法正常工作

结论上：

- “一个 `hi` 为什么这么大”主要是 `Codex` 自带上下文，不是 `MMS` 单独放大
- 真正最值得先减的是两类：
  - 过长的 `AGENTS.md`
  - 没在用但还挂着的 skills

---

### Q8：为什么同样三次 `hi`，同事 `input` 只有十几到几百，而我这边每次都还是很大？

A：目前看，不是单一原因，但关键差异已经明确有两层：

1. 你本地 `Codex` 仍然关闭了 response storage
   - `~/.codex/config.toml`
   - `~/.config/mms/codex-gateway/.../.codex/config.toml`
   - 两边当前都是 `disable_response_storage = true`
2. 你的 `privateopenai` / `xin` 上游链路都不接受 `previous_response_id`
   - 这意味着它们虽然暴露了 `/responses`
   - 但并不支持真正的 server-side conversation continuation

所以对你这条链来说，后续轮次大概率仍要把那一大段固定前缀重新发上去，自然就会继续看到“大 input”。

同事那种“后续只发很小 delta”的表现，通常意味着上游链路真的支持：

- `previous_response_id`
- 或者等价的 server-side continuation / response storage

---

### Q9：为什么 `company` 会命中 `cache read`，而 `private` 不会？

A：这件事不能只看“是不是同样问了三次 `hi`”，还要看上游把请求当成什么类型。

当前已经确认的 private 问题有两层：

1. **MMS 本地 bridge 之前会丢客户端标识头**
   - 上游看到的是 `python-httpx/0.28.1`
   - 不是原始 `Codex CLI`
2. **private CRS 当前命中的账户链路不是 `openai-responses`，而是普通 `openai`**
   - private CRS 代码里普通 `openai` 链路会把 `store = false`
   - 这条路本来就不是“真正的 response storage relay”

因此 private 当前“不读缓存 / 不像同事那样极小 input”是符合现状的。

`company` 那边之所以能看到 `cache read`，更可能是它的 CRS / 上游账户配置本来就支持 prompt cache 或 response storage，而不是因为你这边 `Codex` 文本更小。

---

### Q10：如果目标是像同事那样让后续 `input` 很小，是不是还要改 CRS？

A：是，**只改 MMS 不够**。

这轮 MMS 修复解决的是第一层问题：

- 把 `User-Agent` / `originator` / `session_id` 这些头透传上去
- 让上游至少能看见“这原本是个 `Codex` 请求”

但如果你要的是更强的效果：

- 真正使用 `previous_response_id`
- 后续轮次只传很小 delta
- 稳定的 server-side continuation

那还需要 CRS / newapi 侧满足至少一项：

1. 账户链路走 `openai-responses` 或等价的 storage-capable relay
2. 上游明确支持 `previous_response_id`
3. 服务端没有把 `store` 强制改成 `false`

所以答案是：

- **第一步修 MMS：要做，而且已经做**
- **第二步改 CRS / 账户路由：如果要达到同事那种效果，也要做**

---

### Q11：`MMS -> newapi -> CRS` 这条链，也会丢失那些 header 吗？

A：如果第一跳 `MMS` 就没透传，那后面的 `newapi` / `CRS` 自然也拿不到。

这也是为什么这轮先修 `MMS bridge`。

额外确认到的一点是：`newapi` 自定义版源码里，确实已经有这类 override / 映射能力，例如：

- `header:session_id -> json:prompt_cache_key`
- `originator = codex_cli_rs`

但前提仍然是：它得先收到这些 header。第一跳没了，后面无法“凭空恢复原始 Codex 身份”。

补充一个 2026-03-25 的 live 结论：

- `MMS -> privateopenai(/openai) -> CRS`
  - 这条链已经确认修好
  - private CRS 日志能看到 `User-Agent: codex_cli_rs/...`
  - `cache read` 也已经重新出现
- `MMS -> xin(newapi 4001) -> CRS`
  - 这条链的第一跳 `MMS` 已修好
  - 一开始 `newapi-custom` 运行中的实际转发仍然让 CRS 看到 `User-Agent: Go-http-client/1.1`
  - 继续排查后确认，真正卡点不是 `param_override` JSON，而是：
    - channel `8/11` 都配置了 `pass_through_body_enabled = true`
    - 这会在 `responses_handler.go` 里跳过 `ApplyParamOverrideWithRelayInfo(...)`
    - 导致 `pass_headers/sync_fields` 根本不会执行
  - 把 `8/11` 的 `pass_through_body_enabled` 改成 `false` 后，live 验证已恢复：
    - `Authenticated request from key: new-api-relay`
    - `User-Agent: "codex_cli_rs/0.116.0"`
    - `✅ Codex CLI request detected, forwarding as-is`
    - `Using bound dedicated openai account: charlotte (...) for API key new-api-relay`

所以当前更精确的结论是：

- `privateopenai` 的问题，这轮主要是 `MMS` 问题，已经修复
- `xin/newapi` 这条链最终也修通了，但中间真实根因是：
  - `newapi` channel 开了 `pass_through_body_enabled`
  - 导致 `param_override` 根本没执行
  - 所以头透传失效
- 到这一刻为止，这轮**没有修改 CRS 源码**，只改了：
  - 本地 `MMS`
  - 远端 `newapi` channel 配置
  - 远端 `CRS` 里 `new-api-relay` 这把 key 的账号绑定

---

### Q12：CRS 里 `codex app` / `codex cli` 是怎么识别的？能不能直接“识别成 app”？

A：按这轮查到的 private CRS 代码看，目前**没有单独的 `codex_app` client type**。

它识别的核心仍然是 `Codex CLI family`，主要依赖：

- `User-Agent`
  - 例如 `codex_vscode/...`
  - `codex_cli_rs/...`
  - `codex_exec/...`
- `originator`
- `session_id`
- body 里的 `instructions` 特征

所以“识别成 app”在这套 CRS 代码里并不是单独一条新类型，更像是：

- 只要请求特征像 `Codex family`
- 就会被归到对应 validator / adaptation 逻辑里

换句话说，现在最应该先修的不是“伪装成 app”，而是确保上游先看到原始 `Codex` 特征头。

---

### Q13：为什么 `newapi` 明明已经配了 `param_override.pass_headers`，private CRS 还是只看到 `Go-http-client/1.1`？

A：因为这次真正的拦路点不是 `param_override` JSON 本身，而是 channel setting：

- `channels.id in (8,11)` 当时都带着：
  - `setting.pass_through_body_enabled = true`
- 在 `newapi` 源码里：
  - `relay/responses_handler.go`
  - 只要全局 `PassThroughRequestEnabled` 或 channel `PassThroughBodyEnabled` 为真
  - 就会直接透传原 body
  - 并跳过 `ApplyParamOverrideWithRelayInfo(...)`

这意味着：

- `pass_headers`
- `sync_fields`
- `header:session_id -> json:prompt_cache_key`

这些规则虽然“配上了”，但实际上完全没有运行。

本次真正修复 `xin(4001)` 的动作是：

1. 保留 `8/11` 上的合法 `param_override`
2. 把 `8/11` 的 `pass_through_body_enabled` 改成 `false`
3. 保留 `new-api-relay -> charlotte` 的单账号绑定

改完后，private CRS 日志已确认：

- `Authenticated request from key: new-api-relay`
- `User-Agent: "codex_cli_rs/0.116.0"`
- `✅ Codex CLI request detected, forwarding as-is`

也就是说，`newapi -> CRS` 这一跳现在已经不再丢失原始 Codex 身份。

### Q14：如果想要“动态绑定多个 OpenAI 账户，但同一 session 粘在一个账户上”，应该怎么做？

A：当前最短、最稳、最可控的路径，不是让单把 CRS key 自己在 group 里乱调度，而是：

1. 在 CRS 里准备多把 API key
   - 每把 key 直接绑定一个明确的 `openaiAccountId`
   - 不要再绑 `group:...`
2. 在 newapi 里建多条同模型 channel
   - `base_url` 都指向同一个 CRS `/openai`
   - 但每条 channel 使用不同的 CRS API key
3. 让这些 channel 进入同一个 `group`
   - 用 `weight/priority` 控制初次分配概率
4. 利用 `newapi` 自带的 `channel_affinity`
   - 它会按请求特征把同一类请求粘到第一次成功的 channel

这套方案的好处是：

- **同一 session**：会继续命中同一个 newapi channel
- **同一个 newapi channel**：背后就是同一把 CRS key
- **同一把 CRS key**：再固定到同一个 OpenAI OAuth 账户

这样就能得到你要的效果：

- 当前会话期间稳定指向一个 OpenAI 账户
- 不会在多账户之间乱跳，导致上下文和 cache 失真
- 新 session 才有机会重新分到别的账户
- 某个账户快满时，可以通过调低权重、禁用对应 channel、或切新 CRS key 来迁移新 session

注意一个关键前提：

- `channel_affinity` 粘的是 **channel**
- 不是直接粘 `CRS` 里的 `openaiAccountId`

所以如果你未来想做“动态但会话粘连”的分流，**多 channel + 多 CRS key + 单账号绑定** 是当前最简单可落地的架构。

### Q15：`Claude` 也有类似“头没透传”的风险吗？

A：有，但这轮已经先补了第一层最关键的 `MMS -> 上游 gateway/CRS` 透传。

当前 `Claude bridge` 已补传：

- `User-Agent`
- `x-app`
- `anthropic-version`
- `anthropic-beta`
- `anthropic-dangerous-direct-browser-access`
- `X-Stainless-*`

补丁位置：

- 文件：[mms_bridge.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_bridge.py#L51)

这组头不是凭空猜的，而是结合两类信息定的：

- 当前本机安装的 `Claude Code 2.1.81` 二进制里能直接搜到：
  - `x-app`
  - `anthropic-dangerous-direct-browser-access`
  - `X-Stainless-Arch`
  - `X-Stainless-Lang`
  - `X-Stainless-OS`
  - `X-Stainless-Package-Version`
  - `X-Stainless-Runtime`
  - `X-Stainless-Runtime-Version`
  - `X-Stainless-Retry-Count`
  - `X-Stainless-Timeout`
  - `X-Stainless-Helper-Method`
- 官方 Anthropic API 文档能确认：
  - `anthropic-version`
  - `anthropic-beta`

但这里仍要分清边界：

- **对 Claude -> MMS -> CRS(/claude or /messages)**：
  - `MMS` 这一跳已经不再把请求降格成单纯的 `python-httpx` 指纹
  - 但还不能直接宣称“与官方 Claude Code 完全等价”
- **要不要继续怀疑 CRS / newapi 本身**
  - 仍要看它们是否继续保留这些头
  - 尤其是中间层如果再次改写 header/body，client fingerprint 还是会失真

如果你关心风控、封号、或 cache 识别，这轮补丁是必要条件，但不是全部条件。

### Q16：现在 `MMS` 直连 `CRS`，能不能理解成“约等于官方 Codex CLI + OAuth 登录”的效果？

A：对 **Codex 直连 OpenAI 型 CRS**，可以理解成“已经接近”，但还不能说“完全等价”。

已经接近的部分：

- 上游能重新看到原始 `Codex CLI` 特征头
- CRS 已会按 `Codex CLI request` 逻辑处理
- `privateopenai(/openai)` 和现在修好的 `xin(newapi 4001)` 都能重新命中这条识别链

还不完全等价的部分：

- CRS 仍可能对 body 做自己的改写
  - 例如某些路由会把 `store=false`
- 是否支持真正的 `previous_response_id` continuation
  - 仍取决于 CRS 路由、账号池类型、以及 response storage 设计
- `Claude` 路由当前还没有补齐类似等级的 header 透传

所以更准确的表述是：

- `Codex -> MMS -> CRS(/openai)`：已经接近官方 `Codex CLI + OAuth` 的客户端识别效果
- 但还不是“所有 server-side 行为都与官方直连完全一致”

### Q17：`newapi` 的 `channel_affinity` 到底在哪里配置？

A：有两层入口。

**1. 运行时配置入口**

- Web 管理页组件：
  - `/opt/new-api/src/newapi-src/web/src/pages/Setting/Operation/SettingsChannelAffinity.jsx`
- 对应 option key：
  - `channel_affinity_setting.enabled`
  - `channel_affinity_setting.switch_on_success`
  - `channel_affinity_setting.max_entries`
  - `channel_affinity_setting.default_ttl_seconds`
  - `channel_affinity_setting.rules`

**2. 默认值源码**

- `/opt/new-api/src/newapi-src/setting/operation_setting/channel_affinity_setting.go`

当前默认规则里：

- `codex cli trace`
  - `path_regex = /v1/responses`
  - `key_sources = gjson:prompt_cache_key`
- `claude cli trace`
  - `path_regex = /v1/messages`
  - `key_sources = gjson:metadata.user_id`

本轮远端实查 `82.156.121.141` 的 `options` 表后确认：

- 当前没有任何 `channel_affinity_setting%` 的数据库覆写项
- 所以 `new-api-custom(4001)` 现在实际跑的是**源码默认规则**

### Q18：`Claude` 这边除了 header 透传，还有什么真实会出问题的点？

A：这轮继续实测后，确认过 3 个具体坑，其中 2 个已经能确定会命中官方 `Claude Code`。

**问题 1：`oauth_bridge` 原来不接受 `?beta=true`**

真实 `Claude Code 2.1.81` 发出的路径是：

- `POST /v1/messages?beta=true`

但原来的 `_BridgeHandler` 只接受精确：

- `/v1/messages`

结果就是：

- `codex_claude_bridge`
- `gemini_claude_bridge`

这两条 `oauth_bridge` 分支会直接 `404 not found`。

这轮已修复：

- 文件：[mms_bridge.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_bridge.py#L893)
- 现在会先剥离 query string 再匹配路径

**问题 2：`oauth_bridge` 原来没有 `/v1/models`**

原来的 `_BridgeHandler` 没有实现：

- `GET /v1/models`

本地实测返回的是：

- `501 Unsupported method`

这会在某些 `Claude Code` 模型校验场景下留下隐患。

这轮已修复：

- 文件：[mms_bridge.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_bridge.py#L883)
- 现在会返回当前 bridge 暴露的模型列表

**问题 3：`gateway_claude_bridge` 对 `/v1/responses?beta=true` 的翻译不完整**

原来的翻译只处理精确：

- `/v1/responses`

如果带 query：

- `/v1/responses?beta=true`

会在本地 bridge 直接 `404`。

虽然当前抓到的官方 `Claude Code 2.1.81` 主路径还是：

- `/v1/messages?beta=true`

但这个点依然属于兼容性缺口。

这轮已修复：

- 文件：[mms_bridge.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_bridge.py#L1138)
- 现在会在保留 query string 的前提下，把 `/v1/responses` 正确翻译成 `/v1/messages`

### Q19：`newapi` 默认给 `Claude` 做 sticky 的 `metadata.user_id` 真的是官方请求里会带的吗？

A：是，而且这轮已经用本机 `Claude Code 2.1.81` 直接抓包确认。

本地真实请求表现为：

- 路径：
  - `POST /v1/messages?beta=true`
- body 顶层包含：
  - `metadata`
- 其中：
  - `metadata.user_id`

实际是一个 JSON 字符串，里面带：

- `device_id`
- `account_uuid`
- `session_id`

而且在同一个显式 `--session-id` 下重复请求时，抓到的 `metadata.user_id` 保持一致。

这说明 `newapi` 默认规则里的：

- `gjson:metadata.user_id`

并不是拍脑袋写的，它确实能作为 `Claude` session sticky 的 key source 使用。

---

## 本地 smoke 结果（2026-03-25）

> 说明：
> - 这里只记录“当前代码 + 当前本地配置 + 最小请求”的结果
> - `504`、`余额不足`、`模型不存在` 优先视为上游/provider 问题，不直接归因于本地代码

### Claude

可用：

- `xin`
- `newapi`
- `kimi-codingplan`
- `glm-en`
- `bailian-codingplan`
- `minimax-cn`

失败：

- `private`：`404 model not found`
- `companycrs`：`504`
- `companycrsopenai`：`504`
- `privateopenai`：`404 /openai/v1/messages`

补充观察（2026-03-25 23:20）：

- `private(/claude)` 的 `/v1/models` 实际返回的是 Anthropic 的 dated model id，例如：
  - `claude-sonnet-4-20250514`
  - `claude-sonnet-4-5-20250929`
  - `claude-opus-4-20250514`
  - `claude-opus-4-5-20251101`
- 它不会直接广告 `claude-sonnet-4-6` / `claude-opus-4-6`
- MMS 已在本地 probe patch 层补出这两个 alias，避免 provider 列表里只看到 dated id、不方便直接选择

### Codex

可用：

- `xin`
- `newapi`
- `bailian-codingplan`
- `privateopenai`

失败：

- `glm-en`：`429 insufficient balance`
- `minimax-cn`：`timeout`
- `private`：`404 /claude/v1/chat/completions`
- `companycrs`：`504`
- `companycrsopenai`：`504`

补充观察（2026-03-25 15:00-15:20）：

- `privateopenai`
  - 原生 `POST /responses` 已确认 `200`
  - 清掉 `~/.config/ccs/cache/bridge_mode_cache.json` 的旧 fallback 后，重复请求已重新出现 `cache read`
  - 说明此前“不读缓存”大概率是被旧的 `chatcompletions` fallback 污染
  - 如果本身就不提供 `/openai/v1/models`，推荐把该 provider 的 `models_endpoint` 设为 `manual`
  - 这样 MMS 会直接使用手工补充模型，跳过远端 `/models` 探测，减少进入模型选择时的空等
- `companycrsopenai`
  - 本次直接 probe：
    - `/responses` 返回 `429`
    - `/v1/chat/completions` 返回 `200`
  - 这更像是上游 CRS 当前限流 / 配额状态，而不是本地 bridge 协议不兼容
- `xin`
  - `4001` 背后是 `new-api-custom`
  - 明确支持 `/responses`
  - 初始阶段现网虽然 `POST /v1/responses` 能通，但 private CRS 日志仍显示：
    - `Authenticated request from key: new-api-relay`
    - `User-Agent: "Go-http-client/1.1"`
  - 继续排查后确认真实根因：
    - `channel 8/11` 的 `pass_through_body_enabled=true`
    - 让 `param_override` 完全失效
  - 把 `pass_through_body_enabled` 改成 `false` 后，private CRS 已恢复看到：
    - `User-Agent: "codex_cli_rs/0.116.0"`
    - `✅ Codex CLI request detected, forwarding as-is`
  - 说明这条链当前已经恢复到“按原始 Codex CLI 身份被 CRS 识别”的状态

- `xin -> private CRS` 的 stickiness
  - 已将 `new-api-relay` 从 `openaiAccountId = group:088b...` 改为直接绑定：
    - `ba317690-ee89-4d22-8d7d-ef9f65209283`
    - `charlotte`
  - 变更前备份：
    - `/tmp/new-api-relay-apikey-before-stickiness-20260325-210703.txt`
  - 改后 CRS 日志已出现：
    - `Using bound dedicated openai account: charlotte (...) for API key new-api-relay`
  - 这一步已经解决“newapi 过去后每次动态换 OpenAI OAuth 账户”的问题

### Qwen

可用：

- `xin`
- `newapi`
- `bailian-codingplan`

失败 / 不建议暴露：

- `kimi-codingplan`：`403 only available for coding agents`
- 其余 provider 当前在 `qwen` 侧无有效模型或返回错误，不应在 TUI 中展示为可选

### Kimi

可用：

- `xin`
- `newapi`
- `bailian-codingplan`

失败 / 待确认：

- `kimi-codingplan`：API 级 smoke 返回 `403 only available for coding agents`
  - 这不等于真实 `kimi` 官方 CLI 一定不可用
  - 但说明“裸 OpenAI 请求模拟”不足以代表该 provider 的官方 CLI 行为

---

## 给后续 TUI 的实现建议

### 1. provider 可见性不要只看 `supported_clis`

至少要再加一层：

- 当前 CLI 下是否有 `option_models`

否则会出现“能看到 provider，但一点进去没有任何真实可选模型”的噪音项。

### 2. “测试连接”要拆层

建议分成两种动作：

- `测试 provider`：检查探测、协议、缓存、基础连通性
- `测试 CLI 启动`：走真实 launch 路径 smoke 一次

不要把两者合成一个按钮，否则：

- `companycrs*` 这种慢 504 provider 会拖垮交互
- 用户也无法判断是“provider 挂了”还是“CLI 启动链有 bug”

### 3. 区分“代码问题”和“上游问题”

建议 TUI 里给状态打标签：

- `local_bug`
- `provider_config`
- `upstream_error`
- `quota_or_auth`

这样排障路径会短很多。

---

## 常用排障文件

- `~/.config/ccs/cache/provider_debug.log`
- `~/.config/ccs/cache/bridge_error.log`
- `~/.config/ccs/cache/bridge_mode_cache.json`
- `~/.config/mms/cache/models_<provider>.json`

---

## 常用排障结论速记

- `Responses 可用但被误 fallback`：优先看 `bridge_mode_cache.json`
- `进入选模很慢`：优先看 `models_<provider>.json` 有没有生成
- `gateway 可达但 Codex 502`：优先排查本地 bridge 生命周期
- `provider 出现在列表但 CLI 不通`：优先看该 CLI 下是否真的有兼容模型/协议

---

## 已知未修限制

### Claude 对 openai-only provider 的自动降级仍不完整

当前 `claude` 链路里，以下 provider 仍属于“列表可见，但真实启动不一定能通”的已知限制：

- `privateopenai`
- `companycrsopenai`

原因不是这轮修过的 Codex bridge，而是 `launch_claude()` 的降级条件还不够严格：

- provider 配置里如果带了 `anthropic_base_url`
- 但该地址实际并不能稳定提供 `Anthropic Messages`
- 现有分支不会把它识别成“应降级到 OpenAI bridge 的 openai-only provider”

结果就是：

- `codex` 现在可以通过 OpenAI bridge 正常走 GPT
- `claude` 仍可能继续落到 `/v1/messages` 链路，出现 `404 /openai/v1/messages` 或 `504`

这部分当前已记录为后续单独修复项，不包含在本轮 commit 内。

---

### Q20：`MMS` 隔离环境里，`ssh` / `gitconfig` / `skills` 现在会带进来吗？skill 里还能再起一个 `mms` 吗？

A：会，而且这轮又补了一层“防套娃”。

当前 `MMS` 的隔离 session 里：

- `.ssh`
- `.gitconfig`
- `.gitignore_global`
- `~/.codex/skills`

都会继续从真实用户目录映射进去，所以：

- 隔离 session 里的 `git` / `ssh` 可用
- `Codex` 还能继续看到全局安装的 skills
- skill 里技术上可以再调用一次 `mms`

但之前有一个隐患：

- 第一层 `MMS` 会把 `HOME` 切到 `~/.config/mms/.../s/<pid>`
- 如果第二层 `mms` 再从这个 `HOME` 推导“真实家目录”
- 就会继续在 session 里面套 session，路径越来越深

这轮已经在 launcher 里补了：

- `MMS_REAL_HOME`
- `ORIGINAL_HOME`
- `REAL_HOME`
- `GH_CONFIG_DIR`
- gateway 路径下回源真实 `XDG_CONFIG_HOME`

现在的规则是：

- 第一层 `MMS` 启动时显式把真实 home 传下去
- 后续不管是子 skill、还是第二层 `mms`
- 共享资源都优先从 `MMS_REAL_HOME` 回源，而不是再从当前隔离 `HOME` 继续推导
- 像 `gh` 这类依赖 `~/.config` 的工具，会通过回源提示读到真实用户配置

补丁位置：

- 文件：[mms_launchers.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/mms_launchers.py)

因此当前的结论是：

- “隔离环境里 ssh / git / skills 带不过来”这个问题，已经不是现状
- “skill 里再起一个 mms 会不会继续套娃”这个问题，这轮也已经在 `MMS` 侧收住了

但仍建议把“skill 里再起 `mms`”主要用于：

- one-shot 命令
- 辅助 smoke
- 短链路调试

不要默认把它当成长期、深层嵌套的主工作流。
