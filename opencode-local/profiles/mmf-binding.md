# MMF Binding

MMF should be the first MMS lane that attaches `opencode-local` capabilities.

The binding should extend the current OpenCode `profile + subagent` model instead of replacing it. The new shape is `profile + capability pack + role slots + generated subagents`.

## Why This Shape

Current MMF OpenCode usage is mostly profile plus subagent roster. That is a good launch UX, but it couples behavior to generated agent names too early.

The next shape should separate four concepts:

| Concept | Owner | Example |
| --- | --- | --- |
| profile | MMS/MMF | `agent`, future `agent+capabilities` internal profile |
| capability pack | `opencode-local` | context projection, closeout bridge, continuity bridge |
| role slot | MMS/MMF profile binding | `coordinator`, `executor`, `explorer`, `reviewer`, `vision`, `fixer` |
| generated agent id | OpenCode adapter | any valid OpenCode agent key for the current session |

This lets the visible MMF surface stay simple while the adapter can regenerate OpenCode-specific files as OpenCode evolves.

## Proposed Launch Flow

```text
mmf opencode --profile agent
  -> resolve MMF preview root and model routes
  -> choose role slots from profile policy
  -> attach opencode-local capability pack manifest
  -> generate session-local OpenCode plugins/tools/skills/agents
  -> launch OpenCode with generated config
```

## Binding Contract

MMF may provide:

- selected profile id
- selected model/route bundle revision
- role slot policy
- safe session-local paths
- host context pointer
- capability pack version

MMF must not provide:

- real-home auth files
- API keys in generated static config
- direct task-state write paths
- OpenCode core patch instructions
- mommy/state-core private internals in public adapter config

## Recommended Profile Form

Use an internal profile flag first, not a new public mode:

```toml
[opencode]
default_profile = "agent"

[opencode.capability_pack]
enabled = true
id = "opencode-local/mmf-agent-v0"
version = "0.1"
attach = "session-local"

[opencode.role_slots.executor]
preset = "executor"
edit = "ask"

[opencode.role_slots.explorer]
preset = "explore"
edit = "deny"
```

The TOML above is an example shape only. It must not be written to real `~/.config/mms/**` without the MMS human gate.

## Migration From Current Roster

- Keep existing `agent` profile as the user-facing entry.
- Treat current `mobius-*` names as generated defaults, not stable API.
- Add role slots beside existing roster parsing first.
- Generate the old roster from role slots until the adapter is ready.
- Move capability attachment behind MMF preview behavior before exposing it in stable `mms`.
