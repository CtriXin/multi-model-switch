# Official Model Capability Source Runbook

Date: 2026-06-14

Purpose: keep new-model capability updates repeatable for MMF official
overrides, especially `context`, `max_output`, `thinking`, and `effort`.

This file is evidence and operating guidance. Runtime truth still comes from
the selected MMF config root, its DB candidates, and the generated
latest-approved bundle.

## Runtime Read Path

MMF runtime consumers should read capability/profile data in this order:

1. `generated/model-registry.latest-approved.json`
2. `generated/model-capabilities.approved.json`
3. `generated/model-policy.effective.json`
4. `generated/provider-profiles.generated.json`
5. Built-in seed fallback: `config/provider-profiles.json`

Relevant readers:

- `mms_capability_resolver.py`: resolves `context_window_tokens`,
  `max_output_tokens`, `supports_vision`, `supports_thinking`, and
  `thinking_control`.
- `mms_provider_profiles.py`: applies provider/profile body patches such as
  `thinking.type`, `thinkingConfig.thinkingLevel`, `reasoning.effort`,
  `reasoning_split`, and protocol-specific aliases.
- `mms_opencode_config.py`: converts resolved capability/profile data into
  OpenCode `limit`, `attachment`, `options`, and `variants`.

Do not make OpenCode, Claude, or Codex model-capability behavior depend on
hardcoded model lists. If a capability is missing, add source-backed data to the
MMF official override path instead.

## Source Priority

Use these evidence layers:

1. `vendor_official`: vendor docs, official model pages, official pricing pages,
   official tool-integration pages.
2. `provider_catalog`: OpenRouter or gateway `/models`; useful for route ids,
   context, supported parameters, and price, but it must not silently overwrite
   official facts.
3. `runtime_observed`: smoke tests and route health; confirms live behavior but
   does not become official capability truth by itself.
4. `manual`: human override in WebUI/model-policy when official docs are
   incomplete or the user intentionally wants a safer local limit.

Unknown official fields should stay unknown. Do not invent `max_output_tokens`,
vision support, or effort controls from model name patterns.

## Operator Workflow

For a newly released model, use one of these two routes:

### Human-first

1. In WebUI, pull provider/OpenRouter catalog data to discover model ids and
   provider routes.
2. Open the official source links listed below or the vendor docs index.
3. Manually mark capability fields in WebUI:
   - `context_window_tokens`
   - `max_output_tokens` only when official max/default semantics are clear
   - `vision` / `supports_vision`
   - `thinking` / `supports_thinking`
   - exact `thinking_control.path`, allowed values, default, and mapping
4. Save to the current MMF preview root and publish latest-approved bundle.
5. Run targeted smoke for Claude/OpenCode/Codex when the field affects request
   shaping.

### LLM-assisted

1. Ask the LLM to read this runbook plus the vendor official docs.
2. The LLM may draft a provider-profile/model-policy/MMF official-override patch.
3. The LLM must label each field with source layer and URL.
4. A human or WebUI action should apply/publish the candidate. The LLM must not
   write global `~/.config/mms*` directly unless explicitly instructed.
5. The LLM must leave ambiguous fields blank or conservative, then record the
   ambiguity.

## Current Official Source Matrix

### Z.ai GLM-5.2

Official source:

- https://docs.z.ai/devpack/latest-model

Source-backed facts:

- Model id: `glm-5.2`
- Claude Code long-context selector: `glm-5.2[1m]`
- Claude Code auto compact window: `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000`
- Context: `1000000`
- Output: `131072`
- Input modalities: text
- Reasoning: true
- Claude Code effort mapping:
  - `low`, `medium`, `high` -> upstream `high`
  - `xhigh`, `max`, `ultracode` -> upstream `max`

MMF encoding notes:

- Store `context_window_tokens=1000000`.
- Store `max_output_tokens=131072`.
- Do not add vision.
- Treat the documented effort mapping as Claude Code integration evidence.
  Only emit OpenCode request `options`/`variants` when a provider profile has a
  request-body path, not when the source is an environment-only field.
- Existing GLM profile behavior can continue to use `thinking.type` only where
  the selected provider route supports it or a live smoke confirms it.

### Kimi K2.7 Code

Official sources:

- https://platform.kimi.ai/docs/guide/kimi-k2-7-code-quickstart
- https://platform.kimi.ai/docs/guide/use-kimi-k2-thinking-model
- https://platform.kimi.ai/docs/pricing/chat-k27-code

Source-backed facts:

- Model id: `kimi-k2.7-code`
- Context: `256000` / 256K
- Modalities: text, image, video input; text output
- Thinking: always on; non-thinking mode is not supported
- `thinking.type`: only `"enabled"`; passing `"disabled"` errors
- `thinking.keep`: effectively `"all"` / Preserved Thinking always on
- `reasoning_content` must be preserved in message history for multi-step tool
  calls.
- `max_tokens`: documented default is `32768`.
- For reliable tool/reasoning output, official guidance says use
  `max_tokens >= 16000`.
- Temperature/top_p/n/presence/frequency controls are fixed for K2.7 Code; do
  not send non-default values unless the vendor docs change.

MMF encoding notes:

- Store `context_window_tokens=256000`.
- Store vision/video support if the schema can distinguish multimodal input;
  otherwise `supports_vision=true` is acceptable for image input selection.
- Store `supports_thinking=true`.
- Do not create a disable-thinking toggle for `kimi-k2.7-code`; it is not a
  valid control.
- Do not mark `thinking.keep` as optional for K2.7 Code.
- Do not write `official_max_output_tokens=256000` unless a newer official page
  explicitly says K2.7 output maximum equals context-minus-prompt. If MMF needs
  a practical output budget, use a manual/practical field or a conservative
  profile default of `32768`, with source semantics noted.

### MiniMax M3

Official sources:

- https://platform.minimax.io/docs/guides/text-generation
- https://platform.minimax.io/docs/api-reference/text-openai-api
- https://platform.minimax.io/docs/guides/text-m3-function-call

Source-backed facts:

- Model id: `MiniMax-M3`
- Context: `1000000`
- Modalities: text, image, video input; text output
- Thinking: on by default
- OpenAI-compatible thinking control:
  - `thinking.type="adaptive"` keeps thinking on
  - `thinking.type="disabled"` skips thinking
- M2.x models accept `thinking.disabled` but still think; do not use M3 thinking
  controls for M2.x.
- `reasoning_split=true` is output-format control, not a thinking on/off switch.
  It separates thinking into `reasoning_content` / `reasoning_details`.
- For multi-turn function/tool conversations, preserve the complete assistant
  message, including reasoning fields.
- OpenAI endpoint:
  - Global: `https://api.minimax.io/v1`
  - China: `https://api.minimaxi.com/v1`

MMF encoding notes:

- Store `context_window_tokens=1000000`.
- Store multimodal support for `MiniMax-M3`; keep M2.x text-only/known behavior
  separate unless official docs say otherwise.
- Store `supports_thinking=true`.
- For OpenAI-compatible routes, use `reasoning_split=true` when the caller needs
  structured reasoning output. Keep `thinking.type` as the on/off control.
- Do not infer a `max_output_tokens` value from context; add it only when
  official docs give an exact generation maximum.

## OpenRouter / Provider Catalog Handling

OpenRouter model import remains useful but should be tagged as
`provider_catalog`, not `official`.

Use OpenRouter for:

- provider route ids
- provider-specific model aliases
- catalog context and `max_completion_tokens`
- supported parameter hints
- pricing and availability snapshots

Do not let OpenRouter overwrite a vendor official field during "MMF official
override" unless the UI explicitly shows the source downgrade/override and the
operator confirms it.

## Field Checklist For Future Models

For every new model, capture:

- canonical model id and local aliases
- provider id and base URL
- supported protocols: `openai_chat_completions`, `anthropic_messages`,
  `openai_responses`
- context window tokens
- max output tokens, or "unknown"
- input modalities: text/image/video/audio
- output modalities
- thinking support
- thinking control path and allowed values
- effort control path, allowed values, default, and mapping
- whether the control is request-body, env-only, header-only, or UI-only
- whether reasoning content must be preserved across tool turns
- source URL and source layer for each field
- live smoke result if request shaping changed

## Guardrails

- Environment-only controls such as `CLAUDE_CODE_EFFORT_LEVEL` must not become
  OpenCode request `options` or `variants`.
- Local selectors such as `[1m]` are MMF/runner selectors unless the vendor API
  accepts them literally.
- Preserve official `thinking` semantics exactly. `thinking.type`,
  `thinking.keep`, `reasoning_split`, `reasoning.effort`, and
  `thinkingConfig.thinkingLevel` are not interchangeable.
- If official docs conflict with runtime observation, keep the official value as
  source evidence, record runtime observation separately, and use a safer manual
  local override only after explicit user/operator intent.
