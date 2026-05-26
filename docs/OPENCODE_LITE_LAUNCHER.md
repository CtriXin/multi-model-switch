# OpenCode Launcher Modes

MMS launches OpenCode through fixed modes. It does not ask the user to tune agents on every start.

## Decision

- `OpenSpec Multi` (`lite_pro_orchestrated`) is the default/recommended OpenCode mode. It keeps GPT-5.5 as coordinator/release gate, delegates implementation to a long-running GPT-5.4 executor, and uses domestic agents only for read-only exploration, bug-hunt, and visual/context checks.
- `Pro Solo` (`lite_pro`) is the high-confidence custom-agent lane for cases where one GPT-5.5-led lane is preferable to executor fanout.
- Both Lite Pro-derived modes now include an OpenSpec/SpecBridge contract lane: `mobius-spec-writer` creates the minimal task contract, and `mobius-spec-compliance-reviewer` checks the actual diff and validation output against that contract item by item.
- MMS can launch the same generated OpenCode config through the interactive TUI, a headless backend server (`opencode serve`), or ACP (`opencode acp`). Backend/ACP are entrypoints over the same session-local config; they do not replace MMS routing, trace, or evidence policy.
- `OMO` keeps using the existing global OpenCode + OMO setup.
- `Raw` is a pure fallback with no OMO and no custom agents.
- `lite` remains supported by profile ID for compatibility, but is hidden from the selector.
- In the OpenCode tab, MMS shows this mode selector first; session-local modes do not ask the user to choose a channel/model before mode selection.
- Lite Pro auto-resolves a deterministic multi-model roster and writes it only into session-local OpenCode config.
- Lite Pro uses mixed OpenCode providers: GPT routes prefer `@ai-sdk/openai` + Responses API for cache-friendly transport; GPT chat completions are only a degraded fallback; direct MiMo uses the official `@ai-sdk/openai-compatible` `/v1` path; the other non-GPT routes with `anthropic_messages` support use `@ai-sdk/anthropic` and `/v1/messages`.
- Lite Pro fail-closes protocol selection: GPT routes reject Anthropic transport, and non-GPT routes require `anthropic_messages`; if a protocol-safe non-GPT route is unavailable, that role uses the stable GPT fallback instead of silently using chat completions.
- Direct MiMo is available again as a supplemental CN/vision reviewer. It is not the final release gate, and MMS-generated OpenCode config disables MiMo model reasoning by default until OpenCode can replay MiMo `reasoning_content` in tool loops.
- Lite Pro includes optional vision helper agents. If the active coding/review model cannot read images, the coordinator can ask MiMo/Kimi/Qwen vision helpers to inspect screenshots first, then pass structured observations back to the main workflow.
- Lite Pro launch does not make a live model request by default. Set `MMS_OPENCODE_LAUNCH_PREFLIGHT=1` to run a tiny OpenCode preflight against the primary builder route; if `builder_primary` fails and `builder_fallback` passes, MMS starts OpenCode with `mobius-builder-stable` on the fallback model instead of opening a broken session. See `docs/OPENCODE_PREFLIGHT_OPT_IN_DECISION_2026-05-18.md` for the root-cause and fix record.
- MMS does not delete or rewrite global OMO config.
- MMS does not write `~/.config/opencode/opencode.json`, `~/.config/opencode/oh-my-openagent.jsonc`, or `~/.config/mms/config.toml` for this mode selection.

## Modes

| Mode | Launch shape | Config source | Use case |
| --- | --- | --- | --- |
| `lite_pro_orchestrated` / `OpenSpec Multi` | `opencode --pure --agent mobius-builder-pro -m mms-builder_primary/<model>` | MMS-generated session-local multi-provider `opencode.json` | Default/recommended: 5.5 coordinator/release gate, 5.4 long-running executor, domestic read-only exploration/bug-hunt |
| `lite_pro_orchestrated_backend` / `Backend Multi` | `opencode serve --pure` | Same session-local config as `OpenSpec Multi` | Headless backend server for SDK/WebUI/automation clients |
| `lite_pro_orchestrated_acp` / `ACP Multi` | `opencode acp --pure` | Same session-local config as `OpenSpec Multi` | ACP-compatible editor/client integration |
| `lite_pro` / `Pro Solo` | `opencode --pure --agent mobius-builder-pro -m mms-builder_primary/<model>` | MMS-generated session-local multi-provider `opencode.json` | Single GPT-5.5-led lane with OpenSpec contract checks and named fallback agents |
| `heavy_omo` / `OMO Global` | `opencode` | Existing global OpenCode + OMO config | Global OMO/fanout lane |
| `raw` / `Raw Pure` | `opencode --pure -m mms/<safe-gpt-model>` | MMS-generated session-local `opencode.json` | Debug fallback |

Direct launch is also supported, for example `mms opencode --profile lite_pro_orchestrated` or `mmd opencode --profile lite_pro_orchestrated`.

Alternative entrypoints are explicit and opt-in:

```bash
mms opencode --profile lite_pro_orchestrated_backend
mms opencode --profile lite_pro_orchestrated_acp
mms opencode --profile lite_pro_orchestrated --backend-agent
```

`Backend Multi` and `--backend-agent` start `opencode serve --pure` with the MMS-generated session-local config for SDK/WebUI/headless clients. `ACP Multi` and `--opencode-entrypoint acp` start `opencode acp --pure` for ACP-compatible editors. Neither path writes global OpenCode config.

## Lite Pro Roster

| Agent | Mode | Current resolved model | Fallback role | Edit policy |
| --- | --- | --- | --- | --- |
| `mobius-builder-pro` | primary | `gpt-5.5` | main worker | ask |
| `mobius-builder-stable` | primary | `gpt-5.4` | launch/builder fallback | ask |
| `mobius-spec-writer` | subagent | `gpt-5.5` via Responses | OpenSpec/SpecBridge contract writer | ask |
| `mobius-spec-compliance-reviewer` | subagent | `gpt-5.5` via Responses | contract-vs-diff acceptance reviewer | deny |
| `mobius-explore-glm` | subagent | `glm-5-turbo` via Anthropic | primary explorer | deny |
| `mobius-explore-kimi` | subagent | `kimi-for-coding` via Anthropic | fallback explorer | deny |
| `mobius-vision-mimo` | subagent | `mimo-v2.5` via direct MiMo OpenAI-compatible | primary image helper | deny |
| `mobius-vision-kimi` | subagent | `kimi-k2.5` / `K2.6` via Anthropic | image helper fallback | deny |
| `mobius-vision-qwen` | subagent | `qwen3.6-plus` / `qwen3.6-flash` via Anthropic | image helper fallback | deny |
| `mobius-reviewer-gpt55` | subagent | `gpt-5.5` via Responses | primary release-gate reviewer | deny |
| `mobius-reviewer-gpt54` | subagent | `gpt-5.4` via Responses | stable reviewer outage fallback | deny |
| `mobius-reviewer-mimo` | subagent | `mimo-v2.5-pro` via direct MiMo OpenAI-compatible | supplemental CN/vision critique reviewer | deny |
| `mobius-bughunt-deepseek` | subagent | `deepseek-v4-pro` via Anthropic | read-only defect and edge-case hunt | deny |
| `mobius-bughunt-glm` | subagent | `glm-5.1` via Anthropic | fallback read-only defect hunt | deny |
| `mobius-bughunt-qwen` | subagent | `qwen3.7-max` via Anthropic | orchestrated-mode long-context bug-hunt | deny |
| `mobius-executor-gpt54` | subagent | `gpt-5.4` via Responses | orchestrated-mode long-running implementation executor | ask |
| `mobius-fixer-gpt54` | subagent | `gpt-5.4` | focused fixer fallback | ask |

GLM/Kimi/DeepSeek/Qwen routes are cache-sensitive in the current config, so Lite Pro assigns them to Anthropic `/v1/messages` for read-only support roles. Text-only Qwen support roles prefer `qwen3.7-max`; Qwen vision stays on `qwen3.6-plus` / `qwen3.6-flash` because `qwen3.7-max` is treated as text-only. They must not fall back to `chat/completions` silently. MiMo is the exception: Xiaomi's OpenCode guide uses OpenAI-compatible `/v1`, and warns that OpenCode + Anthropic protocol can miss `reasoning_content` in tool loops. MiMo remains direct-only and is configured with `reasoning=false` in OpenCode-generated model metadata until OpenCode can reliably preserve that field.

## Configurable Agent Roster

The `mobius-*` names above are default preset agents, not the long-term user-facing boundary. MMS now accepts a small `[opencode]` override layer so WebUI can hide those internal names behind labels such as "Vision Agent 1" or "Executor 2" while the launcher still writes a valid session-local `opencode.json`.

Supported config shape:

```toml
[opencode]
default_profile = "lite_pro_orchestrated"

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
- This layer is still session-local. It does not write global OpenCode config or real `~/.config/mms/**` by itself.

## Lite Pro Orchestrated

`lite_pro_orchestrated` uses the same launch shape and route guardrails as Lite Pro, but changes the work split:

- `mobius-builder-pro` / `gpt-5.5` is coordinator only: `edit=deny`, plans, delegates, inspects diffs, and accepts/rejects executor output.
- The coordinator must create or reuse a concise OpenSpec/SpecBridge-style contract for non-trivial work before executor dispatch, then run spec-compliance review before the general release gate.
- Primary executor: `mobius-executor-gpt54`. MMS no longer shards normal implementation across low-step domestic executor chains.
- `mobius-explore-qwen` is available as an extra read-only Qwen explorer for broad repo/API context.
- `mobius-bughunt-deepseek`, `mobius-bughunt-glm`, and `mobius-bughunt-qwen` are read-only challenge agents for defects, missing tests, counterexamples, and risky assumptions.
- `mobius-vision-mimo`, `mobius-vision-kimi`, and `mobius-vision-qwen` are read-only image helpers. They are only generated when a matching image-capable route exists, so non-vision models do not falsely advertise image support.
- Review is separated from executors: `mobius-reviewer-gpt55` is the release gate, and `mobius-reviewer-gpt54` is only a reviewer-route outage fallback. The coordinator prompt tells OpenCode not to let executor/fixer agents self-approve their own output.
- `mobius-reviewer-mimo` is supplemental only: use it for CN/vision/counterexample critique when direct MiMo exists, then keep GPT as the final release gate.
- The GPT executor/fixer have edit/test permissions and must return changed files, validation commands, results, risks, and blockers. They must treat the contract packet as authoritative and return a blocker instead of reinterpreting unclear acceptance criteria.
- Domestic agents remain read-only so a low step cap cannot leave partial edits or force handoff-chained implementation.
- If acceptance fails, the coordinator sends one bounded failure packet to `mobius-fixer-gpt54` instead of cycling through multiple domestic executors.

Fallback is deterministic, not random. There are two layers:

1. Launch fallback: `builder_primary` (`mobius-builder-pro` / `gpt-5.5`) is selected first without a live request. Set `MMS_OPENCODE_LAUNCH_PREFLIGHT=1` to preflight it; if it fails, MMS tries `builder_fallback` (`mobius-builder-stable` / `gpt-5.4`) and launches that route when healthy.
2. Agent fallback: the primary builder prompt tells it to use the first lane, then call the paired fallback agent when a subagent fails, returns low confidence, misses evidence, or validation still fails.

## Lite Stable Agents

| Agent | Mode | Purpose | Edit policy |
| --- | --- | --- | --- |
| `mobius-builder` | primary | Daily scoped implementation | ask |
| `mobius-explore` | subagent | Read-only codebase lookup | deny |
| `mobius-reviewer` | subagent | Release-gate review and evidence check | deny |
| `mobius-fixer` | subagent | Focused repair for a known failure | ask |

## Smoke

Dry smoke validates generated config and agent discovery without real model calls:

```bash
./mms opencode-smoke --profile lite_pro
```

Live smoke performs real OpenCode model calls and records a Moebius trace artifact:

```bash
./mms opencode-smoke --profile lite_pro --live
```

Use `--agent <name>` to test one agent. Use `--health-summary` to include the current repo-local route health table from `.ai/opencode-health/latest.json` without making extra model calls. Without `--agent`, live smoke dispatches one small OpenCode task per configured Lite Pro agent/model, including the fallback lanes. Every smoke writes `.ai/trace/<trace_id>/opencode-smoke-result.json` with routes, launch candidates, checks, and configured transport evidence.

When `--live` is used, the smoke also appends one route health row per tested agent to `.ai/opencode-health/route-health.jsonl` and refreshes `.ai/opencode-health/latest.json`. Each row records `model`, `provider_id`, `protocol`, `request_url`, `role`, `agent`, `status`, `error_class`, `latency_sec`, `fallback_reason`, and `cache_transport_evidence`. Dry smoke does not mutate the health ledger.

MMS reads `.ai/opencode-health/latest.json` as repo-local health input only. `blocked` routes are not eligible for automatic fallback, fresh `unhealthy` routes are temporarily filtered, then route preference is deterministic: `live_healthy`, `degraded`, `untested`, stale `unhealthy`, `blocked`. Lite Pro route selection applies that health input inside each role: same model on another healthy channel first, then the role's peer model, then the existing stable GPT fallback path.

The OpenCode mode menu appends compact health hints to Lite Pro modes, such as `health: 15/15 healthy` for `lite_pro` or `health: 18/18 healthy` for `lite_pro_orchestrated`. `Backend Multi` and `ACP Multi` reuse the same `lite_pro_orchestrated` health summary.

## Guardrails

- Do not put agent roles in `model-routes.json`.
- Do not treat OpenSpec/SpecBridge as a replacement orchestrator. It is a contract artifact that constrains executors and reviewers; MMS still owns launch/session routing and Moebius still owns closure when used.
- Do not store API keys in OpenCode agent config; use session env vars such as `MMS_OPENCODE_API_KEY_*`.
- Keep destructive shell, deploy, push, and external directory access behind `ask` or `deny`.
- Keep `heavy_omo` global-config based until a separate audited OMO overlay is implemented.
- Do not use `K2.6` in Lite Pro through `chat/completions`; if added later, keep it on Anthropic `/v1/messages` and validate with live smoke first.
- Do not assign GLM/Kimi/DeepSeek dual-protocol cache-sensitive routes to Lite Pro's OpenCode `chat/completions` lane; prefer Anthropic `/v1/messages`. Direct MiMo is explicitly OpenAI-compatible `/v1` per Xiaomi's OpenCode guide.
- Do not route MiMo through shared relays in Lite Pro; use direct MiMo only. In OpenCode-generated configs, keep MiMo `reasoning=false` unless the client path can preserve `reasoning_content` through multi-turn tool calls.
