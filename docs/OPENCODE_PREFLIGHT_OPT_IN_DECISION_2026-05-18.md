# OpenCode Lite Pro Preflight Opt-In Decision

- Date: 2026-05-18
- Repo: `multi-model-switch`
- Branch: `main`
- Fix commit: `0a323f9 fix(opencode): make launch preflight opt-in`
- First included tag: `v2.10.3`
- Related runtime docs: `docs/OPENCODE_LITE_LAUNCHER.md`
- Local recorder: `/Users/xin/issue-tracking/issues/multi-model-switch/opencode-preflight-opt-in-20260518/issue.md`

## User Symptom

OpenCode Lite Pro / 5.5 Multi-Agent launch paused for a long time at:

```text
OpenCode Lite Pro preflight: 检查 primary builder route...
```

The launch banner showed `gpt-5.5`, `OpenCode Lite Pro`, `api_key`, and direct network/DNS settings. The pause happened before the interactive OpenCode session opened.

## Root Cause

This was not a local config parse or TUI delay. MMS was doing a live model request during launch.

Before the fix, `_apply_opencode_profile(..., "lite_pro")` set:

```python
runtime["opencode_launch_preflight"] = True
```

That made `_opencode_select_launch_candidate(...)` call `_opencode_run_preflight(...)`, which spawned a real OpenCode one-shot request:

```bash
opencode run --pure --dangerously-skip-permissions \
  --agent mobius-builder-pro \
  -m mms-builder_primary/gpt-5.5 \
  "MMS OpenCode launch preflight. Reply exactly OK and nothing else."
```

The default timeout was `35s`. If the primary builder route failed or timed out, MMS could then try the fallback route, so the perceived launch wait could approach two route checks.

## Decision

Default launch should not spend latency, tokens, network budget, or privacy budget just to open an OpenCode session.

The live preflight remains useful for smoke tests and failover-before-open diagnostics, but it should be an opt-in path, not the normal startup path.

## Fix

Changed the Lite Pro / Lite Pro Orchestrated runtime default to skip live preflight:

```python
runtime["opencode_launch_preflight"] = False
```

The existing env override path was preserved. Users can still request the old live check explicitly:

```bash
MMS_OPENCODE_LAUNCH_PREFLIGHT=1 mms opencode
```

When enabled, the same deterministic failover behavior remains:

1. preflight `builder_primary` / `mobius-builder-pro` / `gpt-5.5`
2. if it fails, preflight `builder_fallback` / `mobius-builder-stable` / `gpt-5.4`
3. launch the first route that returns `OK`

When disabled, launch selects `builder_primary` directly and opens OpenCode immediately. If the route is actually unhealthy, the error appears inside the OpenCode session or during explicit smoke/doctor verification instead of blocking startup.

## Files Changed

- `mms_core.py`: changed the Lite Pro default from live preflight on to off.
- `tests/test_opencode_launcher.py`: updated default-shape assertions and added `MMS_OPENCODE_LAUNCH_PREFLIGHT=1` opt-in coverage.
- `docs/OPENCODE_LITE_LAUNCHER.md`: documented that live launch preflight is opt-in.
- `README.md`: clarified that `opencode run` preflight is optional.
- `README.zh-CN.md`: same clarification in Chinese.

## Verification

Commands run before commit:

```bash
python3.13 -m pytest -q tests/test_opencode_launcher.py -q
python3.13 -m pytest -q
npm run build --if-present
git diff --check
```

Results:

- `tests/test_opencode_launcher.py`: passed, 42 tests.
- Full pytest: `582 passed, 4 skipped`.
- Build: passed, Python launcher sources compiled.
- Diff check: passed.

## Operational Guidance

Use default launch for normal interactive work:

```bash
mms opencode
```

Use live preflight only when diagnosing route health or when you want MMS to fail over before opening OpenCode:

```bash
MMS_OPENCODE_LAUNCH_PREFLIGHT=1 mms opencode
```

If the opt-in preflight itself feels too slow but is still desired, reduce the timeout:

```bash
MMS_OPENCODE_LAUNCH_PREFLIGHT=1 MMS_OPENCODE_PREFLIGHT_TIMEOUT=8 mms opencode
```

## Residual Risk

With default preflight disabled, a broken primary route is discovered later, after OpenCode opens. This is intentional: normal launch avoids hidden real requests, while smoke/debug paths keep the failover-before-open behavior available.

