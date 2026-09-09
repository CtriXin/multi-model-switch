# Flywheel / Looper MMS Contract

MMS Next is the model/source-of-truth for Flywheel and Looper model selection.
Flywheel keeps GitHub issue/PR/gate flow ownership; MMS owns model, provider,
fallback, and runtime-control resolution.

Phase 1 added a read-only resolver:

```bash
mmf flywheel resolve --lane worker --priority AI-P3 --json
mmf flywheel resolve --lane committee --priority AI-P0 --json
```

The resolver does not launch a model, write user config, or read Runtimia Agent
state. It reads the active MMS config root plus model route exports and emits a
sanitized plan that is safe to paste into tracker comments: provider/model ids and
runtime controls are included; API keys and endpoint/proxy URLs are omitted.

Phase 2 adds a headless worker/fixer runner:

```bash
mmf flywheel run --lane worker --priority AI-P3 --cwd <worktree> --artifact-dir <run-dir> exec <prompt>
```

`run` resolves the same profile, writes `<run-dir>/resolved-route.json` and
`<run-dir>/run-result.json`, then launches the selected MMS runtime headlessly.
OpenAI/GPT-family models use Codex CLI; non-GPT Anthropic-compatible worker/fixer
routes use Claude CLI through MMS' Claude bridge. The command accepts Looper's Codex-shaped tail
(`exec [--model <ignored>] <prompt>`). MMS owns the actual model/provider
choice; Looper's `--model` is ignored.

By default `run` prints only raw agent text to stdout. This preserves Looper's
completion marker contract: if the agent prints
`__LOOPER_RESULT__={...json...}`, the marker lands at line start for Looper to
parse. Use `--json` only for diagnostics, not as the Looper command output.

`resolved-route.json` is safe for issue/PR evidence: it contains sanitized
model/provider/runtime metadata and `cache_transport_evidence.v1`, but not API
keys, endpoint URLs, or proxy fields. The transport evidence records the
concrete upstream `request_path` (for example `/v1/messages`) while leaving
`request_url` blank because MMS provider hosts can be private. The raw key and
endpoint are used only in-process to launch the selected runtime.
If the preferred generated route export is sanitized, `run` may read the
matching legacy secret-bearing route inside the same config root for launch-only
credentials while keeping artifacts redacted.

The runner also exposes the same evidence in the JSON result and
`run-result.json`:

```json
{
  "cache_transport_evidence": {
    "schema": "cache_transport_evidence.v1",
    "model": "qwen3.7-max",
    "provider_id": "newapi-personal-tokyo",
    "protocol": "anthropic_messages",
    "request_url": "",
    "request_path": "/v1/messages",
    "fallback_used": false,
    "fallback_reason": ""
  }
}
```

For non-OpenAI-family CN / dual-protocol / cache-sensitive routes, `run`
defaults to `anthropic_messages` when `anthropic_base_url` exists. OpenAI-family
models default to `openai_responses`. `openai_chat_completions` for
cache-sensitive non-OpenAI routes is only valid as an audited fallback with a
non-empty `fallback_reason`.

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
runtime = "claude"
model = "qwen3.7-max"
provider = "direct-qwen"
reasoning_effort = "high"
thinking_mode = "disable"
max_context_tokens = 1000000
```

Supported resolver profile fields:

- `runtime` / `runtime_kind` / `cli`: `codex`, `claude`, `opencode`, `opencode_profile`, or future runner ids. `mmf flywheel run` executes `codex` for GPT/OpenAI-family worker/fixer routes and `claude` for non-GPT worker/fixer routes; committee profiles remain resolver-only here.
- `model` / `model_id` / `model_name`: MMS model route key or OpenCode profile id.
- `provider` / `provider_id` / `route_provider` / `model_route_provider` / `channel`: optional provider override.
- `thinking_mode`: `auto`, `enable`, or `disable`.
- `reasoning_effort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`.
- `max_context_tokens` / `context_length`: positive integer override.

## Built-In Defaults

If no Flywheel config exists, the resolver preserves current Flywheel behavior:

- `worker`: `flywheel.worker.default` -> `codex`, `gpt-5.5`, `reasoning_effort=medium`.
- `fixer`: `flywheel.fixer.default` -> `codex`, `gpt-5.5`, `reasoning_effort=medium`.
- `worker/fixer AI-P2`: `claude`, `glm-5.2`, `reasoning_effort=medium`.
- `worker/fixer AI-P3`: `claude`, `qwen3.7-max`, `reasoning_effort=medium`.
- `worker/fixer AI-P4`: `claude`, `MiniMax-M3`, `reasoning_effort=medium`.
- `committee`: `AI-P0 -> heavy`, `AI-P1 -> standard`, `AI-P2 -> light`, `AI-P3/P4 -> fast`.

## Remaining Follow-Up

Flywheel should switch its worker hook from the older Runtimia Codex wrapper to
`mmf flywheel run` after this MMS runner lands. Committee profile execution can
remain on the existing OpenCode committee path until it needs the same runner
interface.
