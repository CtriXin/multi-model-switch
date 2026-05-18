# OpenCode Launcher Profiles

MMS launches OpenCode through fixed profiles. It does not ask the user to tune agents on every start.

## Decision

- `5.5 Pro` is the default high-confidence custom-agent lane.
- `5.5 Multi-Agent` keeps GPT-5.5 as coordinator only and delegates implementation to domestic executor agents before a GPT-5.4 final fallback.
- `OMO` keeps using the existing global OpenCode + OMO setup.
- `Raw` is a pure fallback with no OMO and no custom agents.
- `lite` remains supported by profile ID for compatibility, but is hidden from the selector.
- In the OpenCode tab, MMS shows this profile selector first; session-local profiles do not ask the user to choose a channel/model before profile selection.
- Lite Pro auto-resolves a deterministic multi-model roster and writes it only into session-local OpenCode config.
- Lite Pro uses mixed OpenCode providers: GPT routes prefer `@ai-sdk/openai` + Responses API for cache-friendly transport; GPT chat completions are only a degraded fallback; every non-GPT route with `anthropic_messages` support uses `@ai-sdk/anthropic` and `/v1/messages`.
- Lite Pro fail-closes protocol selection: GPT routes reject Anthropic transport, and non-GPT routes require `anthropic_messages`; if a protocol-safe non-GPT route is unavailable, that role uses the stable GPT fallback instead of silently using chat completions.
- Direct MiMo is available again as a supplemental CN/vision reviewer. It is not the final release gate, and MMS-generated OpenCode config disables MiMo model reasoning by default until OpenCode can replay MiMo `reasoning_content` in tool loops.
- Lite Pro includes optional vision helper agents. If the active coding/review model cannot read images, the coordinator can ask MiMo/Kimi/Qwen vision helpers to inspect screenshots first, then pass structured observations back to the main workflow.
- Lite Pro launch does not make a live model request by default. Set `MMS_OPENCODE_LAUNCH_PREFLIGHT=1` to run a tiny OpenCode preflight against the primary builder route; if `builder_primary` fails and `builder_fallback` passes, MMS starts OpenCode with `mobius-builder-stable` on the fallback model instead of opening a broken session. See `docs/OPENCODE_PREFLIGHT_OPT_IN_DECISION_2026-05-18.md` for the root-cause and fix record.
- MMS does not delete or rewrite global OMO config.
- MMS does not write `~/.config/opencode/opencode.json`, `~/.config/opencode/oh-my-openagent.jsonc`, or `~/.config/mms/config.toml` for this profile selection.

## Profiles

| Profile | Launch shape | Config source | Use case |
| --- | --- | --- | --- |
| `lite_pro` / `5.5 Pro` | `opencode --pure --agent mobius-builder-pro -m mms-builder_primary/<model>` | MMS-generated session-local multi-provider `opencode.json` | Daily coding with 5.5 primary and named fallback agents |
| `lite_pro_orchestrated` / `5.5 Multi-Agent` | `opencode --pure --agent mobius-builder-pro -m mms-builder_primary/<model>` | MMS-generated session-local multi-provider `opencode.json` | 5.5 coordinator with executor chain for implementation |
| `heavy_omo` / `OMO` | `opencode` | Existing global OpenCode + OMO config | Global OMO/fanout lane |
| `raw` / `Raw` | `opencode --pure -m mms/<safe-gpt-model>` | MMS-generated session-local `opencode.json` | Debug fallback |

Direct launch is also supported, for example `mms opencode --profile lite_pro` or `mmd opencode --profile lite_pro`.

## Lite Pro Roster

| Agent | Mode | Current resolved model | Fallback role | Edit policy |
| --- | --- | --- | --- | --- |
| `mobius-builder-pro` | primary | `gpt-5.5` | main worker | ask |
| `mobius-builder-stable` | primary | `gpt-5.4` | launch/builder fallback | ask |
| `mobius-explore-glm` | subagent | `glm-5-turbo` via Anthropic | primary explorer | deny |
| `mobius-explore-kimi` | subagent | `kimi-for-coding` via Anthropic | fallback explorer | deny |
| `mobius-vision-mimo` | subagent | `mimo-v2.5` via direct MiMo Anthropic | primary image helper | deny |
| `mobius-vision-kimi` | subagent | `kimi-k2.5` / `K2.6` via Anthropic | image helper fallback | deny |
| `mobius-vision-qwen` | subagent | `qwen3.6-plus` via Anthropic | image helper fallback | deny |
| `mobius-reviewer-gpt55` | subagent | `gpt-5.5` via Responses | primary release-gate reviewer | deny |
| `mobius-reviewer-gpt54` | subagent | `gpt-5.4` via Responses | stable reviewer outage fallback | deny |
| `mobius-reviewer-mimo` | subagent | `mimo-v2.5-pro` via direct MiMo Anthropic | supplemental CN/vision critique reviewer | deny |
| `mobius-fixer-deepseek` | subagent | `deepseek-v4-pro` via Anthropic | primary fixer | ask |
| `mobius-fixer-glm` | subagent | `glm-5.1` via Anthropic | fallback fixer | ask |
| `mobius-fixer-gpt54` | subagent | `gpt-5.4` | final fixer fallback | ask |

GLM/Kimi/DeepSeek/MiMo routes are cache-sensitive in the current config, so Lite Pro assigns them to Anthropic `/v1/messages`. They must not fall back to `chat/completions` silently. MiMo remains direct-only and is configured with reasoning disabled in OpenCode-generated model metadata to avoid the official `reasoning_content` tool-loop 400 until OpenCode can replay that field itself.

## Lite Pro Orchestrated

`lite_pro_orchestrated` uses the same launch shape and route guardrails as Lite Pro, but changes the work split:

- `mobius-builder-pro` / `gpt-5.5` is coordinator only: `edit=deny`, plans, delegates, inspects diffs, and accepts/rejects executor output.
- Primary executor chain: `mobius-executor-deepseek` → `mobius-executor-glm` → `mobius-executor-qwen` → `mobius-executor-gpt54`.
- `mobius-explore-qwen` is available as an extra read-only Qwen explorer for broad repo/API context.
- `mobius-vision-mimo`, `mobius-vision-kimi`, and `mobius-vision-qwen` are read-only image helpers. They are only generated when a matching image-capable route exists, so non-vision models do not falsely advertise image support.
- Review is separated from executors: `mobius-reviewer-gpt55` is the release gate, and `mobius-reviewer-gpt54` is only a reviewer-route outage fallback. The coordinator prompt tells OpenCode not to let executor/fixer agents self-approve their own output.
- `mobius-reviewer-mimo` is supplemental only: use it for CN/vision/counterexample critique when direct MiMo exists, then keep GPT as the final release gate.
- Executor agents have edit/test permissions and must return changed files, validation commands, results, risks, and blockers.
- If acceptance fails, the coordinator sends a bounded failure packet to the next executor instead of editing directly.

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

The OpenCode profile menu appends compact health hints to Lite Pro profiles, such as `health: 9/9 healthy` for `lite_pro` or `health: 14/14 healthy` for `lite_pro_orchestrated`.

## Guardrails

- Do not put agent roles in `model-routes.json`.
- Do not store API keys in OpenCode agent config; use session env vars such as `MMS_OPENCODE_API_KEY_*`.
- Keep destructive shell, deploy, push, and external directory access behind `ask` or `deny`.
- Keep `heavy_omo` global-config based until a separate audited OMO overlay is implemented.
- Do not use `K2.6` in Lite Pro through `chat/completions`; if added later, keep it on Anthropic `/v1/messages` and validate with live smoke first.
- Do not assign GLM/Kimi/DeepSeek/MiMo dual-protocol cache-sensitive routes to Lite Pro's OpenCode `chat/completions` lane; prefer Anthropic `/v1/messages`.
- Do not route MiMo through shared relays in Lite Pro; use direct MiMo only. In OpenCode-generated configs, keep MiMo `reasoning=false` unless the client path can preserve `reasoning_content` through multi-turn tool calls.
