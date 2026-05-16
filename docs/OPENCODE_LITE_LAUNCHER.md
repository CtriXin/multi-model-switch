# OpenCode Launcher Profiles

MMS launches OpenCode through fixed profiles. It does not ask the user to tune agents on every start.

## Decision

- `OpenCode Lite Pro` is the default high-confidence custom-agent lane.
- `OpenCode Lite` remains a stable single-model custom-agent lane.
- `OpenCode Heavy / OMO` keeps using the existing global OpenCode + OMO setup.
- `OpenCode Raw` is a pure fallback with no OMO and no custom agents.
- In the OpenCode tab, MMS shows this profile selector first; Lite/Lite Pro/Raw do not ask the user to choose a channel/model before profile selection.
- Lite Pro auto-resolves a deterministic multi-model roster and writes it only into session-local OpenCode config.
- Lite Pro uses mixed OpenCode providers: OpenAI-family routes use `@ai-sdk/openai-compatible`; every non-GPT route with `anthropic_messages` support uses `@ai-sdk/anthropic` and `/v1/messages`.
- Lite Pro launch runs a tiny OpenCode preflight against the primary builder route. If `builder_primary` fails and `builder_fallback` passes, MMS starts OpenCode with `mobius-builder-stable` on the fallback model instead of opening a broken session.
- MMS does not delete or rewrite global OMO config.
- MMS does not write `~/.config/opencode/opencode.json`, `~/.config/opencode/oh-my-openagent.jsonc`, or `~/.config/mms/config.toml` for this profile selection.

## Profiles

| Profile | Launch shape | Config source | Use case |
| --- | --- | --- | --- |
| `lite_pro` | `opencode --pure --agent mobius-builder-pro -m mms-builder_primary/<model>` | MMS-generated session-local multi-provider `opencode.json` | Daily coding with 5.5 primary and named fallback agents |
| `lite` | `opencode --pure --agent mobius-builder -m mms/<safe-gpt-model>` | MMS-generated session-local `opencode.json` | Stable single-model coding lane |
| `heavy_omo` | `opencode` | Existing global OpenCode + OMO config | Heavy OMO/fanout lane |
| `raw` | `opencode --pure -m mms/<safe-gpt-model>` | MMS-generated session-local `opencode.json` | Debug fallback |

## Lite Pro Roster

| Agent | Mode | Current resolved model | Fallback role | Edit policy |
| --- | --- | --- | --- | --- |
| `mobius-builder-pro` | primary | `gpt-5.5` | main worker | ask |
| `mobius-builder-stable` | primary | `gpt-5.4` | launch/builder fallback | ask |
| `mobius-explore-glm` | subagent | `glm-5-turbo` via Anthropic | primary explorer | deny |
| `mobius-explore-kimi` | subagent | `kimi-for-coding` via Anthropic | fallback explorer | deny |
| `mobius-reviewer-mimo` | subagent | `mimo-v2.5-pro` | primary reviewer | deny |
| `mobius-reviewer-deepseek` | subagent | `deepseek-v4-pro` via Anthropic | fallback reviewer | deny |
| `mobius-fixer-deepseek` | subagent | `deepseek-v4-pro` via Anthropic | primary fixer | ask |
| `mobius-fixer-glm` | subagent | `glm-5.1` via Anthropic | fallback fixer | ask |
| `mobius-fixer-gpt54` | subagent | `gpt-5.4` | final fixer fallback | ask |

GLM/Kimi/DeepSeek/MiMo routes are cache-sensitive in the current config, so Lite Pro assigns them to Anthropic `/v1/messages`. They must not fall back to `chat/completions` silently.

Fallback is deterministic, not random. There are two layers:

1. Launch fallback: `builder_primary` (`mobius-builder-pro` / `gpt-5.5`) is preflighted first. If it fails, MMS tries `builder_fallback` (`mobius-builder-stable` / `gpt-5.4`) and launches that route when healthy. Set `MMS_OPENCODE_LAUNCH_PREFLIGHT=0` to disable the live launch preflight.
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

The OpenCode profile menu appends a compact Lite Pro health hint such as `health: 9/9 healthy` or `health: 7/9 healthy, 1 degraded, 1 blocked`.

## Guardrails

- Do not put agent roles in `model-routes.json`.
- Do not store API keys in OpenCode agent config; use session env vars such as `MMS_OPENCODE_API_KEY_*`.
- Keep destructive shell, deploy, push, and external directory access behind `ask` or `deny`.
- Keep `heavy_omo` global-config based until a separate audited OMO overlay is implemented.
- Do not use `K2.6` in Lite Pro until a live OpenCode `chat/completions` smoke proves that route is safe.
- Do not assign GLM/Kimi/DeepSeek/MiMo dual-protocol cache-sensitive routes to Lite Pro's OpenCode `chat/completions` lane; prefer Anthropic `/v1/messages`.
