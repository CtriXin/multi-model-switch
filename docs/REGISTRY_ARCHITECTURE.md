# MMS Registry Architecture

This document freezes the Local Registry v2 compatibility contract for
implementation work. It describes the registry boundaries and acceptance
criteria; it does not implement the runtime SQLite layer.

## Non-Goals

- Do not write real `~/.config/mms/**` during docs or test-only contract work.
- Do not store plaintext credentials, OAuth state, or Claude config in the
  registry.
- Do not make downstream projects depend on the SQLite schema.
- Do not treat reference snapshots or provider catalogs as runtime truth.
- Do not change launcher, bridge, or TUI runtime behavior from this document.

## Truth Layers

| Layer | Definition | Mutable by | Runtime default? |
|---|---|---|---|
| `source_truth` | Raw evidence: official docs, provider catalogs, gateway `/models`, imported local files, runtime observations, and captured `source_snapshot` files. | Refresh/import/probe jobs. | No. |
| `candidate_truth` | Parsed or edited facts that are not yet approved: new routes, changed capability facts, stale/missing observations, policy drafts, and reference-ingestion diffs. | Refresh/import/TUI draft actions. | No, except explicit preview/opt-in session. |
| `approved_truth` | Immutable promoted registry revision used to publish the consumer-facing latest-approved bundle. | Explicit promotion, safe auto-promote gates. | Yes. |
| `runtime_truth` | Per-run pinned effective bundle plus selected model, route, profile, policy, and recorded health result for that run. | Launcher/resolver at run start, runtime evidence writer. | Yes, for that run only. |
| `health_overlay` | Fast TTL state for key/route/provider health: 401/403/429, quota, 5xx, timeout, circuit breaker, latency, cache/cost observations. | Runtime telemetry. | Overlay only; never rewrites approved truth. |

Layer rules:

- `candidate_truth` cannot silently replace `approved_truth`.
- `runtime_truth` must record the bundle and component revisions it used.
- `health_overlay` may avoid or down-rank a route for the TTL window, but it
  must not change capability, policy, route, or profile revisions.
- Downstream projects consume `approved_truth` through the latest-approved
  bundle or resolver, never by querying registry tables directly.

## Revision Classes

The registry publishes one bundle revision that pins four component revisions:

| Revision | Owns |
|---|---|
| `bundle_revision` | The atomic consumer-facing publish unit. |
| `capability_revision` | Source-backed model capabilities: context, max output, modality, tools, thinking controls, supported parameters, pricing units. |
| `route_revision` | Provider id, route group, base URLs, wire model id, fallback chain, secret references, validation state. |
| `policy_revision` | Visibility, favorites, hide/show, project policy, downgrade/fallback policy, ordering hints. |
| `profile_revision` | Provider protocol quirks: auth headers, body patches, aliases, context/profile references. |

`health_overlay` is intentionally not a revision. It is fast, reversible, and
TTL-bound.

## Latest-Approved Bundle Contract

Canonical consumer entrypoint:

```text
~/.config/mms/generated/model-registry.latest-approved.json
```

The latest-approved bundle manifest MUST contain:

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
      "sensitivity": "secret",
      "legacy_alias_compat": true
    },
    "lineup": {
      "canonical_path": "generated/model-routes.lineup.json",
      "legacy_alias_path": "model-routes.lineup.json",
      "sha256": "<hex>",
      "sensitivity": "non-secret",
      "legacy_alias_compat": true
    },
    "profile": {
      "canonical_path": "generated/provider-profiles.generated.json",
      "legacy_alias_path": "",
      "sha256": "<hex>",
      "sensitivity": "non-secret",
      "legacy_alias_compat": false
    },
    "policy": {
      "canonical_path": "generated/model-policy.effective.json",
      "legacy_alias_path": "model-policy.json",
      "sha256": "<hex>",
      "sensitivity": "non-secret",
      "legacy_alias_compat": true
    },
    "capabilities": {
      "canonical_path": "generated/model-capabilities.approved.json",
      "legacy_alias_path": "",
      "sha256": "<hex>",
      "sensitivity": "non-secret",
      "legacy_alias_compat": false
    }
  }
}
```

Bundle rules:

- New v2 consumers MUST read the manifest first, verify per-file hashes, and
  record `bundle_revision` or `model_registry_revision` in run artifacts.
- Generated v2 exports MUST carry the same `model_registry_revision` or
  `bundle_revision` as the manifest.
- Legacy root files may remain strict v1 compatibility aliases when adding new
  fields would break existing consumers. In that case the manifest is the
  source of the revision tie and the root file is not a standalone v2 surface.
- Downstream projects MUST NOT assemble mixed route/profile/policy/capability
  revisions manually.
- `provider-profiles.generated.json` and `model-policy.effective.json` are
  generated consumer-facing artifacts only when referenced by the manifest.
  Human-maintained source files remain separate inputs.

## Atomic Publish

The publish process MUST use atomic temp-file + rename semantics:

1. Build every export from the same approved registry revision set.
2. Write each payload to a temp file in the same filesystem directory.
3. Flush and rename each canonical payload into `generated/*`.
4. Refresh any legacy root alias after the canonical payload is durable.
5. Write the manifest temp file last, with final hashes for canonical payloads
   and aliases.
6. Rename the manifest last. Consumers treat this rename as the bundle publish
   point.

If a consumer sees a missing file or hash mismatch, it must reject that bundle
and keep using its previously verified bundle or fail closed.

## Canonical Files And Legacy Aliases

| Surface | Canonical in v2 | Legacy root alias | Notes |
|---|---|---|---|
| Router | `generated/model-routes.json` | `model-routes.json` | Only surface that may contain `api_key`; new consumers should use manifest hash. |
| Lineup | `generated/model-routes.lineup.json` | `model-routes.lineup.json` | Non-secret capability/display export. |
| Provider profile | `generated/provider-profiles.generated.json` | none by default | Consumer-facing effective profile, not human source profile. |
| Policy | `generated/model-policy.effective.json` | `model-policy.json` compatibility input/export as needed | Effective policy export must preserve human policy source semantics. |
| Capabilities | `generated/model-capabilities.approved.json` | none | Source-backed approved capability facts for resolver use; optional but recommended. |
| Manifest | `generated/model-registry.latest-approved.json` | none | Canonical latest-approved bundle entrypoint. |

Legacy root files exist for compatibility. They are aliases/copies, not a second
source of truth.

## Current CLI Entrypoints

The first live implementation exposes a conservative publish/verify loop:

```text
mms registry refresh-sources
mms registry refresh-sources --if-due
mms registry check-staleness
mms registry scheduled-refresh
mms registry fetch-openrouter-catalog
mms registry diff-openrouter-catalog
mms registry publish-approved
mms registry verify
mms registry resolve <model>
```

Rules:

- `refresh-sources` imports local reference snapshots into SQLite
  `source_snapshot`, `source_check`, `model_identity`, and `model_fact` tables
  only.
- `check-staleness` is read/metadata-only for source freshness: it reports
  missing, changed, and max-age-exceeded source references without promoting
  runtime truth.
- `refresh-sources --if-due` updates only sources whose `source_check` state is
  missing, content-changed, or stale. This is the safe hook for a future
  scheduled job because it avoids full network/startup refresh behavior.
- `scheduled-refresh` is the safe wrapper for cron/launchd/manual runs. It
  runs local reference refresh only when due, optionally refreshes OpenRouter
  provider-catalog evidence when due, and writes only `source_snapshot`,
  `source_check`, and `candidate_change` evidence. It must not be wired into
  MMS startup.
- `scheduled-refresh --no-network` never fetches remote catalogs; it may still
  import a local `--openrouter-from-file` payload for reproducible testing or
  offline evidence capture.
- `scheduled-refresh --dry-run` reports due state without importing source or
  candidate rows beyond opening/migrating the selected SQLite DB.
- `fetch-openrouter-catalog` explicitly fetches or imports OpenRouter
  `/api/v1/models` into `source_snapshot` as `provider_catalog` evidence; it
  does not promote prices/context/supported-parameter changes into runtime
  defaults by itself.
- `diff-openrouter-catalog` compares the latest OpenRouter source snapshot with
  the latest calibration snapshot's OpenRouter references and writes
  `candidate_change` rows. These rows are review evidence only until a later
  promotion action approves them.
- `publish-approved` writes `generated/*` and
  `generated/model-registry.latest-approved.json`; it does not edit legacy root
  aliases or runtime defaults.
- `verify` checks manifest hashes before a consumer should trust the bundle.
- `resolve <model>` reads the verified latest-approved capability facts and
  falls back through the existing resolver stack when individual facts are
  incomplete; a missing or hash-mismatched manifest fails closed.

## Current Runtime Adoption

MMS now uses the latest-approved bundle for the low-risk resolver surfaces:

- `mms_registry.provider_profiles.load_provider_profiles()` first verifies the manifest,
  then reads `generated/provider-profiles.generated.json`.
- `mms_registry.capability_resolver.resolve_model_capabilities()` first verifies the
  manifest, then reads `generated/model-capabilities.approved.json`.
- `mms_launchers._lookup_context_window()` and the TUI capability summary only
  accept approved context facts when the resolver marks the field source as
  `approved_facts`.
- `mms_router.export_model_routes(force=False)` and
  `mms_router.validate_model_config_bundle()` read the verified generated
  router/lineup/policy payloads first; explicit `force=True` still regenerates
  legacy root aliases from current config.

Fallback is intentionally conservative:

- Missing manifest, invalid JSON, hash mismatch, or missing capability/profile
  payload means MMS falls back to the legacy built-in/user profile files or
  conservative capability defaults.
- Candidate/source snapshots are never read by runtime resolver paths.
- Launcher/provider/account selection and bridge routing are unchanged in this
  phase.

## Privacy Boundary

Every route group and provider route must expose a `privacy_boundary`:

| Value | Meaning |
|---|---|
| `private` | Single-user/private key, local relay, or route whose prompts must not automatically leave the private boundary. |
| `team` | Shared trusted team/provider account with an explicit team data boundary. |
| `public` | Public SaaS/provider route approved for public-provider dispatch. |

Privacy rules:

- Missing, empty, or unknown privacy is treated as conservative `private`.
- Automatic fallback across different boundaries is blocked unless an explicit
  allow rule names both source and target boundary plus provider/route ids.
- Same-family auto-upgrade still requires privacy, capability, context, health,
  and cost-policy checks.
- Auto-promote of a new route is blocked unless privacy is declared or resolved
  to conservative private and no cross-boundary fallback is introduced.
- Provider catalog references such as OpenRouter do not define local privacy.
  Privacy must come from local route metadata or an explicit approval event.

## Deletion, Tombstone, And Purge

Refresh absence is not deletion:

- Provider catalog missing a model means `candidate_truth` receives a
  stale/missing observation.
- Gateway `/models` missing a model means route validation needs review.
- Imported local file absence means a candidate diff, not a tombstone.

Tombstone rules:

- Tombstone must come from an explicit TUI/action event with actor, timestamp,
  route/model id, reason, and `last_approved_revision`.
- Candidate deletion must not alter the latest-approved bundle until promoted.
- Tombstoned entries remain recoverable and searchable with
  `restore_available=true`.
- Physical purge requires retention expiry, a fresh backup/export, and second
  confirmation. Purge is never inferred from refresh absence.

## Reference Snapshot Ingestion Boundary

Files under `docs/reference/model-capability-calibration/*` are
`source_snapshot` inputs. They are evidence for importer/candidate generation,
not runtime truth.

Ingestion must preserve these layers:

| Layer | Examples | Promotion rule |
|---|---|---|
| `official` | Vendor model pages, official product docs. | Can become capability facts when exact enough. |
| `provider_catalog` | OpenRouter route id, context, max output, supported parameters, pricing. | Provider catalog reference only; it does not overwrite official facts silently. |
| `runtime` | Gateway `/models`, smoke result, transport evidence. | Route/health/candidate evidence, not official capability truth. |
| `local_alias` | MMS selectors like `[1m]`, `-low`, `-openai-canary`. | Local alias metadata; never sent as vendor official id unless profile says so. |

Thinking control must not be collapsed into only true/false:

- Gemini 3 / 3.1 / 3.5 preserve `thinkingConfig.thinkingLevel`.
- Gemini 2.5 preserves numeric `thinkingConfig.thinkingBudget`.
- GLM preserves `thinking.type` and reasoning-content persistence semantics.
- Provider `reasoning` / `include_reasoning` support remains provider request
  compatibility metadata, not vendor-official thinking-budget evidence.

## Downstream Compatibility

Downstream projects:

- MUST consume the latest-approved bundle manifest, generated exports, or
  `mms registry resolve` when that resolver exists.
- MUST NOT query SQLite tables or depend on table/column names.
- SHOULD record `bundle_revision`, `capability_revision`, `route_revision`,
  `policy_revision`, and `profile_revision` in run artifacts when making model
  calls.
- MUST keep emitting `cache_transport_evidence.v1` for actual calls.
- MUST fail closed on manifest hash mismatch, mixed revisions, missing secret
  route fields, or missing required transport evidence.

## Acceptance Criteria Matrix

| ID | Contract requirement |
|---|---|
| A1 / R1 | Latest-approved bundle manifest is canonical and prevents mixed capability/route/profile/policy revisions. |
| A2 / R2 | Protected runtime files stay thin; registry integration should use adapter/resolver modules. |
| A3 / R3 | `privacy_boundary` is explicit; missing means conservative private; cross-boundary fallback needs explicit allow. |
| A4 / R4 | Rescue artifacts must be secret-safe and metadata-only in global indexes. |
| A5 / R5 | Absence during refresh is not deletion; tombstone and purge require explicit events. |
| A6 / R6 | Real config root writes must go through approved helpers and human gates; docs/tests here do not write real config. |
| A7 / R7 | Blocking tests include export/profile/fail-closed suites plus new registry contract tests. |
| R8 | Reference snapshots are source evidence only; OpenRouter is provider catalog reference, not vendor official truth. |
| R9 | Thinking-control ingestion preserves raw semantic knobs rather than boolean-only support. |
| R10 | Downstream compatibility is manifest/export/resolver based; direct SQLite schema dependency is forbidden. |
