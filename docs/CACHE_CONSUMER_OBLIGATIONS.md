# Cache Consumer Obligations

> Date: 2026-04-29
> Scope: every project that resolves model routes via MMS and makes
> direct provider calls (Hive / Pilot / Ant / Moebius / agent-soul /
> any future MMS-extending tool).
> Companion doc: `SERVER_CLAUDE_CACHE_RUNBOOK.md` (server side).

## Why this doc exists

The cache hit rate dashboard on 2026-04-29 showed extreme disparity
across CN models routed through the same `newapi-personal-tokyo`
gateway:

| Model | Calls | Hit |
|---|---|---|
| kimi-for-coding | 1371 | 84.1% |
| kimi-k2.5 | 160 | 82.6% |
| deepseek-v4-pro | 205 | 38.9% |
| qwen3.6-plus | 864 | 13.2% |
| glm-5 | 54 | 6.0% |
| qwen3-max | 87 | 0.0% |

All these models route through dual-URL endpoints (anthropic +
openai_chat). The disparity is not an MMS routing problem and not a
gateway problem (kimi works, so the gateway is capable). It is a
**caller-side discipline problem** — most callers default to OpenAI
chat completions and never set `cache_control`, so Anthropic prompt
cache never engages.

Without consumer discipline, ten projects extending MMS will each
re-discover this same lesson at the cost of thousands of cache misses.

## The four rules

If your project consumes MMS routes and calls providers directly
(rather than going through MMS bridge), you MUST do the following:

### Rule 1 — protocol selection: anthropic_first for CN models

When a route exposes both `anthropic_base_url` and `openai_base_url`,
**default to anthropic_messages** for any model in these families:

- `kimi-*`
- `qwen*`
- `glm-*`
- `deepseek-*`
- `mimo-*`
- `minimax-*`

Only fall back to openai_chat when:
- the route exposes only `openai_base_url`, or
- explicit user override (`--protocol openai`, debug flag, etc.)

The provider profiles in `config/provider-profiles.json` declare both
protocols are available for these vendors. The choice is the caller's
responsibility, not the profile's.

Pseudocode:
```python
def select_protocol(route, model_id):
    if matches_cn_family(model_id) and route.anthropic_base_url:
        return "anthropic_messages"
    if route.openai_base_url:
        return "openai_chat"
    if route.anthropic_base_url:
        return "anthropic_messages"
    raise NoTransportAvailable()
```

### Rule 2 — cache_control on system block

When using `anthropic_messages` protocol, the request `system` field
**must be an array of blocks** (not a string), and the cached prefix
block(s) **must carry** `cache_control: { type: "ephemeral" }`:

```ts
system: [
  { type: "text", text: baseInstructions },
  { type: "text", text: soulCardOrPromptBody,
    cache_control: { type: "ephemeral" } }
]
```

Without `cache_control`, the gateway will not cache the prefix even if
your bytes are stable. This is a strict requirement of Anthropic's
prompt cache, not an optional optimization.

For `openai_chat` protocol, no `cache_control` field exists; the
gateway uses implicit prefix cache. Byte-stability of the system
message is the only lever you have.

## The third (often overlooked) rule

### Rule 3 — system prompt byte-stability

Whatever protocol you use, the **system block content MUST be
byte-stable across calls** that should share cache. Specifically:

- No `run_id` in system body
- No timestamps in system body
- No commit hashes in system body (unless the cache scope is exactly
  one commit)
- No randomly-ordered fields (sort keys when serializing JSON)

If any of these are needed, put them in:
- the user message, or
- a custom HTTP header (gateway typically ignores in cache key), or
- request metadata (out of prompt body)

Pilot's pre-2026-04-29 pattern of embedding `run_id` in system prompt
is the canonical anti-example: every pilot-run got a fresh cache key,
guaranteeing zero cross-run cache benefit no matter how many other
things were correct.

### Rule 4 — runtime evidence must be actual

Every direct model call must write `cache_transport_evidence.v1` to the
project's run artifact, worker result, or review result. See
`docs/MODEL_CONFIG_CONTRACT.md` for the exact minimal shape.

The evidence must be based on the real selected transport, not only the
logical model route:

- `protocol`: `anthropic_messages`, `openai_chat_completions`, or
  `openai_responses`
- `request_url` or `request_path`: the actual upstream target path
- `provider_id`: the selected MMS provider/channel
- `fallback_used` and `fallback_reason`: non-empty reason for any audited
  fallback to OpenAI chat on a cache-sensitive non-OpenAI-family route
- `usage.cache_read_input_tokens`, `usage.cache_creation_input_tokens`, and
  `usage.cached_tokens`: normalized from provider response usage fields

Do not report only semantic labels such as `claude_style`, `anthropic`, or
`openai`. If a direct SDK path cannot observe the final URL, record
`evidence_source: "resolved_route"` and still include the resolved route's
concrete request path. Proxy/adapter paths must record the actual upstream URL.

## Validation checklist

Before merging any PR that touches direct provider calls, run this:

1. Call your code path twice with the same input within 5 minutes.
2. Inspect the second response's `cache_read_input_tokens` (Anthropic)
   or equivalent OpenAI usage field.
3. If `cache_read_input_tokens > 0`: pass.
4. If `0`: one of the three rules is broken. Diff the request bodies
   to find which.

For automated validation, every project should have tests that assert:

- CN dual route first attempt is `/v1/messages`
- DeepSeek through NewAPI first attempt is `/v1/messages`
- GPT/OpenAI-family first attempt is `/v1/chat/completions` or `/v1/responses`
- OpenAI chat fallback on cache-sensitive routes has `fallback_reason`
- worker/run result includes `cache_transport_evidence.v1`

## Per-project status reference

As of 2026-04-29 the following remediation work is in flight (will be
removed from this section as commits land):

| Project | Issue | Fix path |
|---|---|---|
| Hive | `inferProtocolPreference()` defaults to openai_chat for newapi-tokyo dual URLs (provider-profiles.ts:204) | add CN family short-circuit; add cache_control |
| Ant | `mms.ts:115-117` selects openai_first; system passed as string | reverse default; convert system to array with cache_control |
| Pilot | `pilot_run.py:2112,4416` embeds run_id into system_prompt | move run_id out of system body |
| Moebius | review pack instructions may pull in commit hash; downstream consumers see varying system | isolate run-specific metadata from reviewer-visible instruction body |

Once all four land, this table moves to a "verified" section.

## Future MMS-extending projects

If you build a new project that consumes MMS routes:

- Read this doc before writing any provider call.
- Reuse the loader pattern from `mms_registry/provider_profiles.py` (Python) or
  the cross-language `loadProfiles / matchProfile / applyProfile` API
  documented in `PROVIDER_PROFILES.md`.
- Write your protocol selection following Rule 1.
- Write your request shape following Rule 2 + Rule 3.
- Add a cache validation test before merging (Rule 4 of validation).

A project that does not follow these obligations is silently doubling
or quintupling its provider cost. The discipline is cheap; the
violation is expensive at scale.

## Companion docs

- `PROVIDER_PROFILES.md` — what each profile declares (data contract)
- `SERVER_CLAUDE_CACHE_RUNBOOK.md` — server-side (gateway) cache config
- This doc — client-side (caller) cache obligations

Together these three define the full cache discipline contract.
