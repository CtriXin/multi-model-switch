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
./mmf preview init --json
./mmf config web --print-summary
./mmf config web --no-open
./mmf registry status
./mmf registry legacy-report --config-dir "$MMS_CONFIG_ROOT" --json
./mmf registry refresh-sources --path docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json
./mmf registry backup-db --config-dir "$MMS_CONFIG_ROOT" --reason manual-smoke
./mmf registry restore-db <backup.sqlite> --config-dir "$MMS_CONFIG_ROOT"
```

`config root` and `legacy-report` are read-only. `preview init` is the explicit write boundary for creating the preview root layout and empty registry DB under `<config_root>/registry/`; it refuses stable-root init unless `--allow-stable` is explicitly used on the lower-level `registry init-root` command. `restore-db` is dry-run by default; `--apply` is explicit and creates a pre-restore backup before replacing the preview DB.
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
- WebUI: `/api/state` includes `model_source_status`; the first panel shows root, registry DB, legacy conflict, and latest-approved bundle status.
- TUI: Settings -> `模型真源 / Registry Truth` first shows the same Model Source status; explicit refresh/publish/doctor actions remain separate.
- Existing WebUI Save behavior is not changed in this slice; disabling or redirecting save to preview candidates belongs to Stage 4.

Current preview init implementation:

- `mmf preview init [--json]` creates the v2 preview layout under the selected `MMS_CONFIG_ROOT`.
- Created directories: `registry/`, `secrets/`, `generated/`, `backups/db/`, `backups/generated/`, `backups/legacy-import/`, `imports/`, `logs/`, and `snapshots/`.
- It initializes `<config_root>/registry/model-registry.sqlite` unless `--no-db` is passed.
- It writes a non-secret `<config_root>/root-manifest.json`.
- Lower-level `mms registry init-root` refuses stable roots by default; stable init requires explicit `--allow-stable`.

### Stage 4 - Write Path And Publish

- WebUI Save writes DB + secret backend.
- Save triggers backup, publish-approved, verify.
- Generated bundle becomes the only downstream preview output.

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
