> Provenance: copied from `/Users/xin/auto-skills/CtriXin-repo/moebius/docs/30-mms-model-capability-calibration.md` on 2026-05-22.
> Purpose: MMS-owned reference snapshot for registry/source-truth design. Treat as evidence input, not runtime truth.
> Update rule: refresh through explicit registry/reference refresh workflow; do not edit generated facts by hand without adding source notes.

# MMS Model Capability Calibration

Generated: `2026-05-21T16:54:05.613316Z`

Scope: current MMS route aliases plus local selectors. Values are official-first; provider catalogs are stored separately as reference evidence.

## Summary

- total: `40`
- official_exact_or_base_alias: `35`
- needs_official_alias_evidence: `3`
- official_partial: `2`
- one_million_yes: `19`
- vision_yes_or_image: `22`
- thinking_yes: `33`
- thinking_control_captured: `33`
- official_max_output_captured: `16`
- openrouter_referenced: `33`
- openrouter_catalog_total_models_at_capture: `358`

## Gate Rules

- Only `official_exact*`, `official_base_local_*`, and `official_product*` rows may seed installer defaults.
- `needs_official_alias_evidence` rows must not be shown as official calibrated support, even if OpenRouter has provider-catalog metadata.
- `supports_thinking=True` is only a coarse gate. If official docs expose `thinkingLevel`, `thinkingBudget`, `thinking.type`, `reasoning.effort`, or another knob, store it in `thinking_control`.
- Gemini 3 / 3.1 / 3.5 use `thinkingLevel`; numeric `thinkingBudget` ranges in Google docs apply to Gemini 2.5 series, not current Antigravity Gemini 3 rows.
- `[1m]`, `(high)`, `(medium)`, `(low)`, `-thinking`, `-medium`, `-openai-canary`, and draw-size suffixes are local selectors/aliases unless official docs use that exact model id.
- Direct model vision and plan/tool-level vision are different: Vision MCP or separate VLM models must not make a text-model row `supports_vision=True`.
- OpenRouter is a `provider_catalog_reference`: good for route ids, context, max output, supported parameters, and price snapshots; it does not silently overwrite `official_*` fields.

## Reference Source Contract

- `vendor_official`: fills `official_*`, `supports_*`, exact thinking knobs, and official capabilities.
- `provider_catalog`: fills `provider_*`, route ids, route-specific context/max output, pricing, architecture, and `supported_parameters`.
- `runtime_observed`: confirms live health but cannot by itself raise a row to official capability support.
- `local_alias`: explains MMS suffix/selector mapping; never treat suffixes as vendor model IDs without source evidence.

## Capability Field Contract

- `official_context_window_tokens`: official context/input token limit; leave `unknown` if not exact.
- `official_max_output_tokens`: official max output token limit; leave `unknown` if not exact.
- `supports_vision`: direct model vision/image support only; plan-level MCP/tool vision belongs in notes or `official_capabilities`.
- `supports_thinking`: coarse installer gate; exact control belongs in `thinking_control`.
- `thinking_control.control_type`: official knob such as `thinkingLevel`, `thinkingBudget`, `thinking.type`, `reasoning.effort`.
- `thinking_control.allowed_values/default/requested_value`: preserve official/default/local selector values separately.
- `thinking_control.numeric_budget_tokens` / `budget_range_tokens`: fill only when official docs expose numeric budgets.
- `provider_catalog_references.openrouter.pricing_raw_usd_per_unit`: raw OpenRouter API values in USD per token/request/unit.
- `provider_catalog_references.openrouter.pricing_usd_per_million_tokens`: derived only for token-priced keys, not image/request/web_search/audio unit prices.
- `provider_catalog_mismatch_notes`: keep official-vs-provider discrepancies visible instead of resolving them silently.

## Models

| Alias | Canonical | Confidence | Context | Max output | 1M | Vision | Thinking | Thinking control | OpenRouter reference | Notes |
|---|---|---:|---:|---:|---|---|---|---|---|---|
| `anthropic/claude-opus-4.7` | `claude-opus-4.7` | `official_exact_with_provider_prefix` | `500000` | `unknown` | `False` | `True` | `True` | type=unknown_or_provider_default | anthropic/claude-opus-4.7; $5 in / $25 out per 1M tokens; ctx=1000000; max_out=128000 | OpenRouter prefix is provider routing; canonical Anthropic model is Claude Opus 4.7. |
| `claude-opus-4-6-thinking` | `claude-opus-4-6` | `official_base_local_alias` | `1000000` | `128000` | `True` | `True` | `True` | type=unknown_or_provider_default | anthropic/claude-opus-4.6; $5 in / $25 out per 1M tokens; ctx=1000000; max_out=128000 | Antigravity 官方 Models 页列出 Claude Opus 4.6 (thinking)；Anthropic 官方资料给出 Opus 4.6 及 1M context。`-thinking` 是本地 selector，不是 raw API id。 |
| `claude-sonnet-4-6` | `claude-sonnet-4-6` | `official_exact_with_product_source` | `1000000` | `64000` | `True` | `True` | `True` | type=unknown_or_provider_default | anthropic/claude-sonnet-4.6; $3 in / $15 out per 1M tokens; ctx=1000000; max_out=128000 | Antigravity 官方 Models 页列出 Claude Sonnet 4.6 (thinking)；Anthropic 官方模型页给出 `claude-sonnet-4-6` 及 context/output。 |
| `deepseek-v4-flash` | `deepseek-v4-flash` | `official_exact_modelstudio` | `1000000` | `unknown` | `True` | `False` | `True` | type=unknown_or_provider_default | deepseek/deepseek-v4-flash; $0.112 in / $0.224 out per 1M tokens; ctx=1048576 | Model Studio 官方模型表给出 deepseek-v4-* 1M context；DeepSeek 官网同时给出 deepseek-chat/reasoner 1M 作交叉参考。 |
| `deepseek-v4-pro` | `deepseek-v4-pro` | `official_exact_modelstudio` | `1000000` | `unknown` | `True` | `False` | `True` | type=unknown_or_provider_default | deepseek/deepseek-v4-pro; $0.435 in / $0.87 out per 1M tokens; ctx=1048576; max_out=384000 | Model Studio 官方模型表给出 deepseek-v4-* 1M context；DeepSeek 官网同时给出 deepseek-chat/reasoner 1M 作交叉参考。 |
| `deepseek-v4-pro[1m]` | `deepseek-v4-pro` | `official_base_local_selector` | `1000000` | `unknown` | `True` | `False` | `True` | type=unknown_or_provider_default | deepseek/deepseek-v4-pro; $0.435 in / $0.87 out per 1M tokens; ctx=1048576; max_out=384000 | [1m] 是 MMS selector，不应当当成官网 canonical model id。 |
| `gemini-3-flash-agent(high)` | `gemini-3-flash-preview` | `official_base_local_alias` | `1048576` | `65536` | `True` | `True` | `True` | type=thinkingLevel; alias=high; default=high (default, dynamic) | google/gemini-3-flash-preview; $0.5 in / $3 out per 1M tokens; ctx=1048576; max_out=65536 | Antigravity 官方 Models 页列出 Gemini 3 Flash；本地 `*-agent(...)` 是 CPA/MMS effort alias，不是 Google API canonical model id。 |
| `gemini-3-flash-agent(low)` | `gemini-3-flash-preview` | `official_base_local_alias` | `1048576` | `65536` | `True` | `True` | `True` | type=thinkingLevel; alias=low; default=high (default, dynamic) | google/gemini-3-flash-preview; $0.5 in / $3 out per 1M tokens; ctx=1048576; max_out=65536 | Antigravity 官方 Models 页列出 Gemini 3 Flash；本地 `*-agent(...)` 是 CPA/MMS effort alias，不是 Google API canonical model id。 |
| `gemini-3-flash-agent(medium)` | `gemini-3-flash-preview` | `official_base_local_alias` | `1048576` | `65536` | `True` | `True` | `True` | type=thinkingLevel; alias=medium; default=high (default, dynamic) | google/gemini-3-flash-preview; $0.5 in / $3 out per 1M tokens; ctx=1048576; max_out=65536 | Antigravity 官方 Models 页列出 Gemini 3 Flash；本地 `*-agent(...)` 是 CPA/MMS effort alias，不是 Google API canonical model id。 |
| `gemini-3.1-flash-image` | `gemini-3.1-flash-image-preview` | `official_base_local_alias` | `131072` | `32768` | `False` | `image_generation` | `True` | type=thinking on/off; default=not specified on model card | google/gemini-3.1-flash-image-preview; $0.5 in / $3 out per 1M tokens; ctx=131072; max_out=65536 | Google Gemini API 官方模型页列出 `gemini-3.1-flash-image-preview`；本地 alias 少 `-preview`，按 base local alias 校准为 image generation route。 |
| `gemini-3.1-flash-lite` | `gemini-3.1-flash-lite` | `official_exact` | `1048576` | `65536` | `True` | `True` | `True` | type=thinkingLevel; default=minimal | google/gemini-3.1-flash-lite; $0.25 in / $1.5 out per 1M tokens; ctx=1048576; max_out=65536 | Google Gemini API 官方模型页已有精确 `gemini-3.1-flash-lite`，可从 unknown 提升为 official_exact。 |
| `gemini-3.1-pro-low` | `gemini-3.1-pro-preview` | `official_base_local_alias` | `1048576` | `65536` | `True` | `True` | `True` | type=thinkingLevel; alias=low; default=high (default, dynamic) | google/gemini-3.1-pro-preview; $2 in / $12 out per 1M tokens; ctx=1048576; max_out=65536 | Antigravity 官方 Models 页列出 Gemini 3.1 Pro (low)；本地 alias 保留 low selector，canonical 能力按 Gemini 3.1 Pro Preview 校准。 |
| `gemini-3.5-flash-low` | `gemini-3.5-flash` | `official_base_local_alias` | `1048576` | `65536` | `True` | `True` | `True` | type=thinkingLevel; alias=low; default=medium | google/gemini-3.5-flash; $1.5 in / $9 out per 1M tokens; ctx=1048576; max_out=65536 | 当前 MMS preset `antigravity35-low` 使用该本地 alias；Antigravity 官方 Models/Plans 页列出 Gemini 3.5 Flash。 |
| `glm-5` | `glm-5` | `official_exact` | `200000` | `128000` | `False` | `False` | `True` | type=thinking.type; alias=enabled unless caller disables; default=enabled; forced thinking for GLM-5.1/GLM-5 | z-ai/glm-5; $0.6 in / $1.92 out per 1M tokens; ctx=202752 | BigModel/Z.ai 官方模型概览给出 200K context / 128K max output；深度思考页确认支持 `thinking.type`，无 numeric thinkingBudget；文本模型行不计 direct vision，Vision MCP/GLM-5V-Turbo 另算工具/视觉模型能力。 |
| `glm-5-turbo` | `glm-5-turbo` | `official_exact` | `200000` | `128000` | `False` | `False` | `True` | type=thinking.type; alias=enabled unless caller disables; default=enabled by default; auto/dynamic thinking according to deep-thinking docs | z-ai/glm-5-turbo; $1.2 in / $4 out per 1M tokens; ctx=202752; max_out=131072 | BigModel/Z.ai 官方模型概览给出 200K context / 128K max output；深度思考页确认支持 `thinking.type`，无 numeric thinkingBudget；文本模型行不计 direct vision，Vision MCP/GLM-5V-Turbo 另算工具/视觉模型能力。 |
| `glm-5.1` | `glm-5.1` | `official_exact` | `200000` | `128000` | `False` | `False` | `True` | type=thinking.type; alias=enabled unless caller disables; default=enabled; forced thinking for GLM-5.1/GLM-5 | z-ai/glm-5.1; $0.98 in / $3.08 out per 1M tokens; ctx=202752 | BigModel/Z.ai 官方模型概览给出 200K context / 128K max output；深度思考页确认支持 `thinking.type`，无 numeric thinkingBudget；文本模型行不计 direct vision，Vision MCP/GLM-5V-Turbo 另算工具/视觉模型能力。 |
| `gpt-5.3-codex` | `gpt-5.3-codex` | `needs_official_alias_evidence` | `unknown` | `unknown` | `unknown` | `unknown` | `unknown` |  | openai/gpt-5.3-codex; $1.75 in / $14 out per 1M tokens; ctx=400000; max_out=128000 | 未找到精确官方模型 ID 能证明该 alias；安装包不得猜测，必须保持 unknown 或要求 provider alias evidence。 |
| `gpt-5.3-codex-spark` | `gpt-5.3-codex-spark` | `needs_official_alias_evidence` | `unknown` | `unknown` | `unknown` | `unknown` | `unknown` |  |  | 未找到精确官方模型 ID 能证明该 alias；安装包不得猜测，必须保持 unknown 或要求 provider alias evidence。 |
| `gpt-5.4` | `gpt-5.4` | `official_exact` | `400000` | `unknown` | `False` | `True` | `True` | type=unknown_or_provider_default | openai/gpt-5.4; $2.5 in / $15 out per 1M tokens; ctx=1050000; max_out=128000 | 注意：当前 MMS lineup 写 1,000,000，需要按官方模型表降为 400,000。 |
| `gpt-5.4-mini` | `gpt-5.4-mini` | `official_exact` | `400000` | `unknown` | `False` | `True` | `True` | type=unknown_or_provider_default | openai/gpt-5.4-mini; $0.75 in / $4.5 out per 1M tokens; ctx=400000; max_out=128000 | 注意：当前 MMS lineup 写 1,000,000，需要按官方模型表降为 400,000。 |
| `gpt-5.5` | `gpt-5.5` | `official_exact` | `1048576` | `unknown` | `True` | `True` | `True` | type=unknown_or_provider_default | openai/gpt-5.5; $5 in / $30 out per 1M tokens; ctx=1050000; max_out=128000 | 校准为 OpenAI official model listing。 |
| `gpt-draw-1024x1024` | `gpt-image-2` | `official_base_local_alias` | `unknown` | `unknown` | `False` | `image_generation` | `False` |  |  | 尺寸 suffix 是本地 alias；official image model/context 不按 text context window 校准。 |
| `gpt-draw-1024x1536` | `gpt-image-2` | `official_base_local_alias` | `unknown` | `unknown` | `False` | `image_generation` | `False` |  |  | 尺寸 suffix 是本地 alias；official image model/context 不按 text context window 校准。 |
| `gpt-draw-1536x1024` | `gpt-image-2` | `official_base_local_alias` | `unknown` | `unknown` | `False` | `image_generation` | `False` |  |  | 尺寸 suffix 是本地 alias；official image model/context 不按 text context window 校准。 |
| `gpt-image-2` | `gpt-image-2` | `official_exact` | `unknown` | `unknown` | `False` | `image_generation` | `False` |  |  | Image generation/editing model；text context window/thinking 不适用。 |
| `gpt-oss-120b-medium` | `gpt-oss-120b` | `official_base_local_alias` | `131072` | `131072` | `False` | `False` | `True` | type=unknown_or_provider_default | openai/gpt-oss-120b; $0.039 in / $0.18 out per 1M tokens; ctx=131072 | Antigravity 官方 Models/Plans 页列出 GPT-OSS-120b；当前 MMS 将 `gpt-oss-120b-medium` 放在 Antigravity hidden models，作为本地 effort alias 记录。 |
| `K2.6` | `Kimi K2.6 / Kimi Code` | `official_exact_or_product_alias` | `262144` | `unknown` | `False` | `unknown` | `True` | type=unknown_or_provider_default | moonshotai/kimi-k2.6; $0.73 in / $3.49 out per 1M tokens; ctx=262144; max_out=262142 | Kimi Code 官方说明为 K2.6 thinking model，256K-token context；API/agent 模型面以 kimi-for-coding 暴露。 |
| `kimi-for-coding` | `kimi-for-coding` | `official_exact_or_product_alias` | `262144` | `unknown` | `False` | `unknown` | `True` | type=unknown_or_provider_default |  | Kimi Code 官方说明为 K2.6 thinking model，256K-token context；API/agent 模型面以 kimi-for-coding 暴露。 |
| `kimi-k2.5` | `Kimi K2.5 / Kimi Code` | `official_product_family` | `262144` | `unknown` | `False` | `unknown` | `True` | type=unknown_or_provider_default | moonshotai/kimi-k2.5; $0.4 in / $1.9 out per 1M tokens; ctx=262144; max_out=262144 | 按 Kimi Code 256K context 校准；精确 K2.5 文档证据不足时不要上调。 |
| `kimi-k2.6` | `Kimi K2.6 / Kimi Code` | `official_exact_or_product_alias` | `262144` | `unknown` | `False` | `unknown` | `True` | type=unknown_or_provider_default | moonshotai/kimi-k2.6; $0.73 in / $3.49 out per 1M tokens; ctx=262144; max_out=262142 | Kimi Code 官方说明为 K2.6 thinking model，256K-token context；API/agent 模型面以 kimi-for-coding 暴露。 |
| `mimo-v2.5` | `mimo-v2.5` | `official_exact` | `1048576` | `131072` | `True` | `True` | `True` | type=unknown_or_provider_default | xiaomi/mimo-v2.5; $0.4 in / $2 out per 1M tokens; ctx=1048576; max_out=131072 | MiMo docs state only mimo-v2.5 and mimo-v2-omni support image/audio/video input; thinking requires preserving reasoning_content. |
| `mimo-v2.5-pro` | `mimo-v2.5-pro` | `official_exact` | `1048576` | `131072` | `True` | `False` | `True` | type=unknown_or_provider_default | xiaomi/mimo-v2.5-pro; $1 in / $3 out per 1M tokens; ctx=1048576; max_out=16384 | 官方 schema lists max completion default 131072 for pro; multimodal input exception names only mimo-v2.5 and mimo-v2-omni, so pro is text-only for vision routing. |
| `mimo-v2.5-pro[1m]` | `mimo-v2.5-pro` | `official_base_local_selector` | `1048576` | `131072` | `True` | `False` | `True` | type=unknown_or_provider_default | xiaomi/mimo-v2.5-pro; $1 in / $3 out per 1M tokens; ctx=1048576; max_out=16384 | [1m] 不应发给官方 API；MMS 应在 wire alias 阶段剥离成 mimo-v2.5-pro。 |
| `MiniMax-M2.7` | `MiniMax-M2.7` | `official_partial` | `unknown` | `unknown` | `unknown` | `True` | `True` | type=unknown_or_provider_default | minimax/minimax-m2.7; $0.279 in / $1.2 out per 1M tokens; ctx=204800; max_out=131072 | 官方文档确认 MiniMax-M2.7 / 全模态 / thinking 示例；未找到官网精确 context window 数字，204800 只保留为 current_mms_context。 |
| `qwen3-coder-next` | `qwen3-coder-next` | `needs_official_alias_evidence` | `unknown` | `unknown` | `unknown` | `unknown` | `unknown` |  | qwen/qwen3-coder-next; $0.11 in / $0.8 out per 1M tokens; ctx=262144; max_out=262144 | 未找到精确官方模型 ID 能证明该 alias；安装包不得猜测，必须保持 unknown 或要求 provider alias evidence。 |
| `qwen3-coder-plus` | `qwen3-coder-plus` | `official_exact` | `1000000` | `unknown` | `True` | `False` | `True` | type=unknown_or_provider_default | qwen/qwen3-coder-plus; $0.65 in / $3.25 out per 1M tokens; ctx=1000000; max_out=65536 | Coder model按官方 text-generation/deep-thinking 资料校准；未列入 vision model。 |
| `qwen3.5-plus` | `qwen3.5-plus` | `official_exact` | `1000000` | `unknown` | `True` | `True` | `True` | type=unknown_or_provider_default | qwen/qwen3.5-plus-20260420; $0.3 in / $1.8 out per 1M tokens; ctx=1000000; max_out=65536 | Model Studio docs list Qwen3.5/3.6 plus as 1M, deep-thinking capable, and vision-capable in multimodal section. |
| `qwen3.6-plus` | `qwen3.6-plus` | `official_exact` | `1000000` | `unknown` | `True` | `True` | `True` | type=unknown_or_provider_default | qwen/qwen3.6-plus; $0.325 in / $1.95 out per 1M tokens; ctx=1000000; max_out=65536 | Model Studio docs list Qwen3.5/3.6 plus as 1M, deep-thinking capable, and vision-capable in multimodal section. |
| `qwen3.6-plus-openai-canary` | `qwen3.6-plus` | `official_base_local_alias` | `1000000` | `unknown` | `True` | `True` | `True` | type=unknown_or_provider_default | qwen/qwen3.6-plus; $0.325 in / $1.95 out per 1M tokens; ctx=1000000; max_out=65536 | -openai-canary 是本地协议测试 alias，不是官网模型 ID。 |
| `qwen3.8-max-preview` | `qwen3.8-max-preview` | `official_partial` | `unknown` | `unknown` | `unknown` | `unknown` | `True` | type=enable_thinking / reasoning.effort |  | 用户提供的 Model Studio 官方“文本生成”页确认该 ID、Token Plan 限定、Thinking 和 Function Calling；该页明确让精确 context 以模型广场为准，故不推断 1M、Vision 或 max output。 |

## OpenRouter Price / Unit Snapshot

OpenRouter `models` page and `/api/v1/models` are treated as provider catalog references. Raw values are USD per token/request/unit; token fields are additionally normalized to per-1M tokens.

| OpenRouter route | Used by alias | Provider ctx | Provider max output | Token prices | Non-token/unit prices | Supported parameters |
|---|---|---:|---:|---|---|---|
| `anthropic/claude-opus-4.6` | `claude-opus-4-6-thinking` | `1000000` | `128000` | prompt=$5/M tokens; completion=$25/M tokens; input_cache_read=$0.5/M tokens; input_cache_write=$6.25/M tokens | web_search=$0.01 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, max_completion_tokens, +5 more |
| `anthropic/claude-opus-4.7` | `anthropic/claude-opus-4.7` | `1000000` | `128000` | prompt=$5/M tokens; completion=$25/M tokens; input_cache_read=$0.5/M tokens; input_cache_write=$6.25/M tokens | web_search=$0.01 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +2 more |
| `anthropic/claude-sonnet-4.6` | `claude-sonnet-4-6` | `1000000` | `128000` | prompt=$3/M tokens; completion=$15/M tokens; input_cache_read=$0.3/M tokens; input_cache_write=$3.75/M tokens | web_search=$0.01 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, max_completion_tokens, +5 more |
| `deepseek/deepseek-v4-flash` | `deepseek-v4-flash` | `1048576` | `unknown` | prompt=$0.112/M tokens; completion=$0.224/M tokens; input_cache_read=$0.022/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +12 more |
| `deepseek/deepseek-v4-pro` | `deepseek-v4-pro`, `deepseek-v4-pro[1m]` | `1048576` | `384000` | prompt=$0.435/M tokens; completion=$0.87/M tokens; input_cache_read=$0.003625/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +12 more |
| `google/gemini-3-flash-preview` | `gemini-3-flash-agent(high)`, `gemini-3-flash-agent(low)`, `gemini-3-flash-agent(medium)` | `1048576` | `65536` | prompt=$0.5/M tokens; completion=$3/M tokens; internal_reasoning=$3/M tokens; input_cache_read=$0.05/M tokens; input_cache_write=$0.08333333333333334/M tokens | image=$0.0000005 (USD per image input); audio=$0.000001 (USD per OpenRouter route-defined audio unit (kept raw; not normalized to per-1M tokens)); web_search=$0.014 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +4 more |
| `google/gemini-3.1-flash-image-preview` | `gemini-3.1-flash-image` | `131072` | `65536` | prompt=$0.5/M tokens; completion=$3/M tokens | web_search=$0.014 (USD per web search operation) | reasoning, include_reasoning, structured_outputs, response_format, max_tokens, +4 more |
| `google/gemini-3.1-flash-lite` | `gemini-3.1-flash-lite` | `1048576` | `65536` | prompt=$0.25/M tokens; completion=$1.5/M tokens; internal_reasoning=$1.5/M tokens; input_cache_read=$0.025/M tokens; input_cache_write=$0.08333333333333334/M tokens | image=$0.00000025 (USD per image input); audio=$0.0000005 (USD per OpenRouter route-defined audio unit (kept raw; not normalized to per-1M tokens)); web_search=$0.014 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +4 more |
| `google/gemini-3.1-pro-preview` | `gemini-3.1-pro-low` | `1048576` | `65536` | prompt=$2/M tokens; completion=$12/M tokens; internal_reasoning=$12/M tokens; input_cache_read=$0.2/M tokens; input_cache_write=$0.375/M tokens | image=$0.000002 (USD per image input); audio=$0.000002 (USD per OpenRouter route-defined audio unit (kept raw; not normalized to per-1M tokens)); web_search=$0.014 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +4 more |
| `google/gemini-3.5-flash` | `gemini-3.5-flash-low` | `1048576` | `65536` | prompt=$1.5/M tokens; completion=$9/M tokens; internal_reasoning=$9/M tokens; input_cache_read=$0.15/M tokens; input_cache_write=$0.08333333333333334/M tokens | image=$0.0000015 (USD per image input); audio=$0.000003 (USD per OpenRouter route-defined audio unit (kept raw; not normalized to per-1M tokens)); web_search=$0.014 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +4 more |
| `minimax/minimax-m2.7` | `MiniMax-M2.7` | `204800` | `131072` | prompt=$0.279/M tokens; completion=$1.2/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +12 more |
| `moonshotai/kimi-k2.5` | `kimi-k2.5` | `262144` | `262144` | prompt=$0.4/M tokens; completion=$1.9/M tokens; input_cache_read=$0.09/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +12 more |
| `moonshotai/kimi-k2.6` | `K2.6`, `kimi-k2.6` | `262144` | `262142` | prompt=$0.73/M tokens; completion=$3.49/M tokens; input_cache_read=$0.25/M tokens | none | reasoning, include_reasoning, reasoning_effort, tools, tool_choice, structured_outputs, response_format, max_tokens, +13 more |
| `openai/gpt-5.3-codex` | `gpt-5.3-codex` | `400000` | `128000` | prompt=$1.75/M tokens; completion=$14/M tokens; input_cache_read=$0.175/M tokens | web_search=$0.01 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, max_completion_tokens, +1 more |
| `openai/gpt-5.4` | `gpt-5.4` | `1050000` | `128000` | prompt=$2.5/M tokens; completion=$15/M tokens; input_cache_read=$0.25/M tokens | web_search=$0.01 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, max_completion_tokens, +1 more |
| `openai/gpt-5.4-mini` | `gpt-5.4-mini` | `400000` | `128000` | prompt=$0.75/M tokens; completion=$4.5/M tokens; input_cache_read=$0.075/M tokens | web_search=$0.01 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, max_completion_tokens, +1 more |
| `openai/gpt-5.5` | `gpt-5.5` | `1050000` | `128000` | prompt=$5/M tokens; completion=$30/M tokens; input_cache_read=$0.5/M tokens | web_search=$0.01 (USD per web search operation) | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, max_completion_tokens, +1 more |
| `openai/gpt-oss-120b` | `gpt-oss-120b-medium` | `131072` | `unknown` | prompt=$0.039/M tokens; completion=$0.18/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +12 more |
| `qwen/qwen3-coder-next` | `qwen3-coder-next` | `262144` | `262144` | prompt=$0.11/M tokens; completion=$0.8/M tokens; input_cache_read=$0.07/M tokens | none | tools, tool_choice, structured_outputs, response_format, max_tokens, +10 more |
| `qwen/qwen3-coder-plus` | `qwen3-coder-plus` | `1000000` | `65536` | prompt=$0.65/M tokens; completion=$3.25/M tokens; input_cache_read=$0.13/M tokens; input_cache_write=$0.8125/M tokens | none | tools, tool_choice, structured_outputs, response_format, max_tokens, +4 more |
| `qwen/qwen3.5-plus-20260420` | `qwen3.5-plus` | `1000000` | `65536` | prompt=$0.3/M tokens; completion=$1.8/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +4 more |
| `qwen/qwen3.6-plus` | `qwen3.6-plus`, `qwen3.6-plus-openai-canary` | `1000000` | `65536` | prompt=$0.325/M tokens; completion=$1.95/M tokens; input_cache_write=$0.40625/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +4 more |
| `xiaomi/mimo-v2.5` | `mimo-v2.5` | `1048576` | `131072` | prompt=$0.4/M tokens; completion=$2/M tokens; input_cache_read=$0.08/M tokens | none | reasoning, include_reasoning, tools, tool_choice, response_format, max_tokens, +5 more |
| `xiaomi/mimo-v2.5-pro` | `mimo-v2.5-pro`, `mimo-v2.5-pro[1m]` | `1048576` | `16384` | prompt=$1/M tokens; completion=$3/M tokens; input_cache_read=$0.2/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +10 more |
| `z-ai/glm-5` | `glm-5` | `202752` | `unknown` | prompt=$0.6/M tokens; completion=$1.92/M tokens; input_cache_read=$0.12/M tokens | none | reasoning, include_reasoning, tools, tool_choice, structured_outputs, response_format, max_tokens, +10 more |
| `z-ai/glm-5-turbo` | `glm-5-turbo` | `202752` | `131072` | prompt=$1.2/M tokens; completion=$4/M tokens; input_cache_read=$0.24/M tokens | none | reasoning, include_reasoning, tools, tool_choice, response_format, max_tokens, +10 more |
| `z-ai/glm-5.1` | `glm-5.1` | `202752` | `unknown` | prompt=$0.98/M tokens; completion=$3.08/M tokens; input_cache_read=$0.182/M tokens | none | reasoning, include_reasoning, reasoning_effort, tools, tool_choice, structured_outputs, response_format, max_tokens, +13 more |

## OpenRouter Reference Notes

- `openrouter_models_api` is captured from `/api/v1/models`; OpenRouter docs define `context_length`, `pricing`, `supported_parameters`, and `top_provider.max_completion_tokens` in the Models API schema.
- OpenRouter pricing docs say all pricing values are USD per token/request/unit; this doc normalizes only token fields to per-1M-token prices and keeps request/image/web_search/audio raw with explicit units.
- OpenRouter context/max-output/pricing can be newer or route-specific. When it differs from vendor official fields, use `provider_catalog_mismatch_notes` instead of silently changing official calibration.
- OpenRouter `supported_parameters` is useful for route compatibility (`reasoning`, `include_reasoning`, `reasoning_effort`, `tools`, `structured_outputs`, etc.) and is stored in JSON for setup/installer checks.
- For current `GLM` rows, OpenRouter reports `202752` provider context while BigModel docs round the official context to `200K`; keep both.
- For current `gpt-5.4`, OpenRouter reports a larger provider context than the existing official calibration row; keep as a mismatch until OpenAI official docs are refreshed/rechecked.

## Gemini Thinking Notes

- Google thinking docs: Gemini 3 / 3.1 / 3.5 use `thinkingConfig.thinkingLevel`, not numeric `thinkingBudget`.
- `thinkingLevel` table: Gemini 3.1 Pro supports `low/medium/high` only; Gemini 3.1 Flash-Lite, Gemini 3 Flash, and Gemini 3.5 Flash support `minimal/low/medium/high`.
- Defaults: Gemini 3.1 Pro and Gemini 3 Flash default to `high` dynamic; Gemini 3.1 Flash-Lite defaults to `minimal`; Gemini 3.5 Flash defaults to `medium`.
- Numeric `thinkingBudget` belongs to Gemini 2.5 series. Do not send numeric budgets to Gemini 3 aliases unless a future official doc changes the contract.

## Antigravity Official Product Notes

- `google_antigravity_models` is the authoritative Antigravity product selector list. It currently lists `Gemini 3.5 Flash`, `Gemini 3.1 Pro (high/low)`, `Gemini 3 Flash`, `Claude Sonnet 4.6 (thinking)`, `Claude Opus 4.6 (thinking)`, and `GPT-OSS-120b`.
- `google_antigravity_plans` confirms baseline Antigravity agent-model access to Gemini 3.5 Flash, Gemini 3.1 Pro, Gemini 3 Flash, Claude Sonnet & Opus 4.6, and gpt-oss-120b; quota/availability still depends on plan and provider capacity.
- `Nano Banana 2` is listed by Antigravity as an additional internal generative image model for agent image/mockup/diagram tasks, not a user-selectable MMS reasoning route, so it is reference-only and not counted as a main table alias.
- `gemini-3.1-pro-high` is official as an Antigravity product selector counterpart to `gemini-3.1-pro-low`; it is not in current MMS visible aliases, so it should be added only if the provider `/models` exposes that exact local alias.

## GLM Notes

- `bigmodel_model_overview` fills the exact GLM text-model limits: `GLM-5.1`, `GLM-5`, and `GLM-5-Turbo` are `200K` context and `128K` max output.
- `bigmodel_thinking` / `zai_thinking` confirm deep thinking support for `GLM-5.1`, `GLM-5`, and `GLM-5-Turbo`; the official knob is `thinking.type`, not a numeric budget.
- `bigmodel_thinking_mode` / `zai_thinking_mode` document interleaved and preserved thinking; callers must preserve historical `reasoning_content` and use `clear_thinking=false` when they need reasoning continuity.
- `bigmodel_intro` / `zai_devpack` mention Vision Understanding via plan/tooling, and `Vision MCP` has its own docs. That is not direct vision support for base text rows; use `GLM-5V-Turbo` or Vision MCP rows if those are added later.

## Reference Sources

- `deepseek_modelstudio`: https://help.aliyun.com/zh/model-studio/text-generation-model
- `deepseek_official`: https://api-docs.deepseek.com/quick_start/pricing/
- `qwen_text`: https://help.aliyun.com/zh/model-studio/text-generation-model
- `qwen_thinking`: https://help.aliyun.com/zh/model-studio/deep-thinking
- `qwen_vision`: https://help.aliyun.com/zh/model-studio/image-understanding
- `kimi_code`: https://www.kimi.com/code/docs/en/
- `kimi_agents`: https://www.kimi.com/code/docs/en/third-party-tools/other-coding-agents.html
- `mimo_openai`: https://platform.xiaomimimo.com/static/docs/api/chat/openai-api.md
- `mimo_anthropic`: https://platform.xiaomimimo.com/static/docs/api/chat/anthropic-api.md
- `mimo_reasoning`: https://platform.xiaomimimo.com/static/docs/usage-guide/passing-back-reasoning_content.md
- `minimax_openai`: https://platform.minimaxi.com/docs/api-reference/text-openai-api
- `minimax_anthropic`: https://platform.minimaxi.com/docs/api-reference/text-anthropic-api
- `glm_overview`: https://docs.z.ai/devpack/overview
- `glm_51`: https://docs.z.ai/guides/llm/glm-5.1
- `google_models`: https://ai.google.dev/gemini-api/docs/models
- `google_thinking`: https://ai.google.dev/gemini-api/docs/thinking
- `openai_models`: https://platform.openai.com/docs/models
- `openai_reasoning`: https://platform.openai.com/docs/guides/reasoning
- `openai_image`: https://platform.openai.com/docs/guides/image-generation
- `anthropic_models`: https://docs.anthropic.com/en/docs/about-claude/models/overview
- `anthropic_vision`: https://docs.anthropic.com/en/docs/build-with-claude/vision
- `google_antigravity_models`: https://antigravity.google/assets/docs/agent/models.md
- `google_antigravity_plans`: https://antigravity.google/assets/docs/plans/plans.md
- `google_gemini_3_flash`: https://ai.google.dev/gemini-api/docs/models/gemini-3-flash-preview
- `google_gemini_31_pro`: https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview
- `google_gemini_31_flash_lite`: https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite
- `google_gemini_31_flash_image`: https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image-preview
- `google_gemini_35_flash`: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash
- `anthropic_claude_models_current`: https://platform.claude.com/docs/about-claude/models
- `anthropic_claude_1m_context`: https://claude.com/blog/1m-context-ga
- `anthropic_claude_opus_46`: https://www.anthropic.com/news/claude-opus-4-6
- `openai_gpt_oss_120b`: https://platform.openai.com/docs/models/gpt-oss
- `bigmodel_intro`: https://docs.bigmodel.cn/cn/guide/start/introduction
- `bigmodel_model_overview`: https://docs.bigmodel.cn/cn/guide/start/model-overview
- `bigmodel_glm_51`: https://docs.bigmodel.cn/cn/guide/models/text/glm-5.1
- `bigmodel_glm_5`: https://docs.bigmodel.cn/cn/guide/models/text/glm-5
- `bigmodel_glm_5_turbo`: https://docs.bigmodel.cn/cn/guide/models/text/glm-5-turbo
- `bigmodel_thinking`: https://docs.bigmodel.cn/cn/guide/capabilities/thinking
- `bigmodel_thinking_mode`: https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode
- `bigmodel_vision_mcp`: https://docs.bigmodel.cn/cn/coding-plan/mcp/vision-mcp-server
- `zai_glm_51`: https://docs.z.ai/guides/llm/glm-5.1
- `zai_glm_5`: https://docs.z.ai/guides/llm/glm-5
- `zai_glm_5_turbo`: https://docs.z.ai/guides/llm/glm-5-turbo
- `zai_thinking`: https://docs.z.ai/guides/capabilities/thinking
- `zai_thinking_mode`: https://docs.z.ai/guides/capabilities/thinking-mode
- `zai_vision_mcp`: https://docs.z.ai/devpack/mcp/vision-mcp-server
- `openrouter_models_catalog`: https://openrouter.ai/models
- `openrouter_models_api`: https://openrouter.ai/api/v1/models
- `openrouter_models_docs`: https://openrouter.ai/docs/guides/overview/models
- `openrouter_models_api_reference`: https://openrouter.ai/docs/api/api-reference/models/get-models
- `openrouter_api_reference_overview`: https://openrouter.ai/docs/api-reference/overview
