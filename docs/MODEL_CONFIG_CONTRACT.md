# MMS Model Config Contract

This document is the baseline contract for projects that consume MMS model
configuration. New v2 consumers should start from the verified
latest-approved manifest instead of creating a project-local model registry or
reading legacy root files as primary truth.

Canonical consumer entrypoint:

```text
<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json
```

Hive / Pilot / Ant / Moebius / Mobius and future downstream consumers MUST use
that manifest, or a resolver that verifies it, as their first read. They MUST
NOT read `model-routes.json`, `model-policy.json`, or `provider-profiles.json`
from the config root as primary truth. They MUST NOT query SQLite tables
directly.

## Generated Bundle Surfaces

| File | Owner | Sensitivity | Purpose |
|---|---|---|---|
| `generated/model-routes.json` | MMS generated export | Secret | Provider route data: `primary`, `fallbacks`, URL, API key, provider id, wire `model_id`. |
| `generated/model-routes.lineup.json` | MMS generated export + metadata merge | Non-secret | Model metadata: context window, references, display/capability metadata, pricing/tier fields. |
| `generated/provider-profiles.generated.json` | MMS generated export | Non-secret | Effective provider protocol differences: auth headers, body patches, protocol preference, wire aliases, context references. |
| `generated/model-policy.effective.json` | MMS generated export | Non-secret | Effective user/project policy: hide/show, favorite, allow/deny per project, downgrade, project priority. |

`generated/model-routes.json` is the only generated bundle file that should
contain API keys. Do not copy it into public artifacts or docs.

Legacy root files such as `model-routes.json`, `model-routes.lineup.json`,
`provider-profiles.json`, and `model-policy.json` may still exist for
compatibility, backup, import/export, or human source-overlay migration. They
are not the v2 consumer entrypoint and must not be treated as independent
truth.

## Reference Evidence

MMS keeps source/reference snapshots under `docs/reference/`. The current model
capability calibration snapshot lives at:

- `docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.md`
- `docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json`

These files are evidence inputs for registry import/refresh. They are not live
runtime truth and should not be consumed directly by downstream projects.
Runtime consumers should keep reading the approved Router / Lineup / Profile /
Policy surfaces documented below.

## Latest-Approved Bundle

Local Registry v2 introduces a single consumer-facing latest-approved bundle.
New consumers should treat this manifest as the canonical entrypoint:

```text
<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json
```

The bundle pins every generated export to one approved revision set:

```json
{
  "schema": "mms.model_registry.latest_approved.v1",
  "bundle_revision": "bundle_20260522_001",
  "model_registry_revision": "bundle_20260522_001",
  "capability_revision": "cap_20260522_001",
  "route_revision": "route_20260522_001",
  "policy_revision": "policy_20260522_001",
  "profile_revision": "profile_20260522_001",
  "generated_at": "2026-05-22T00:00:00.000Z",
  "files": {
    "router": {
      "canonical_path": "generated/model-routes.json",
      "legacy_alias_path": "model-routes.json",
      "sha256": "<hex>",
      "sensitivity": "secret"
    },
    "lineup": {
      "canonical_path": "generated/model-routes.lineup.json",
      "legacy_alias_path": "model-routes.lineup.json",
      "sha256": "<hex>",
      "sensitivity": "non-secret"
    },
    "profile": {
      "canonical_path": "generated/provider-profiles.generated.json",
      "legacy_alias_path": "",
      "sha256": "<hex>",
      "sensitivity": "non-secret"
    },
    "policy": {
      "canonical_path": "generated/model-policy.effective.json",
      "legacy_alias_path": "model-policy.json",
      "sha256": "<hex>",
      "sensitivity": "non-secret"
    }
  }
}
```

Bundle rules:

- The manifest is the v2 canonical consumer contract; legacy root files remain
  compatibility aliases/copies, not independent truth.
- Generated v2 exports MUST carry the same `model_registry_revision` or
  `bundle_revision` when their strict legacy shape allows it. If a legacy root
  file must stay shape-compatible, the manifest hash is the revision tie.
- Consumers must verify per-file hashes and must not combine route, lineup,
  profile, or policy files from different bundles.
- Publishing uses atomic temp-file + rename: write canonical payloads first,
  refresh legacy aliases, then rename the manifest last.
- `provider-profiles.generated.json` and `model-policy.effective.json` are
  consumer-facing only when referenced by the manifest; human-maintained source
  files stay separate.
- Current MMS runtime adoption is resolver-scoped: provider profiles and
  capability facts are loaded from the verified manifest first, then legacy
  files/conservative defaults are used only when the manifest is missing,
  invalid, or hash-mismatched. Candidate/source snapshots are not runtime input.
- Router read-side adoption is also conservative:
  `mms_router.export_model_routes(force=False)` and
  `validate_model_config_bundle()` read verified generated router/lineup/policy
  first; explicit `force=True` still regenerates legacy root aliases from
  current config. Provider/account priority and bridge routing stay on the
  existing path.

See `docs/REGISTRY_ARCHITECTURE.md` for the full source/candidate/approved/
runtime/health layer contract, `privacy_boundary` gates, deletion/tombstone
rules, and reference-snapshot ingestion boundaries.

## Responsibilities

| Question | Answer |
|---|---|
| What do I read first? | Read `<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json`, verify per-file hashes, then load only the generated files it references. |
| How do I call a model? | Use the manifest-referenced generated Router; use `primary` first, then `fallbacks` in order for transient provider failures. |
| What is the model context window? | Use the manifest-referenced generated Lineup/Capabilities; field: `routes[model].primary.max_context_tokens` when present. |
| Why does a provider need a special body/header/model alias? | Use the manifest-referenced generated Profile. |
| Should this model be visible or preferred in a specific project? | Use the manifest-referenced generated effective Policy. |
| Where should a display name live? | DB/policy source owns human intent; generated Policy/Lineup expose the effective consumer view. |
| Where should a wire alias live? | DB/profile source owns the rule; generated Router/Lineup materialize it as `model_id`. |

## File Shapes

### `model-routes.json`

```json
{
  "version": 1,
  "generated_at": "2026-05-08T00:00:00.000Z",
  "routes": {
    "deepseek-v4-pro": {
      "primary": {
        "provider_id": "deepseek-direct",
        "anthropic_base_url": "https://api.deepseek.com/anthropic",
        "openai_base_url": "",
        "api_key": "sk-...",
        "model_id": "deepseek-v4-pro[1m]"
      },
      "fallbacks": []
    }
  }
}
```

### `model-routes.lineup.json`

```json
{
  "version": 1,
  "generated_at": "2026-05-08T00:00:00.000Z",
  "source_routes_hash": "<sha256 of canonical model-routes payload>",
  "routes": {
    "deepseek-v4-pro": {
      "primary": {
        "provider_id": "deepseek-direct",
        "model_id": "deepseek-v4-pro[1m]",
        "max_context_tokens": 1000000,
        "context_source": "provider-profiles.json",
        "context_reference_url": "https://api-docs.deepseek.com/",
        "context_reference_checked_at": "2026-05-08T00:00:00.000Z"
      },
      "fallbacks": []
    }
  }
}
```

Lineup must not contain `api_key`, `anthropic_base_url`, or `openai_base_url`.
MMS preserves known human-maintained metadata fields while regenerating route
derived fields. Profile-owned fields such as `model_id`, `max_context_tokens`,
`context_source`, and context reference URLs are overwritten on export so Lineup
does not keep stale provider metadata.

### `provider-profiles.json`

Provider profiles are MMS-owned declarative source data. They are used for:

| Field family | Purpose |
|---|---|
| `match` | Match provider/model/base URL to this profile. |
| `auth_headers` | Select Authorization / `x-api-key` header behavior per protocol. |
| `body_patches` | Apply vendor-specific request body patches. |
| `parameter_aliases` | Rename caller intent fields per protocol without hardcoded consumer branches, for example MiMo OpenAI `max_tokens` to `max_completion_tokens`. |
| `model_aliases` | Convert logical model id to provider wire model id. |
| `context_windows` | Source context metadata for Lineup export. |
| `references` | Source reference URLs for Lineup export. |

### `model-policy.json`

```json
{
  "version": 1,
  "updated_at": "2026-05-08T00:00:00.000Z",
  "models": {
    "mimo-v2.5-pro": {
      "visible": true,
      "favorite": false,
      "tier": "secondary",
      "hide_in": ["hive"],
      "show_in": ["mms", "agent-soul"],
      "downgrade_to": "mimo-v2.5"
    }
  },
  "projects": {
    "agent-soul": {
      "default_visible": true,
      "allowed_models": [],
      "hidden_models": [],
      "favorite_models": []
    },
    "hive": {
      "default_visible": false,
      "allowed_models": ["deepseek-v4-flash", "kimi-for-coding"],
      "hidden_models": []
    }
  }
}
```

The policy file is user-owned overlay data. MMS may provide commands to edit it,
but route export must not overwrite human policy entries. A project can use
`default_visible: false` plus `allowed_models` as a compact whitelist; consumers
must treat every other Router model as hidden for that project. `hidden_models`
and `disabled_models` are explicit deny overlays.

Validation treats stale `hidden_models` / `disabled_models` entries as benign:
they can intentionally suppress retired aliases if those aliases return later.
Unknown `allowed_models` and `favorite_models` still warn because they imply a
model the current Router/Lineup cannot actually provide.

Current official execution surface for MMS consumers (`mms`, `hive`, `pilot`,
`ant`, `moebius`/`mobius`) is exposed through the manifest-referenced effective
Policy. During migration, legacy `model-policy.json` remains a compatibility or
source-overlay surface, not the downstream source of truth:

| Family | Models |
|---|---|
| DeepSeek | `deepseek-v4-flash`, `deepseek-v4-pro` |
| MiMo | `mimo-v2.5`, `mimo-v2.5-pro` |
| Kimi | `kimi-for-coding`, `kimi-k2.5`, `K2.6` |
| Qwen | `qwen3-coder-plus`, `qwen3.5-plus`, `qwen3.6-plus` |
| GLM | `glm-5-turbo`, `glm-5.1` |
| MiniMax | `MiniMax-M2.7` |
| Gemini / Antigravity | `gemini-3-flash-agent(high)`, `gemini-3-flash-agent(medium)`, `gemini-3-flash-agent(low)`, `gemini-3-flash-agent(none)`, `gemini-3.1-flash-lite`, `gemini-3.1-pro-low` |
| Claude / Antigravity | `claude-sonnet-4-6`, `claude-opus-4-6-thinking` |
| GPT / OpenAI | `gpt-5.3-codex`, `gpt-5.3-codex-spark`, `gpt-5.4`, `gpt-5.5`, `gpt-image-2` |

`K2.6` is intentionally classified under the Kimi family by policy. `gpt-5.3-codex-spark`
uses the CPA local Codex channel (`us-cpa-local-codex`). The old Gemini preview
surface (`gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`, `gemini-3.1-pro-preview`)
is retired from the official policy surface; current Gemini 3.5/3.1 access goes
through the CPA Antigravity provider (`us-cpa-local-antigravity`). Agent Soul is
not narrowed by this execution whitelist so its draw/image and Jimeng-specific
surfaces can stay project-owned until explicitly migrated.

## Consumer Rules

| Consumer | Required behavior |
|---|---|
| Hive | Verify latest-approved manifest; resolve provider URL/key from manifest-referenced Router; context/display/policy from Lineup/Policy; provider quirks from Profile; emit `cache_transport_evidence.v1` in `WorkerResult`. |
| Pilot | Verify latest-approved manifest; resolve model routes from manifest-referenced Router; planning pool metadata from Lineup/Policy; persist each call's `cache_transport_evidence.v1` in run artifacts. |
| Ant | Verify latest-approved manifest; resolve execution models through manifest-referenced Router; provider quirks from Profile; packet `fallback_chain` remains task-level fallback; include `cache_transport_evidence.v1` in worker results. |
| Moebius / Mobius | Verify latest-approved manifest; prefer manifest-referenced Lineup/Policy for planning and audit; do not read API keys unless dispatching through Ant/Hive; gates must consume downstream `cache_transport_evidence.v1`. |
| Agent Soul local | Verify latest-approved manifest; Router for text-model URL/key; Lineup for context/reference; Policy for visibility; Jimeng stays Agent Soul-owned. |
| Agent Soul online | Sync server-private generated bundle files during deploy; never fold Jimeng keys into MMS files. |

Consumers that adopt Local Registry v2 must resolve through the latest-approved
bundle manifest or a future `mms registry resolve` API. They must not read the
SQLite schema directly, and they should record `bundle_revision`,
`capability_revision`, `route_revision`, `policy_revision`, and
`profile_revision` in run artifacts.

## Runtime Transport And Cache Evidence

Every project that resolves MMS routes and makes model calls must emit the same
minimal evidence object into its run artifact, worker result, or review result.
This is a runtime output contract, not another route table.

```json
{
  "schema": "cache_transport_evidence.v1",
  "model": "deepseek-v4-flash",
  "provider_id": "newapi-personal-tokyo",
  "protocol": "anthropic_messages",
  "request_url": "http://127.0.0.1:4001/v1/messages",
  "request_path": "/v1/messages",
  "route_source": "mms:latest-approved/generated/model-routes.json",
  "provider_profile": "deepseek",
  "fallback_used": false,
  "fallback_reason": "",
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_input_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cached_tokens": 0
  }
}
```

### Evidence Rules

| Rule | Required behavior |
|---|---|
| Actual URL/path | Evidence must include a real `request_url` or at least the concrete `request_path`; semantic labels such as `claude_style` or `anthropic` are not enough. |
| Protocol names | Use canonical values: `anthropic_messages`, `openai_chat_completions`, or `openai_responses`. |
| Cache-sensitive default | For CN / dual-protocol / cache-sensitive routes, if `anthropic_base_url` exists, default to `anthropic_messages`. |
| OpenAI-family exception | `gpt-*`, `o*`, `codex-*`, and other OpenAI-family models may default to OpenAI chat/responses and must not treat mirrored `anthropic_base_url` as Anthropic. |
| Audited chat fallback | `openai_chat_completions` for a non-OpenAI-family cache-sensitive route is allowed only as a fallback and must set a non-empty `fallback_reason`. |
| Usage normalization | Anthropic cache fields map from `cache_read_input_tokens` and `cache_creation_input_tokens`; OpenAI cache maps from `usage.prompt_tokens_details.cached_tokens`, `cached_tokens`, or `cache_read_tokens`. |
| Router minimalism | Do not add context, display, or evidence fields to `model-routes.json`; context remains in Lineup, behavior remains in Profile, and evidence is emitted by runtime artifacts. |

### Gate Expectations

Moebius/Mobius gates and any future review launcher should treat missing or
weak evidence as a routing risk:

| Condition | Expected gate behavior |
|---|---|
| No `cache_transport_evidence.v1` for a real model call | Block or at least High warning, depending on stage policy. |
| Evidence lacks `request_url` and `request_path` | Block or High warning. |
| Cache-priority high slot uses a protocol different from the selected default without `fallback_reason` | Block. |
| `openai_chat_completions` fallback has empty `fallback_reason` | Block. |

Projects may add extra fields, but consumers must not require extra fields to
validate the minimal contract above.

## Consistency Checks

For v2 consumers, first verify the published manifest:

```bash
mms registry verify
```

Legacy alias consistency can still be checked during migration with:

```bash
mms routes check
```

The checks verify:

| Check | Reason |
|---|---|
| Router and Lineup route keys match | Prevent UI-visible models that cannot dispatch, or dispatchable models missing context metadata. |
| Router primary/fallback endpoints are complete | Prevent provider fallback failure caused by missing URL/key/provider. |
| Lineup has no secrets | Keep metadata safe to expose to UI/planners. |
| `source_routes_hash` matches Router | Detect stale Lineup after Router changed. |
| Policy entries point at known models | Detect stale hide/show/favorite rules. |

MMS also writes `model-config.audit.ndjson` on route export changes. The audit
log records the actor, changed files, route count, hashes, and issue count.

## Current Migration Status

MMS has a preview latest-approved publish/verify loop and selected read-side
adoption for generated Router, Lineup, Policy, Profile, and capability facts.
Stable `mms` defaults still preserve legacy behavior while `mmf` uses the
preview config root.

Downstream projects should migrate toward the manifest/resolver contract and
stop maintaining independent context tables or reading root legacy files as
primary truth. Legacy route/policy/profile files remain compatibility,
backup, import/export, or source-overlay surfaces until each consumer is cut
over.
