# MMF Config Root v2 / DB Truth Boundary

Date: 2026-05-26
Owner: Codex
CLI: codex
Model: GPT-5
Status: active draft
Task ID: mmf-config-root-v2-db-truth

## Executive Summary

MMS configuration should converge from many human-edited files into one human-facing control surface: `TUI / mms config / WebUI`; internally `DB + secret backend` becomes the canonical truth, and downstream projects consume one verified latest-approved bundle.

The transition should happen in an isolated future root first:

```text
mms -> ~/.config/mms       # current stable legacy root
mmf -> ~/.config/mms-next  # future preview root via MMS_CONFIG_ROOT
```

`mmf` is a thin wrapper / mode selector, not a forked product. Default `mms` behavior must stay unchanged until the new root is imported, verified, smoked, and intentionally promoted.

## User Intent

The user wants MMS configuration to stop feeling scattered. Future human operation should be:

```text
open WebUI / TUI / mms config
change model source / URL / key / visibility / fallback / policy
save
MMS backs up, writes DB/secret backend, publishes and verifies generated bundle
Hive / Pilot / Ant / Mobius read the verified bundle
```

The user does not want to remember or manually coordinate `config.toml`, `credentials.sh`, `model-routes.json`, `model-routes.lineup.json`, `model-policy.json`, `provider-profiles.json`, generated files, DB tables, and guard snapshots.

## Current Pain Points

- MMS config currently exposes too many surfaces with overlapping meanings.
- URL/key may be edited in `config.toml`, but current code can prefer `credentials.sh`, causing display/runtime drift.
- `model-routes.json`, Lineup, Policy, Profile, generated bundle, and registry DB are easy to mistake as competing truth sources.
- Strict v2 consumers need a valid manifest hash set, but generated files can drift from the manifest.
- Agents must not auto-write real `~/.config/mms/**`, so human-facing UX needs a safer edit/apply path.
- Without durable docs, a future session may not know whether to continue with legacy config, DB truth, WebUI, or generated exports.

## Target Layers

```text
Human Entrance
  TUI / mms config / WebUI
  The only surface humans should need to inspect or edit.

Canonical Truth
  <config_root>/registry/model-registry.sqlite
  <config_root>/secrets/* or compatible secret backend
  DB stores route/policy/profile/capability/revision/audit and secret_ref.
  Secret backend stores plaintext keys or tokens.

Consumer Export
  <config_root>/generated/model-registry.latest-approved.json
  <config_root>/generated/model-routes.json
  <config_root>/generated/model-routes.lineup.json
  <config_root>/generated/provider-profiles.generated.json
  <config_root>/generated/model-policy.effective.json
  <config_root>/generated/model-capabilities.approved.json
```

## Root Strategy

Use an explicit preview root first:

```text
~/.config/mms       legacy stable root
~/.config/mms-next  future preview root
```

Rules:

- `mms` continues reading `~/.config/mms` by default.
- `mmf` sets `MMS_CONFIG_ROOT=~/.config/mms-next` and uses the same MMS code path.
- `MMS_CONFIG_ROOT` is the v2 root selector. Existing `MMS_CONFIG_DIR` remains only as legacy/test compatibility below it.
- `mms-next` is a directory name, not a permanent architecture contract.
- All paths must derive from `config_root`; business logic must not hardcode `mms-next`.
- New root failures must fail closed inside the selected root. They must not silently fall back to old `~/.config/mms` credentials or account state.
- CLI/WebUI/TUI must show the active root clearly: legacy vs future. CLI status is available through `mms config root [--json]` and `mmf config root [--json]`.

Recommended future root layout:

```text
<config_root>/
  registry/model-registry.sqlite
  secrets/
  generated/
  backups/db/
  backups/generated/
  backups/legacy-import/
  imports/
  logs/
  snapshots/
```

## Route / Policy / Lineup / Profile Mapping

### Route

Route should become DB truth.

DB owns provider id, route id, base URLs, protocols, models endpoint, priority, role, supported CLI hints, privacy boundary, validation state, and `secret_ref`.

Generated Router remains the downstream secret-bearing export.

### Policy

Policy should become DB truth.

DB owns model visibility, favorite, per-project allow/deny, downgrade target, fallback preference, privacy crossing rules, and human approval metadata.

Generated effective policy remains the downstream non-secret export.

### Profile

Profile should become DB truth, but it can be stored as revisioned JSON rules instead of over-normalized tables.

DB owns provider match rules, auth header rules, body patches, parameter aliases, model aliases, context rules, and reference metadata.

Built-in `config/provider-profiles.json` remains seed data; user overlays become import/export surfaces.

### Lineup

Lineup should not be human-edited truth.

Lineup is generated from model identity, capability facts, policy, profile, and display metadata. It remains a non-secret consumer export for context window, display/capability metadata, references, and pricing.

## Proposed DB Tables / Ownership

```text
model_identity
  canonical model id, aliases, family, local selectors

provider_route
  provider route, protocols, base URLs, models endpoint, secret_ref, privacy boundary

route_group
  model-to-route mapping, primary/fallback ordering, role/priority-derived claims

model_fact
  context, max output, modality, tools, thinking, pricing, references

provider_profile_rule
  headers, body patches, aliases, parameter mapping, protocol quirks

model_policy_rule
  show/hide/favorite/project allowlist/downgrade/fallback preference

secret_ref
  reference, provider id, fingerprint, last_validated_at, status; no plaintext key

registry_revision / revision_membership
  approved component revisions and bundle revision

health_overlay
  401/403/429/timeout/cache/latency observations; TTL-bound and reversible

audit_log
  actor, action, before/after metadata, backup pointer, revision pointer
```

## Watchdog And Stale Route Export Rule

Current behavior to fix: `scripts/mms_health_watchdog.py` reads root `model-routes.json`, `model-policy.json`, and `config.toml` directly. If a newly configured model such as `qwen3.7-max` is present in config but the last Router export predates the model, watchdog can report stale route state until someone manually runs `mms routes export`.

Target behavior:

- WebUI/TUI/`mms config` model changes trigger backup, publish, and verify automatically.
- Watchdog is a consumer, not a writer. It must not mutate DB truth or run surprise route export from launchd/background context.
- Watchdog should first read `<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json`, verify hashes, then consume generated Router/Policy/Profile/Lineup.
- If the bundle is missing, invalid, hash-mismatched, or older than the approved DB revision, watchdog should report `stale_or_invalid_bundle` with a clear remediation hint.
- Upstream `/models` newly exposing a model should enter candidate/source evidence first; it should not silently become approved route truth unless a later safe auto-promote policy explicitly allows it.
- User-approved WebUI model additions should make the model visible to watchdog on the next run without manual `mms routes export`.

This requirement belongs in the `mmf` preview work because it proves the new config root removes one more manual command from the user workflow.

## Downstream Contract

Hive, Pilot, Ant, Mobius, and future consumers should have one unified read path:

```text
<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json
```

Consumer rules:

- Read the manifest first.
- Verify each generated file hash.
- Do not mix files from different bundle revisions.
- Do not query SQLite tables directly.
- Record `bundle_revision`, `route_revision`, `policy_revision`, `profile_revision`, and `capability_revision` in run artifacts.
- Read Router for URL/key and primary/fallback routes.
- Read Lineup/Capabilities for context, display, pricing, and capability metadata.
- Read Policy for visibility, favorites, project allow/deny, and downgrade preferences.
- Read Profile for provider quirks.
- Emit `cache_transport_evidence.v1` for every real model call.

Fallback CLI/API surfaces can exist for tooling:

```text
mms registry resolve <model>
mms config export --format consumer-bundle
```

They are wrappers around the same bundle truth, not separate truth sources.

## Personalization And Real Data

Separate user personalization from runtime telemetry and approved route truth.

```text
Preferences
  thinking mode, reasoning effort, bypass preference, UI language, default tab,
  session pack, local UI defaults.

Policy
  model visibility, favorite, project allow/deny, downgrade, fallback preference.

Runtime State
  recent usage, speed, health, failures, cache evidence, rescue incidents.
```

Update rules:

- WebUI/TUI Save writes DB and secret backend.
- Save creates a DB backup first.
- Save can create candidate changes; only approved changes publish to latest-approved.
- Publish writes generated files and manifest atomically.
- Verify must pass before the new bundle is trusted.
- Health/runtime telemetry may auto-update overlay state but must not mutate approved route/policy/profile/capability truth.

## Secret Handling

Plaintext API keys and OAuth tokens must not be stored in DB.

DB stores:

```text
secret_ref
fingerprint
provider_id
last_validated_at
status
```

Secret backend options:

- compatibility import from `credentials.sh`
- `<config_root>/secrets/*` with restrictive permissions
- future system keychain integration, behind explicit human confirmation

Backups should default to secret metadata only. Plaintext secret export/import must require human confirmation and clear labeling.

## Backup / Restore

Minimum backup requirements:

```text
<config_root>/backups/db/<timestamp>/model-registry.sqlite
<config_root>/backups/generated/<timestamp>/*
<config_root>/backups/legacy-import/<timestamp>/{config.toml,credentials.sh,model-policy.json,provider-profiles.json}
```

Rules:

- Every WebUI Save backs up DB first via SQLite backup API.
- Every publish snapshots generated bundle files.
- Legacy import stores original files and an import report.
- DB missing: restore latest DB backup first.
- Generated missing: republish from DB.
- DB and generated missing: restore minimal route truth from latest approved bundle plus legacy import backup, then mark as recovery revision.

## HumanGate / Safety

Agents may inspect, diff, document, and create preview-root files. Agents must not auto-write real `~/.config/mms/**` unless the user explicitly confirms the protected config write flow.

Additional gates:

- Changing default `mms` root requires explicit user confirmation.
- Migrating plaintext secrets requires explicit user confirmation.
- Promoting `mms-next` to default requires backup, verify, smoke, and rollback instructions.
- Cross-boundary fallback requires explicit privacy policy.
- Any path that would read old-root auth as fallback from new-root runtime must be blocked.

## Proof Strategy

Phase proof commands should run under preview root unless explicitly testing legacy fallback:

```text
MMS_CONFIG_ROOT=~/.config/mms-next mmf registry verify
MMS_CONFIG_ROOT=~/.config/mms-next mmf routes check
MMS_CONFIG_ROOT=~/.config/mms-next mmf doctor
MMS_CONFIG_ROOT=~/.config/mms-next mmf test --provider <id> --cli codex
MMS_CONFIG_ROOT=~/.config/mms-next mmf test --provider <id> --cli claude
```

Current Stage 1 / Stage 2 preview commands that are safe to run without writing stable `~/.config/mms/**`:

```text
./mmf config root --json
./mmf config source --json
./mmf config save-plan --json
./mmf preview --help
./mmf preview doctor --strict-exit
./mmf preview init --json
./mmf preview prepare --from ~/.config/mms --json
./mmf preview prepare --from ~/.config/mms --include-secrets --json
./mmf config web --print-summary
./mmf config web --no-open
./mmf registry status
./mmf registry legacy-report --config-dir "$MMS_CONFIG_ROOT" --json
./mmf registry legacy-import --config-dir "$MMS_CONFIG_ROOT" --json
./mmf registry legacy-import --config-dir "$MMS_CONFIG_ROOT" --apply --json
./mmf registry legacy-import --config-dir "$MMS_CONFIG_ROOT" --source-config-dir ~/.config/mms --apply --json
./mmf registry v2-save-candidate --config-dir "$MMS_CONFIG_ROOT" --plan-json <webui-plan.json> --apply --json
./mmf preview import-legacy --from ~/.config/mms --apply --json
./mmf preview import-legacy --from ~/.config/mms --apply --include-secrets --json
./mmf preview publish --json
./mmf preview verify --json
./mmf preview status --json
./mmf preview doctor --json
./mmf registry publish-preview --config-dir "$MMS_CONFIG_ROOT" --json
./mmf registry verify --config-dir "$MMS_CONFIG_ROOT"
./mmf registry refresh-sources --path docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json
./mmf registry backup-db --config-dir "$MMS_CONFIG_ROOT" --reason manual-smoke
./mmf registry restore-db <backup.sqlite> --config-dir "$MMS_CONFIG_ROOT"
```

`config root` and `legacy-report` are read-only. `preview init` is the explicit write boundary for creating the preview root layout and empty registry DB under `<config_root>/registry/`; it refuses stable-root init unless `--allow-stable` is explicitly used on the lower-level `registry init-root` command. `legacy-import` is dry-run by default; `--apply` writes sanitized candidate/evidence rows into the preview DB and writes an import report under `<config_root>/imports/`, without plaintext secrets. `restore-db` is dry-run by default; `--apply` is explicit and creates a pre-restore backup before replacing the preview DB.
`config web --print-summary` includes the same Model Source status in the WebUI snapshot; starting the full WebUI still uses the existing audited config save path, so this slice only adds the read-only status panel and does not change save semantics.
TUI Settings -> `模型真源 / Registry Truth` now opens on the same read-only Model Source status before any explicit registry write action is selected.

Required checks:

- root resolution never writes old root during `mmf` flow
- importer reports conflicts between legacy `config.toml` and `credentials.sh`
- generated manifest hashes pass
- Router contains expected provider URL/key through secret resolution
- Lineup contains no URL/key
- Profile contains expected model alias/body/header rules
- Policy applies project allow/deny/favorite rules
- cache-sensitive CN/dual-protocol routes prefer `anthropic_messages` when available
- new-root failure does not silently fall back to old-root OAuth or credentials

## Roadmap

### Stage 0 - Documentation And Worktree Prep

- Land this durable plan.
- Add execution handoff and TODO entries.
- Wait for user to clean main.
- Create isolated worktree `.worktrees/config-root-v2-db-truth`.

### Stage 1 - Preview Root Foundation

- Add `MMS_CONFIG_ROOT` root resolver for preview use.
- Add thin `mmf` wrapper.
- Keep `mms` default root unchanged.
- Add root banner/status in CLI first; WebUI/TUI can adopt the same root status helper later.
- Add tests proving default `mms` still uses old root.
- Add tests proving explicit preview root does not read/fallback to stable `~/.config/mms` credentials or usage paths.

### Stage 2 - Backup And Import

- Add SQLite backup/restore helpers.
  - CLI preview commands:
    - `mmf registry backup-db --config-dir <preview-root> [--db <db-path>]`
    - `mmf registry restore-db <backup.sqlite> --config-dir <preview-root> [--db <db-path>]`
  - `restore-db` is dry-run by default; `--apply` first creates a pre-restore backup, then verifies SQLite integrity.
- Import legacy config, credentials metadata, model policy, provider profiles, and lineup facts into DB.
- Generate import report with conflicts and non-imported fields.
  - Read-only preview command:
    - `mmf registry legacy-report --config-dir <preview-root> [--json]`
  - The report names both sides of a conflict, for example `config.toml:api.base_url` vs `credentials.sh:MMS_API_BASE_URL`, and does not emit plaintext API keys.
- Keep imported secrets as `secret_ref`, not plaintext DB rows.

### Stage 3 - Read-Only Unified View

- WebUI/TUI reads DB and shows unified Model Source view.
- Save stays disabled or writes only a preview candidate.
- No launcher behavior change.

Current Stage 3a implementation:

- CLI: `mms config source [--json]` / `mmf config source [--json]`.
- CLI: `mms config save-plan [--json]` / `mmf config save-plan [--json]` shows the same read-only v2 DB-truth save sequence without writing DB, secrets, generated bundle, or legacy files.
- CLI: `mms config doctor [--json]` / `mmf config doctor [--json]` exposes the read-only preview readiness doctor under the `config` entry.
- WebUI: `/api/state` includes `model_source_status`; the first panel shows root, registry DB, legacy conflict, legacy candidate import counts, and latest-approved bundle status.
- WebUI: `/api/plan` includes a read-only `registry_v2_save_plan` that shows the future DB backup -> candidate revision -> secret backend -> publish -> verify -> rollback sequence. It is plan-only and does not enable DB writes yet.
- TUI: Settings -> `模型真源 / Registry Truth` first shows the same Model Source status, including legacy candidate route counts, and includes `查看 v2 Save Plan` plus read-only `运行 Preview Doctor`; explicit refresh/publish actions remain separate.
- Stable-root WebUI Save behavior is not changed; preview-root legacy save is blocked and users are directed to the DB-truth preview apply path.

Current preview init implementation:

- `mmf preview init [--json]` creates the v2 preview layout under the selected `MMS_CONFIG_ROOT`.
- Created directories: `registry/`, `secrets/`, `generated/`, `backups/db/`, `backups/generated/`, `backups/legacy-import/`, `imports/`, `logs/`, and `snapshots/`.
- It initializes `<config_root>/registry/model-registry.sqlite` unless `--no-db` is passed.
- It writes a non-secret `<config_root>/root-manifest.json`.
- Lower-level `mms registry init-root` refuses stable roots by default; stable init requires explicit `--allow-stable`.

Current legacy import candidate implementation:

- `mmf registry legacy-import --config-dir <preview-root> [--json]` is dry-run by default and reports what would be imported.
- `--source-config-dir <legacy-root>` can read legacy artifacts from a different root while writing only into the preview target selected by `--config-dir`; this supports read-only stable-root inspection plus preview DB import.
- `mmf preview import-legacy --from <legacy-root> [--apply] [--json]` is a thin wrapper around the same importer with target fixed to the active `mmf` preview root.
- `--include-secrets` is explicit and copies legacy API keys into `<preview-root>/secrets/legacy-secrets.json` with `0600` mode; DB rows still store only `secret_ref`.
- `--apply` initializes the preview layout if needed, writes a sanitized import report to `<config_root>/imports/`, stores a `legacy_config_import` source snapshot, imports model identity/facts from legacy model lists and generated route keys, and creates candidate route/provider rows for configured `fallback_models` / `extra_models`.
- It does not store plaintext API keys in DB or import JSON; route candidates use `secret_ref` such as `legacy-config:*` / `legacy-env:*` plus fingerprints in the report.
- After import, `mmf config source --json` and WebUI/TUI Model Source status show read-only candidate counts from DB: legacy import snapshots, legacy route revisions, route groups, and provider routes.
- Stable-root import is refused unless the lower-level command is explicitly passed `--allow-stable`.

Current preview publish implementation:

- `mmf preview publish [--json]` / `mmf registry publish-preview --config-dir <preview-root> [--json]` publishes `<config_root>/generated/model-registry.latest-approved.json` from the latest DB preview route candidate. It supports both legacy import candidates and v2 save candidates.
- `mmf preview verify [--json]` verifies manifest hashes for the active preview root; `mmf preview status [--json]` is a wrapper for Model Source status.
- `mmf preview doctor [--json]` and `mmf config doctor [--json]` are read-only "what next?" commands for preview setup. They check preview root mode, registry DB, legacy import candidates, latest-approved bundle verification, runtime readiness, missing API keys, missing route base URLs, and then print one next action.
- `mmf preview doctor --strict-exit` exits non-zero unless the preview root is runtime-ready. This avoids treating "printed something and did not crash" as success.
- `mmf preview prepare --from <legacy-root> [--include-secrets] [--json]` is the single explicit preview write command for user testing. It runs preview init, legacy import, publish, verify, and doctor against the active preview root; the source root remains read-only.
- Re-running `mmf preview prepare` backs up the existing preview DB under `<config_root>/backups/db/` before importing new candidate evidence.
- It writes generated Router/Lineup/Profile/Policy/Capabilities files, then writes and verifies a manifest-compatible latest-approved bundle.
- It approves the imported route revision and generated component/bundle revisions inside the preview DB.
- Without `--include-secrets`, it is not runtime-ready because plaintext secrets are not stored in DB; generated Router entries carry `secret_ref` and `api_key=""`, with `runtime_ready=false`.
- With the preview secret backend present, publish resolves `secret_ref` into generated Router `api_key` values and reports `runtime_ready=true`.
- `mmf config source`, WebUI, and TUI surface this distinction as bundle `verified` versus bundle `runtime_ready`.
- Missing legacy import candidates fail closed and do not create a generated manifest.

Current watchdog consumer implementation:

- `scripts/mms_health_watchdog.py` respects `MMS_CONFIG_ROOT` and `MMS_CONFIG_DIR` when selecting its config root.
- It prefers a verified `<config_root>/generated/model-registry.latest-approved.json` bundle over root legacy `model-routes.json` / `model-policy.json`.
- When using a verified bundle, it reads generated Profile metadata such as `models_endpoint` for provider checks instead of requiring root `config.toml` provider metadata.
- If a manifest exists but is invalid or hash-mismatched, watchdog reports `stale_or_invalid_bundle` and does not silently fall back to legacy route files.
- If the manifest is missing, explicit selected roots (`MMS_CONFIG_ROOT` / `MMS_CONFIG_DIR`) require the latest-approved bundle and fail closed by default; no-explicit-root stable watchdog behavior remains legacy-compatible.
- `--require-bundle` still forces fail-closed behavior, and `MMS_WATCHDOG_REQUIRE_BUNDLE=0` remains an explicit diagnostic override for an explicit root.
- Watchdog remains read-only with respect to DB and does not run route export or publish.

Current bridge rescue consumer implementation:

- Launcher-injected `MMS_RESCUE_CONFIG_ROOT` now defaults to the selected MMS config root, so `mmf` preview sessions do not silently route bridge rescue through stable `~/.config/mms`.
- Launcher HOME context reports the same selected config root; explicit `MMS_CONFIG_ROOT` / `MMS_CONFIG_DIR` roots are treated as intentional instead of being rewritten to stable `~/.config/mms` in the context banner/guard.
- Read-only `model-context-overrides.json` lookup follows the selected config root and keeps the cache keyed by path, so preview roots do not inherit stable root context overrides.
- Provider profile lookup treats an existing latest-approved manifest as the bundle boundary: valid bundles use generated Profile, invalid/hash-mismatched bundles fall back only to built-in profiles instead of mixing root legacy profile overlays. The profile cache is keyed by selected config root to avoid stable/preview bleed.
- `review-launch` uses verified latest-approved Router routes when an explicit config root is selected (`mmf` / `MMS_CONFIG_ROOT` / `MMS_CONFIG_DIR`); invalid manifests fail closed instead of falling through to legacy provider config. Without an explicit root, legacy `mms` review-launch behavior remains unchanged.
- Project/session store helpers derive their default root from the selected MMS config root, so `mmf` preview sessions keep project state under `<MMS_CONFIG_ROOT>/projects` instead of stable `~/.config/mms/projects`.
- Launcher runtime/cache/usage auxiliary paths derive from the selected config root, preventing preview sessions from reading or writing stable-root `runtime/`, `health_check.json`, `cache/anthropic_base_urls.json`, or `usage.json` by default.
- Local runtime telemetry helpers now follow the selected config root for local `usage.json`, `speed-stats.json`, `health-cache.json`, and `events/`, so preview sessions do not bleed runtime state into stable root by default.
- Broker profile env resolution reads `credentials.sh` only from the selected config root, and local broker logs use `<config_root>/cache/broker`, so preview broker flows do not silently consume stable credentials/cache.
- `statusline-command.sh` reads route status and health cache from the selected config root, so `mmf` gateway sessions display preview route/health state instead of stable-root state.
- Launcher route status path uses `<config_root>/route_status.json` when an explicit config root is selected; default stable launches keep the previous session-home route status path.
- Rescue hot fallback now checks `<config_root>/generated/model-registry.latest-approved.json` before reading generated/root `model-routes.json`.
- If the manifest exists, rescue fallback only uses the verified Router payload; invalid or hash-mismatched manifests fail closed for that fallback lookup instead of silently using unverified generated routes.
- If the manifest is missing, default behavior remains legacy-compatible and reads generated/root route files in the previous order.
- TUI Rescue routed fallback candidate lists use the same boundary: when a latest-approved manifest exists, candidates are read only from the verified Router payload; invalid manifests return no routed candidates instead of falling back to stale legacy files.
- If selected-root resolution fails during bridge rescue fallback lookup, the bridge returns no config-root fallback instead of silently reading stable `~/.config/mms/config.toml`; explicit server/env fallback fields may still be used.

### Stage 4 - Write Path And Publish

- WebUI Save writes DB + secret backend.
- Save triggers backup, publish-approved, verify.
- Generated bundle becomes the only downstream preview output.

Current Stage 4a implementation:

- `mms registry v2-save-candidate` / `mmf registry v2-save-candidate` accepts a WebUI plan JSON (`config`, `model_policy`, `credential_updates`) or direct config/policy JSON and is dry-run unless `--apply`.
- `--apply` is preview-root guarded by default; stable roots require explicit `--allow-stable`.
- The command initializes the selected preview root if needed, backs up an existing preview DB before writing, then writes candidate `route`, `policy`, and `profile` revisions into SQLite.
- Route candidates store `secret_ref` / fingerprint only. Plaintext keys are not stored in DB; legacy compatibility files are not written in this slice.
- If candidate write fails after backup, the preview DB is restored from the pre-write backup.
- `publish-preview` now prefers the latest preview route candidate, including `registry-v2-save-candidate`, and reuses matching DB candidate policy/profile revisions when generating the latest-approved bundle.
- WebUI has a preview-only `写入预览 DB + 发布` action backed by `/api/registry-v2/apply`. It requires the confirmation phrase `写入预览DB`, refuses stable roots, writes DB candidates, writes `<preview-root>/secrets/webui-secrets.json` only when explicit plaintext credential updates are submitted, publishes `generated/model-registry.latest-approved.json`, and verifies hashes.
- WebUI plaintext credential updates are stored only in the preview secret backend; DB candidate rows keep `secret_ref` / fingerprint, the API response is sanitized, and generated Router entries become `runtime_ready=true` only when matching preview secret values exist and every route leaf has an `anthropic_base_url` or `openai_base_url`.
- If WebUI preview publish/verify fails, the action attempts to roll back the preview DB candidate, WebUI secret backend file, and generated bundle files from the pre-publish snapshot.
- This WebUI preview action does not call legacy `/api/save` and does not write `config.toml` / `credentials.sh` / `model-policy.json`.
- WebUI `/api/state` exposes the save contract as two separate write surfaces: `stable_legacy_writes` for legacy `config.toml` / `credentials.sh` / `model-policy.json`, and `preview_v2_writes` for DB candidate revisions, preview secret backend, and generated latest-approved bundle files.
- WebUI legacy `/api/save` is blocked while running against a preview root, so `mmf` users do not accidentally create legacy config files in `~/.config/mms-next`.
- Stable-root WebUI `/api/save` is still not redirected to this path yet; that remains a later Stage 4 slice after more interactive/browser validation.

Current TUI/settings boundary:

- TUI Settings labels direct `model-routes.json` export as `Legacy 路由导出` / `Legacy Route Export` and points v2 publishing users to Registry Truth.
- The compatibility export action remains available, but it is not presented as the v2 truth/publish path.

### Stage 5 - Router Export From DB

- Generate Router/Lineup/Profile/Policy from DB truth.
- Keep legacy export fallback behind explicit compatibility mode.
- Add contract tests for no mixed revisions.

### Stage 6 - Launcher Adoption

- Preview `mmf` launcher reads verified latest-approved bundle.
- Legacy `mms` remains unchanged.
- Only after repeated smoke passes, propose promotion.

### Stage 7 - Downstream Cutover

- Hive/Pilot/Ant/Mobius read `MMS_CONFIG_ROOT` and latest-approved manifest.
- Remove project-specific fixed `~/.config/mms` assumptions.
- Keep strict evidence requirements.

### Stage 8 - Promotion / Public Version

- Add `mms migrate config-v2` / `mmf promote` flow.
- Publish preview docs.
- Later deprecate `mmf` into an alias once v2 becomes default.

## Future LMs Must Not Forget

- Human-facing config must be TUI / `mms config` / WebUI only.
- DB is internal truth; generated bundle is external API.
- Downstream projects must not read SQLite tables.
- `credentials.sh` currently can override `config.toml`; importer must surface this conflict.
- Plaintext keys do not belong in DB.
- `mmf` must be a thin wrapper over the same MMS code, not a fork.
- New-root failures must not silently read old-root credentials or OAuth state.
- `lineup` is generated metadata, not human truth.
- `route`, `policy`, and `profile` should be DB truth.
- Snapshot Guard should protect human/root/secret changes, not generated churn.
