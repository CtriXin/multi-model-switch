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

- 文件：[ccs_launchers.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/ccs_launchers.py#L1269)
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

- 文件：[ccs_bridge.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/ccs_bridge.py#L67)
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

- 文件：[ccs_core.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/ccs_core.py#L2358)
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

- 文件：[ccs_core.py](/Users/xin/auto-skills/CtriXin-repo/multi-model-switch/ccs_core.py#L3299)
- 做法：`_provider_options_for_model()` 在 `option_models` 为空时直接跳过该 provider

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
