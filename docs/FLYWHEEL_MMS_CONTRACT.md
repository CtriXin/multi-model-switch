# Flywheel / Looper MMS Contract

MMS Next is the model/source-of-truth for Flywheel and Looper model selection.
Flywheel keeps GitHub issue/PR/gate flow ownership; MMS owns model, provider,
fallback, and runtime-control resolution.

Phase 1 adds a read-only resolver:

```bash
mmf flywheel resolve --lane worker --priority AI-P3 --json
mmf flywheel resolve --lane committee --priority AI-P0 --json
```

The resolver does not launch a model, write user config, or read Runtimia Agent
state. It reads the active MMS config root plus model route exports and emits a
sanitized plan that is safe to paste into tracker comments: provider/model ids and
runtime controls are included; API keys and endpoint/proxy URLs are omitted.

## Config Shape

Flywheel config may live under `[flywheel.*]` in `config.toml`, or in a dedicated
`flywheel.toml` using the same tables without the outer `flywheel` prefix.

```toml
[flywheel.lanes.worker]
"AI-P0" = "flywheel.worker.p0"
"AI-P1" = "flywheel.worker.p1"
"AI-P2" = "flywheel.worker.p2"
"AI-P3" = "flywheel.worker.p3"
"AI-P4" = "flywheel.worker.p4"

[flywheel.lanes.fixer]
default = "flywheel.fixer.default"

[flywheel.lanes.committee]
"AI-P0" = "opencode-committee-heavy"
"AI-P1" = "opencode-committee-standard"
"AI-P2" = "opencode-committee-light"
"AI-P3" = "opencode-committee-fast"
"AI-P4" = "opencode-committee-fast"

[flywheel.profiles."flywheel.worker.p3"]
runtime = "opencode"
model = "qwen3.7-max"
provider = "direct-qwen"
reasoning_effort = "high"
thinking_mode = "disable"
max_context_tokens = 1000000
```

Supported profile fields:

- `runtime` / `runtime_kind` / `cli`: `codex`, `opencode`, `opencode_profile`, or future runner ids.
- `model` / `model_id`: MMS model route key or OpenCode profile id.
- `provider` / `provider_id` / `route_provider` / `model_route_provider` / `channel`: optional provider override.
- `thinking_mode`: `auto`, `enable`, or `disable`.
- `reasoning_effort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`.
- `max_context_tokens` / `context_length`: positive integer override.

## Built-In Defaults

If no Flywheel config exists, the resolver preserves current Flywheel behavior:

- `worker`: `flywheel.worker.default` -> `codex`, `gpt-5.5`, `reasoning_effort=medium`.
- `fixer`: `flywheel.fixer.default` -> `codex`, `gpt-5.5`, `reasoning_effort=medium`.
- `committee`: `AI-P0 -> heavy`, `AI-P1 -> standard`, `AI-P2 -> light`, `AI-P3/P4 -> fast`.

## Next Phase

The next contract slice should add a headless runner that consumes this resolver
output and launches the selected CLI/profile while preserving Looper's completion
marker contract.
