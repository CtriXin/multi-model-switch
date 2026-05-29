# MMS Session Asset Manager

Status: first WebUI inventory slice.

## User Problem

Users can see model/provider config in WebUI, but skills, MCP servers, hooks,
and optional agent packs are harder to reason about:

- which item is global and affects plain Claude/Codex/OpenCode;
- which item is injected only by MMS for the current session;
- which CLI receives it;
- which file path owns it;
- whether it is passive, enabled by default, or gated by a pack toggle.

## UX Model

The WebUI should explain assets in three layers:

1. **Global / inherited**: user-owned CLI config or plugins. MMS may inherit or
   preview these, but WebUI should not silently edit them.
2. **MMS dynamic**: session-local skills, MCP servers, plugins, and hooks that
   MMS injects at launch. These are safe to visualize and disable per session.
3. **Optional packs**: Caveman, NSR, ECC, OMC. The pack switch is the user-level
   control; MCP/skills/hooks are the expanded surfaces underneath it.

## First WebUI Slice

The first slice adds a read-only **Session Skills / MCP / Hooks** panel:

- tab by `MMS dynamic`, `Global / inherited`, and `Other detected`;
- filter by CLI: `Claude`, `Codex`, `OpenCode`, `Antigravity`;
- filter by surface kind: `Skills`, `MCP`, `Hooks`;
- show name, description, origin, path/trigger, and `disable_key`;
- show common global roots and whether they exist;
- show the current `preferences.toml` snippet for launch defaults and disabled
  session surfaces.

This slice does not write `~/.config/mms/preferences.toml`. It keeps the
existing human-gate rule: WebUI can display and explain the target snippet, then
a later audited preferences writer can be added.

## TUI Relationship

The TUI confirmation screen already has the per-launch runtime control:

- `Tab` toggles bypass;
- `C` toggles Caveman;
- `N` toggles NSR when available;
- `X` cycles Claude agent pack (`none` / `ecc` / `omc`);
- the MCP / Skills / Hooks panels allow selecting a displayed item and disabling
  it for this launch.

The WebUI should be the discovery and configuration overview. The TUI remains
the final per-launch override surface.

## Persistence Contract

Current read/write boundaries:

- `preferences.toml` is the right persistent home for `bypass`,
  `caveman_mode`, `nsr_mode`, `agent_pack`, and disabled session surfaces.
- `config.toml` / registry DB remain model/provider/routing truth, not the place
  for per-session asset toggles.
- Global Claude/Codex/OpenCode config should stay read-only unless the human
  explicitly enters a global installer/config flow.

Future save support should therefore be an audited preferences writer, not a
side effect of the model/provider save flow.
