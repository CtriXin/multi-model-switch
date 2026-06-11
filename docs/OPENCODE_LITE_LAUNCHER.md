# OpenCode Launcher Profiles

MMS now exposes four user-facing OpenCode profiles: `agent`, `review`, `omo`, and `raw`.
The older `lite_pro*` names are kept as hidden compatibility aliases only; they are no longer shown in CLI help, README examples, or the TUI selector.

## Decision

- `agent` is the default/recommended mode. It resolves the MMS-generated session-local agent roster, keeps GPT-5.5 as coordinator/release gate, delegates long-running implementation to GPT-5.4, and uses domestic routes for read-only exploration, bug-hunt, and vision/context checks.
- `review` is the Review Hub host mode. MMS resolves reviewer models before OpenCode starts, writes a session-local dynamic roster, then opens OpenCode TUI with a fast domestic host with GPT fallback that asks for a Review Hub request root and fans out to the preloaded reviewer agents.
- `omo` uses the existing global OpenCode + OMO setup. MMS does not write or delete global OMO config.
- `raw` is pure OpenCode with a session-local config and no OMO/custom agents.
- `lite_pro`, `pro`, `pro_solo`, and `lite_pro_orchestrated` normalize to the same internal agent roster profile for backward compatibility.
- `lite_pro_orchestrated_backend` and `lite_pro_orchestrated_acp` remain hidden compatibility aliases for old scripts, but they are not public modes.
- MMS does not write `~/.config/opencode/opencode.json`, `~/.config/opencode/oh-my-openagent.jsonc`, or `~/.config/mms/config.toml` for profile selection.

## Public Profiles

| Profile | Launch shape | Config source | Use case |
| --- | --- | --- | --- |
| `agent` | `opencode --pure --agent mobius-builder-pro -m mms-builder_primary/<model>` | MMS-generated session-local multi-provider `opencode.json` | Default agent roster: 5.5 coordinator/release gate, 5.4 executor, domestic read-only support |
| `review` | `opencode --pure --agent review-hub-host -m mms-builder_primary/<model>` | MMS-generated session-local multi-provider `opencode.json` | Review Hub host: use MMS-selected dynamic reviewers, run same request root, aggregate slots |
| `omo` | `opencode` | Existing global OpenCode + OMO config | Global OMO/fanout lane |
| `raw` | `opencode --pure -m mms/<safe-gpt-model>` | MMS-generated session-local `opencode.json` | Debug/minimal fallback |

Direct launch examples:

```bash
mms
mms opencode --profile agent
mms opencode --profile review
mms opencode --profile omo
mms opencode --profile raw
```

Review is TUI-first: choose `OpenCode` -> `Review`, Space-select reviewer models in the model page, then Enter to launch and remember the selection. CLI flags such as `--review-models` and `--save-review-models` remain only for scripts and smoke tests.

Dry smoke validates generated config and agent discovery without real model calls:

```bash
./mms opencode-smoke --profile agent
./mms opencode-smoke --profile review --review-models kimi2.5 minimax2.7 glm5-turbo
```

Live smoke performs real OpenCode model calls and records a Moebius trace artifact:

```bash
./mms opencode-smoke --profile agent --live
```

Use `--agent <name>` to test one agent. Use `--health-summary` to include the current repo-local route health table from `.ai/opencode-health/latest.json` without making extra model calls.

## Agent Roster

The `agent` profile currently resolves these default preset agents when matching routes exist:

| Agent | Mode | Purpose | Edit policy |
| --- | --- | --- | --- |
| `mobius-builder-pro` | primary | Coordinator/release gate | deny |
| `mobius-builder-stable` | primary | Launch/builder fallback | ask |
| `mobius-spec-writer` | subagent | OpenSpec/SpecBridge contract writer | ask |
| `mobius-spec-compliance-reviewer` | subagent | Contract-vs-diff acceptance reviewer | deny |
| `mobius-executor-gpt54` | subagent | Long-running implementation executor | ask |
| `mobius-explore-glm` | subagent | Primary read-only explorer | deny |
| `mobius-explore-kimi` | subagent | Explorer fallback | deny |
| `mobius-explore-qwen` | subagent | Qwen read-only explorer | deny |
| `mobius-bughunt-deepseek` | subagent | Defect and edge-case hunt | deny |
| `mobius-bughunt-glm` | subagent | Defect-hunt fallback | deny |
| `mobius-bughunt-qwen` | subagent | Long-context Qwen challenge lane | deny |
| `mobius-vision-mimo` | subagent | Primary image helper | deny |
| `mobius-vision-kimi` | subagent | Image helper fallback | deny |
| `mobius-vision-qwen` | subagent | Image helper fallback | deny |
| `mobius-reviewer-gpt55` | subagent | Primary release-gate reviewer | deny |
| `mobius-reviewer-gpt54` | subagent | Stable reviewer outage fallback | deny |
| `mobius-reviewer-mimo` | subagent | Supplemental CN/vision critique reviewer | deny |
| `mobius-fixer-gpt54` | subagent | Focused repair fallback | ask |

The internal `mobius-*` names are defaults, not the long-term UX boundary. WebUI can present them as labels such as "Vision Agent 1" or "Executor 2" while the launcher still writes valid session-local OpenCode config.

The `review` profile has a safe default roster and a dynamic MMS-selected roster:

| Agent | Mode | Purpose | Edit policy |
| --- | --- | --- | --- |
| `review-hub-host` | primary | Fast domestic Review Hub dispatcher/aggregator | ask |
| `review-hub-host-stable` | primary | Host fallback | ask |
| `review-qwen` | subagent | Qwen long-context independent review | ask |
| `review-kimi` | subagent | Kimi independent review, defaults to K2.6 | ask |
| `review-glm` | subagent | GLM independent review, defaults to GLM 5.1 | ask |
| `review-deepseek` | subagent | DeepSeek independent review | ask |
| `review-mimo` | subagent | MiMo multimodal/vision review, defaults to `mimo-v2.5` | ask |
| `review-mimo-pro` | subagent | MiMo Pro large-project/product critique, defaults to `mimo-v2.5-pro` | ask |

When the TUI selection, `--review-models`, or `[opencode.review].models` is set, MMS disables the default reviewer agents for that session and creates exact dynamic agents such as `review-kimi-k2-5`, `review-minimax-m2-7`, and `review-glm-5-turbo`. Fuzzy tokens are resolved from the MMS provider/model registry, so `qwen glm kimi minimax` and `kimi2.5 minimax2.7 glm5.1 glm5-turbo` both work. Use `domestic` for one best model per domestic family, or `all` for all visible domestic models.

Saved review defaults:

```toml
[opencode.review]
models = ["qwen", "kimi2.5", "minimax2.7", "glm5-turbo"]
```

The host does not copy dispatcher context into memory. It expects a durable Review Hub request root, gives each preloaded reviewer the same request-root command, and relies on runner-local MCP/skills during each reviewer preflight.

## Configurable Agent Roster

Supported config shape:

```toml
[opencode]
default_profile = "agent"

# Backward-compatible model override for an existing default agent or route key.
[opencode.agent_models.mobius-explore-glm]
provider_id = "domestic"
model = "kimi-for-coding"

# Disable a default agent.
[opencode.agent_roster.mobius-vision-mimo]
enabled = false
preset = "vision"

# Add a custom agent. Unknown roster entries are treated as custom agents.
[opencode.agent_roster.mobius-vision-custom-1]
enabled = true
custom = true
preset = "vision"
provider_id = "domestic"
model = "qwen3.6-plus"
description = "Custom Qwen vision helper"
```

Roster rules:

- `agent_models` only changes model/provider for an existing default agent or route key.
- `agent_roster` controls enable/disable and custom agents; custom agents get their own `custom_<agent>` route key.
- Required builder safety is preserved: `mobius-builder-pro` cannot be disabled by config.
- `preset` selects safe defaults for route search and permission shape: `builder`, `executor`, `explore`, `bughunt`, `vision`, `reviewer`, `spec`, or `fixer`.
- Missing or invalid explicit overrides fall back to the default automatic route and are recorded in runtime as `opencode_agent_model_override_unresolved`.
- This layer is session-local. It does not write global OpenCode config or real `~/.config/mms/**` by itself.

## Route Guardrails

- Do not put agent roles in `model-routes.json`.
- Do not store API keys in OpenCode agent config; use session env vars such as `MMS_OPENCODE_API_KEY_*`.
- Keep destructive shell, deploy, push, and external directory access behind `ask` or `deny`.
- Keep `omo` global-config based until a separate audited OMO overlay is implemented.
- Do not route cache-sensitive GLM/Kimi/DeepSeek/Qwen roles through OpenCode `chat/completions`; prefer Anthropic `/v1/messages`.
- Direct MiMo remains OpenAI-compatible `/v1`; keep MiMo `reasoning=false` unless the client path can preserve `reasoning_content` through multi-turn tool calls.
