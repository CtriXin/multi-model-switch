# Provider Profiles

MMS uses `config/provider-profiles.json` as the built-in declarative reference for provider/model compatibility differences. The goal is to keep vendor-specific request details out of launcher, bridge, chat, discuss, and routing code.

## Load Order

1. Built-in: `config/provider-profiles.json`
2. Optional user overlay, read-only by MMS runtime:
   - `~/.config/mms/provider-profiles.json`
   - `~/.config/mms/model-profiles.json`

Agents must not auto-write the real `~/.config/mms/**` files. User overlays are for manual human configuration.

## What A Profile Can Describe

- `references`: official docs used as source material.
- `api_formats`: protocol-specific base URL and request path metadata.
- `auth_headers`: declarative auth header forms such as `authorization_bearer`, `x-api-key`, and `api-key`.
- `body_patches`: protocol/purpose-specific request body patches, including `thinking_on`, `thinking_off`, and `classify`.
- `effort`: protocol-specific effort field path, allowed values, defaults, and mappings.
- `context_windows`: model-prefix context metadata.
- `model_aliases`: protocol-specific provider wire-model aliases, optionally gated by `provider_id_contains` or `base_url_contains`, for cases where the logical MMS model should stay stable but the upstream API needs a different model string.
- `model_overrides`: model-prefix overrides for thinking/effort/context behavior.

Context metadata is advisory unless the matching protocol can activate that upstream context mode. If an upstream rejects a documented long-context model suffix, keep the built-in profile conservative and move any larger context window to a human-managed local overlay only after a live smoke proves it.

The patch engine intentionally supports only data-driven field patches. It does not load Python hooks from profiles.

## Current Dual-Format References

| Provider | OpenAI-compatible format | Anthropic-compatible format | Thinking / effort shape |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` + `/responses` | N/A | `reasoning.effort` on Responses API |
| Qwen / DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` + `/chat/completions` | `https://dashscope.aliyuncs.com/apps/anthropic` + `/v1/messages` | `enable_thinking`; some local templates use `chat_template_kwargs.enable_thinking`; `thinking_budget` metadata is recorded |
| Xiaomi MiMo | `https://api.xiaomimimo.com/v1` + `/chat/completions` | `https://api.xiaomimimo.com/anthropic` + `/v1/messages` | `thinking.type` enabled/disabled; no GPT-style effort tier recorded |
| MiniMax | `https://api.minimaxi.com/v1` + `/chat/completions` | `https://api.minimaxi.com/anthropic` + `/v1/messages` | OpenAI format can use `reasoning_split`; Anthropic format uses thinking blocks |
| DeepSeek | `https://api.deepseek.com` + `/chat/completions` | `https://api.deepseek.com/anthropic` + `/v1/messages` | OpenAI `reasoning_effort` and Anthropic `output_config.effort`, currently `high`/`max` |
| Kimi Code | `https://api.kimi.com/coding/v1` + `/chat/completions` | `https://api.kimi.com/coding/` + `/v1/messages` | Thinking toggle metadata only; preserve normal client headers |
| GLM / Z.ai | `https://api.z.ai/api/paas/v4/` + `/chat/completions` | `https://api.z.ai/api/anthropic` + `/v1/messages` | `thinking.type` enabled/disabled |

MiMo long context is opt-in by model suffix. Keep ordinary `mimo-v2.5-pro`
at 262144 tokens; expose `mimo-v2.5-pro[1m]` only on direct MiMo routes. The
Token Plan Anthropic endpoint rejects the literal suffixed API model, so MMS
keeps `[1m]` as a local selector and forwards `mimo-v2.5-pro` with the
`context-1m-2025-08-07` Anthropic beta header.

MiMo's OpenCode integration is separate from Claude Code: direct MiMo OpenCode
routes use OpenAI-compatible `/v1` and OpenCode model metadata advertises the
documented 1048576 context / 131072 output limits for `mimo-v2.5-pro` and
`mimo-v2.5`.

## Source References

- OpenAI Responses API: https://platform.openai.com/docs/api-reference/responses
- OpenAI reasoning guide: https://platform.openai.com/docs/guides/reasoning
- OpenAI models: https://platform.openai.com/docs/models
- Qwen / DashScope deep thinking: https://help.aliyun.com/zh/model-studio/deep-thinking
- MiMo original Anthropic API page: https://platform.xiaomimimo.com/docs/zh-CN/api/chat/anthropic-api?target=%E8%AF%B7%E6%B1%82%E4%BD%93
- MiMo Anthropic API: https://platform.xiaomimimo.com/static/docs/api/chat/anthropic-api.md
- MiMo OpenAI API: https://platform.xiaomimimo.com/static/docs/api/chat/openai-api.md
- MiMo OpenCode integration: https://platform.xiaomimimo.com/static/docs/integration/opencode.md
- MiMo Claude Code integration: https://platform.xiaomimimo.com/static/docs/integration/claudecode.md
- MiniMax Anthropic API: https://platform.minimaxi.com/docs/api-reference/text-anthropic-api
- MiniMax OpenAI API: https://platform.minimaxi.com/docs/api-reference/text-openai-api
- DeepSeek Chat Completion: https://api-docs.deepseek.com/api/create-chat-completion
- DeepSeek pricing / context lengths: https://api-docs.deepseek.com/quick_start/pricing/
- DeepSeek Claude Code integration: https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code
- DeepSeek Anthropic API: https://api-docs.deepseek.com/guides/anthropic_api
- Kimi Code docs: https://www.kimi.com/code/docs/en/
- Kimi Code third-party agents: https://www.kimi.com/code/docs/en/third-party-tools/other-coding-agents.html
- Z.ai API introduction: https://docs.z.ai/api-reference/introduction
- Z.ai GLM-4.6 guide: https://docs.z.ai/guides/llm/glm-4.6
- Z.ai DevPack overview: https://docs.z.ai/devpack/overview
