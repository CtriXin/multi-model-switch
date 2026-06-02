# Adapter Registry

这份文档记录的是 **MMS 当前默认维护的前 10 个来源公司/品牌**，不是具体模型清单。

目的只有两个：

1. 给后续接新来源时一个统一基线。
2. 固化 `official OAuth / provider API / claude bridge` 的默认策略，避免不同 worktree 各自发明一套。

对应代码常量见：

- [`mms_registry/adapter_registry.py`](../mms_registry/adapter_registry.py)

直接在 CLI 查看：

```bash
./mms config adapter.registry
```

兼容别名：

```bash
./mms config source.registry
```

## 默认策略

- `official OAuth`：如果某个来源已经有稳定的官方 CLI、SDK 或 backend，可新增原生账号 adapter。
- `claude bridge`：只要某个 `official OAuth` adapter 已经稳定，默认还应支持在 `claude` 里复用。
- `provider API`：如果某个来源没有稳定的原生 CLI/OAuth 路径，默认按 `provider` 接入，不强做 bridge。
- `明确模型 -> 再选来源`：当用户已经选中了具体模型，只展示真正能承载这个模型的来源。

## Top 10 来源

| # | 公司 / 品牌 | 代表模型族 | 当前推荐 adapter | MMS 当前状态 | 原生 OAuth | `claude bridge` 默认要求 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Anthropic / Claude | `claude-*` | `official_native` | 已支持 | 是 | 否，目标 CLI 本身就是 `claude` |
| 2 | OpenAI / GPT / Codex | `gpt-*` / `o*` / `codex-*` | `official_native + claude_bridge` | 已支持 | 是 | 是 |
| 3 | Google / Antigravity / Gemini | `gemini-*` | `official_native` via `agy` + `provider_api` | 已支持 `agy` 官方入口；Gemini CLI 退为 legacy | 是 | 否，默认不再走 Gemini CLI bridge |
| 4 | Alibaba Cloud / Qwen | `qwen-*` / `qwen3-*` | `provider_api` | 已支持 provider 路径 + 来源模板 | 否 | 否 |
| 5 | Moonshot / Kimi | `kimi-*` | `provider_api` | 已支持 provider 路径 + 来源模板 | 有原生登录能力，但未接 adapter | 是，后续若补 OAuth |
| 6 | MiniMax CN | `minimax-*` / `minimax-m*` | `provider_api` | 规划中 | 否 | 否 |
| 7 | MiniMax EN | `minimax-*` / `minimax-m*` | `provider_api` | 规划中 | 否 | 否 |
| 8 | Z.ai / GLM | `glm-*` | `provider_api` | 已支持来源模板 | 否 | 否 |
| 9 | BigModel / 智谱 / GLM | `glm-*` | `provider_api` | 已支持来源模板 | 否 | 否 |
| 10 | Volcengine / 火山引擎 / Doubao | `doubao-*` / `seed-*` | `provider_api` | 规划中 | 否 | 否 |

## 为什么不是所有来源都先做 OAuth

当前默认维护的官方 / bridge 路径：

- `claude <- codex`
- Google 官方入口改走 `agy`，Gemini CLI bridge 不再作为默认维护路径

这些路径能成立，是因为对应来源都满足至少一条：

- 有稳定的官方 CLI/backend
- 有可复用的官方 SDK/core package

而 Qwen、Kimi、MiniMax、Z.ai、智谱、火山这几类来源，当前更稳的接法还是：

- 先走 `provider API`
- 只把它们当模型源，不把它们硬扭成官方桥接

## 当前结论

### 已经稳定的原生来源

- `Claude`
- `Codex`
- `Antigravity CLI (agy)`

### 当前维护的 `claude bridge`

- `codex OAuth -> claude`
- 不再新增 Gemini CLI OAuth bridge；Google 官方入口集中到 `agy`

### 当前优先按 provider 落地的来源

- `Qwen`
- `Kimi`
- `MiniMax CN`
- `MiniMax EN`
- `Z.ai`
- `BigModel / 智谱`
- `Volcengine / Doubao`

### 当前已经提供来源模板的 provider

- `qwen`
- `kimi`
- `zai-glm`
- `bigmodel-glm`

## 后续新增来源时的执行规则

1. 先判断它是不是有稳定的官方 CLI / SDK / backend。
2. 如果有，优先补 `official OAuth`。
3. 一旦 `official OAuth` 稳定，再默认评估是否应补 `claude bridge`。
4. 如果没有稳定原生路径，直接按 `provider_api` 接，不要先做脆弱 bridge。
5. 任何来源接入后，都要把状态更新回这个 registry。

## 参考链接

### 已支持或已确认的官方路径

- OpenAI Codex CLI:
  - https://developers.openai.com/codex/cli
- Antigravity CLI:
  - https://antigravity.google/docs/cli-getting-started
  - https://antigravity.google/docs/gcli-migration
- Claude Code:
  - https://www.anthropic.com/claude-code
  - https://docs.anthropic.com/en/docs/claude-code/quickstart

### 当前更适合按 provider 参考的来源

- Qwen:
  - https://qwen.ai/
  - https://coder.qwen.ai/
- Kimi:
  - https://www.kimi.com/coding/en
  - https://www.kimi.com/coding/docs/en/
  - https://www.kimi.com/code/docs/en/third-party-agents.html
- MiniMax:
  - https://www.minimax.io/en
  - https://www.minimax.io/news/mini-pricemax-performance%E5%85%B3%E4%BA%8Eapi%E7%BC%96%E7%A8%8B%E5%A5%97%E9%A4%90%E5%92%8Cagent
  - https://www.minimax.io/news/minimax-m2
  - https://www.minimax.io/news/minimax-m25
- Z.ai:
  - https://docs.z.ai/
  - https://docs.z.ai/guides/llm/glm-4.6
  - https://docs.z.ai/devpack/extension/usage-query-plugin
- BigModel / 智谱:
  - https://docs.bigmodel.cn/cn/guide/develop/claude/introduction
  - https://docs.bigmodel.cn/cn/guide/develop/openai/introduction
  - https://docs.bigmodel.cn/
- Volcengine / 火山引擎:
  - https://www.volcengine.com/
  - https://developer.volcengine.com/

## 备注

- 这里的“前 10”是当前项目维护优先级，不是任何公开榜单的绝对排名。
- 这里按“公司 / 品牌”维度记录，不按模型数量计数。
- 同一家公司下所有同品牌模型，默认视作同一个来源维护单元。
