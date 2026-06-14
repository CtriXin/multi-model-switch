# opencode-local

`opencode-local` is the MMS-owned home for OpenCode-adjacent capability work.

It is intentionally not an OpenCode fork, not a patched OpenCode distribution, and not a new workflow engine. The goal is to keep reusable runner-side capabilities in a host-neutral shape, then bind them into OpenCode through official extension surfaces when available.

## Position

- OpenCode remains the host runner.
- MMS remains the launcher/session/runtime manager.
- MMF remains the MMS preview lane that can attach this capability pack first.
- `state-core` remains the canonical task-state and done-gate owner.
- `mommy` remains the explicit intake/routing director when used.

## Directory Shape

| Path | Purpose |
| --- | --- |
| `contracts/` | Stable runner-neutral contracts and schemas. These should survive OpenCode internal changes. |
| `capabilities/` | Reusable policies such as context projection, closeout bridge, continuity bridge, and subagent dispatch discipline. |
| `adapters/opencode/` | OpenCode binding notes and future adapter code that uses official OpenCode plugin/tool/skill/agent surfaces. |
| `profiles/` | MMF/MMS profile binding documents. Profiles decide how a capability pack is attached, not what task truth means. |
| `spikes/` | Proof-first validation work such as hook-fit spikes, evidence templates, and bounded experiments before adapter MVP work. |
| `examples/` | Non-secret examples for generated profile/pack manifests. |

## Design Rules

1. Do not patch OpenCode core unless a separate upstream RFC proves the official surface is insufficient.
2. Do not store API keys, OAuth state, account identity, or real-home auth material here.
3. Do not let adapters write canonical task-state directly.
4. Do not put MMF-specific names into the neutral contract layer.
5. Keep MMF binding session-local: generated plugins, tools, skills, and agent config should be attached per launch.
6. Treat OpenCode events/hooks as version-sensitive adapter details, not neutral contract facts.

## Recommended First Form

The first shippable form should be:

```text
MMF profile
  -> session-local capability pack manifest
  -> OpenCode adapter materializes official plugin/tool/skill/agent files
  -> runner-neutral contract tools call state-core/mommy bridges
  -> closeout/compaction writes evidence, not workflow truth
```

This keeps the value portable. If OpenCode changes its internal scheduler or storage, only `adapters/opencode/` should need updates.
