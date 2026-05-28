# Downstream Consumer Bundle Cutover Runbook

Status: preview contract for MMS config-root v2.

This runbook is for Hive, Pilot, Ant, Mobius/Moebius, watchdog-like tools, and
future consumers that need MMS model routing data. It is deliberately small:
consumers get one source, verify it, and fail closed if it is stale or invalid.

## One Source To Read

Resolve the active MMS config root from the selected runtime environment:

```text
MMS_CONFIG_ROOT -> <root>
```

Then read only this manifest first:

```text
<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json
```

Do not read these as primary truth:

```text
<MMS_CONFIG_ROOT>/model-routes.json
<MMS_CONFIG_ROOT>/model-policy.json
<MMS_CONFIG_ROOT>/model-routes.lineup.json
<MMS_CONFIG_ROOT>/provider-profiles.json
<MMS_CONFIG_ROOT>/registry/model-registry.sqlite
```

Legacy root files can exist as compatibility aliases, backups, or import/export
artifacts. SQLite is MMS internal truth, not a downstream API.

## Verify Before Use

Consumer algorithm:

1. Load `<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json`.
2. Check `schema == "mms.model_registry.latest_approved.v1"`.
3. For each `files.*.canonical_path`, compute sha256 and compare with the
   manifest `sha256`.
4. Load only the generated files referenced by the verified manifest.
5. Keep one bundle revision set together; do not mix route/policy/profile/lineup
   from different manifests.
6. Record `bundle_revision`, `route_revision`, `policy_revision`,
   `profile_revision`, and `capability_revision` in the consumer run artifact.
7. Emit `cache_transport_evidence.v1` for real model calls, including actual
   request URL/path when available.

Fail closed when the manifest is missing, unreadable, has a wrong schema, points
to missing files, or any hash mismatches. Do not silently fallback to stable
`~/.config/mms` credentials, global OAuth state, or root legacy files.

## File Responsibilities

| Manifest key | Typical file | Use |
|---|---|---|
| `router` | `generated/model-routes.json` | secret-bearing provider routes, primary/fallback order, URLs, API keys |
| `lineup` | `generated/model-routes.lineup.json` | context/display/capability metadata |
| `profile` | `generated/provider-profiles.generated.json` | protocol quirks, auth header rules, body/model aliases |
| `policy` | `generated/model-policy.effective.json` | visibility, favorites, project allow/deny, downgrade/fallback policy |
| `capabilities` | `generated/model-capabilities.approved.json` | approved capability facts when present |

`router` is local secret-bearing data. Do not copy it into public artifacts,
logs, GitHub issues, or model-to-model prompts.

## Human / Script Checks

Use these read-only checks before or during a cutover:

```bash
mmf preview check --json
mmf config bundle --json
mms config bundle --json
```

`config bundle` is strict by default: missing or invalid latest-approved manifest
returns non-zero. Use `--no-strict-exit` only for diagnostics that must print a
report without passing readiness.

## Minimal Python Verifier

```python
import hashlib
import json
from pathlib import Path


def load_verified_bundle(config_root: str):
    root = Path(config_root).expanduser()
    manifest_path = root / "generated" / "model-registry.latest-approved.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "mms.model_registry.latest_approved.v1":
        raise RuntimeError("invalid MMS latest-approved schema")
    payloads = {}
    for name, entry in (manifest.get("files") or {}).items():
        path = root / str(entry.get("canonical_path") or "")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            raise RuntimeError(f"MMS bundle hash mismatch: {name}")
        payloads[name] = json.loads(path.read_text(encoding="utf-8"))
    return {"manifest": manifest, "payloads": payloads}
```

Consumers may import MMS helper code when available, but the contract above is
the portable fallback. The helper and the portable verifier must enforce the
same fail-closed hash boundary.

MMS ships a small helper for consumers that can import this repo:

```python
from mms_consumer_bundle import load_verified_consumer_bundle

bundle = load_verified_consumer_bundle(
    config_root="/path/to/selected/mms-root",
    include_secret=False,
)
```

When `config_root` is omitted, the helper requires `MMS_CONFIG_ROOT` or
`MMS_CONFIG_DIR` by default. Falling back to stable `~/.config/mms` is opt-in,
so preview consumers do not silently cross into stable credentials or legacy
root files when their environment is incomplete.

## Cutover Checklist

For each downstream project:

- Replace fixed `~/.config/mms` paths with `MMS_CONFIG_ROOT` plus explicit test
  fixtures.
- Replace direct reads of root `model-routes.json`, `model-policy.json`,
  `provider-profiles.json`, and `model-routes.lineup.json` with the verified
  latest-approved manifest.
- Remove any direct SQLite reads; request a new MMS CLI/export field if the
  bundle lacks required data.
- Redact router secrets in logs and artifacts.
- Add tests for missing manifest, hash mismatch, wrong schema, and no fallback
  to global OAuth/legacy root credentials.
- Record bundle/component revisions and cache transport evidence in run output.

## Promotion Rule

Do not promote a downstream consumer until its tests prove all of these:

```text
missing manifest -> fail closed
hash mismatch -> fail closed
wrong schema -> fail closed
MMS_CONFIG_ROOT respected
legacy root files ignored as primary truth
SQLite not queried
secrets redacted from logs/artifacts
bundle revisions recorded
```
