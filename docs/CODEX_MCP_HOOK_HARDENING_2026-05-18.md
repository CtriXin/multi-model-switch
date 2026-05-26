# Codex Inherited MCP / Hook Trust Hardening Report

- timestamp: 2026-05-18T04:20:00-04:00
- release source: `v2.10.2` / `535aeee fix(codex): harden inherited mcp startup`
- follow-up rollup: `v2.10.3` keeps this report traceable from latest `main`
- task / scope: record why MMS-isolated Codex showed `codegraph` MCP startup failure and repeated hook review prompts, and document the implemented fix.

## Symptom

MMS-launched Codex displayed startup warnings similar to:

- `MCP client for codegraph failed to start: MCP startup failed: No such file or directory (os error 2)`
- `MCP startup incomplete (failed: codegraph)`
- `1 hook needs review before it can run. Open /hooks to review it.`

The issue appeared inside MMS session isolation, while the same global setup could work from a normal shell.

## Root Cause

1. Real `~/.claude.json` can contain inherited MCP servers such as:

```json
{
  "mcpServers": {
    "codegraph": {
      "type": "stdio",
      "command": "codegraph",
      "args": ["serve", "--mcp"]
    }
  }
}
```

2. Before the fix, MMS translated that into Codex session config as a bare command:

```toml
[mcp_servers.codegraph]
command = "codegraph"
args = ["serve", "--mcp"]
```

3. In isolated/GUI/NVM launch paths, the MCP child process may not inherit the shell PATH that contains NVM bins, so Codex cannot find `codegraph`.
4. Hook trust reuse was also weakened by Codex Caveman session generation: MMS filtered Caveman hooks and appended a new Caveman hook later, which could move it behind Map or inherited automation hooks. Codex trust state keys include event/group/hook position, so reordering can force another `/hooks` review.

## Fix Implemented

Code changes are in `mms_launchers.py`:

- Added `_normalize_session_mcp_server_spec()` and `_normalize_session_mcp_servers()`.
- Bare MCP commands are resolved through real HOME search via `_resolve_real_home_command_path()`.
- If a bare command cannot be resolved, MMS does not inject that MCP into the session. This is fail-closed and avoids noisy startup warnings.
- Absolute command paths are kept only when executable; URL-based MCP specs are left unchanged.
- The normalization path now covers:
  - `_session_managed_mcp_servers()`
  - `_inject_managed_mcp_servers_into_claude_state()`
  - `_ensure_session_only_claude_mcp_servers()`
  - `_sync_codex_session_claude_json()`
  - `_append_codex_mcp_servers_from_claude_json()`
- Added `_configure_codex_caveman_hooks()` so an existing compact `SessionStart` Caveman hook stays in its original position when possible.
- MMS now strips inherited Looop/bugloop-style Codex hooks from generated session hooks unless a future explicit session surface re-enables them; a normal MMS launch should not enter an autonomous loop just because the real HOME has one installed.
- Removed noisy/non-session Codex RTK/Caveman variants from generated session hooks while keeping the compact valid-JSON hook.

## 2026-05-26 Follow-up

Repeated `Hooks need review` prompts could still happen when a session was launched from a repo worktree or when the durable gateway cache missed trust entries that only existed in a sibling per-PID session.

Follow-up changes:

- `_LOCAL_HOOKS_DIR` now canonicalizes `multi-model-switch/.worktrees/<name>/mms_launchers.py` back to the parent repo `hooks/` directory when the canonical hook bundle exists. This keeps MMS-managed Codex hook command paths stable across worktree-launched sessions.
- Codex hook trust write-back now uses a shared durable-cache writer.
- New Codex gateway sessions refresh `~/.config/mms/codex-gateway/.codex` hook trust from real HOME, durable cache, and sibling session configs during environment preparation, not only after process exit.
- The exit write-back path still persists current-session trust after `Trust all and continue`, but the next launch can now recover from sibling trust even if the previous durable cache was incomplete.

## Safety Rules Preserved

- No direct write to real `~/.claude.json` or real `~/.codex/config.toml` was required.
- Missing optional MCP binaries are dropped from generated session config instead of blocking launch.
- `disabled_session_surfaces.mcp` still wins before normalization.
- Real HOME command resolution reuses existing MMS real-home/NVM/Homebrew discovery without switching the user's default Node.
- Hook trust hashes are not fabricated; MMS only preserves order and reuses existing trusted state where Codex can validate it.

## Validation

Commands run for the hardening commit:

```bash
python3.13 -m py_compile mms_core.py mms_launchers.py mms_tui.py
python3.13 -m pytest -q tests/test_claude_hardening_regressions.py tests/test_opencode_launcher.py tests/test_mms_runtime.py
npm run build --if-present
git diff --check
```

Result:

- `177 passed` for the targeted pytest set.
- `npm run build --if-present` passed.
- `git diff --check` passed.
- Local projection confirmed inherited `codegraph` became an absolute NVM binary path when available.
- Local projection confirmed Codex `SessionStart` order keeps Map/Caveman stable and no longer inherits Looop/bugloop hooks by default. CodeGraph auto-register remains a Claude session hook: uninitialized git repos run init/index, initialized repos sync.

## Regression Tests Added

- Codex MCP inheritance rewrites a bare `codegraph` command to the real HOME binary.
- Codex MCP inheritance drops an unresolved bare `codegraph` command.
- Claude managed MCP state drops unresolvable inherited `codegraph`.
- Existing compact Codex Caveman hook order is preserved so trust reuse has a stable target.
- Existing MCP tests were updated to assert absolute real-HOME command resolution for `node` / `python3`.

## How To Trace / 回源

- Primary fix commit: `535aeee fix(codex): harden inherited mcp startup`
- Release tag containing the fix: `v2.10.2`
- Documentation rollup tag: `v2.10.3`
- Main files:
  - `mms_launchers.py`
  - `tests/test_claude_hardening_regressions.py`
  - `README.md`
  - `README.zh-CN.md`
- Related previous docs:
  - `.ai/regression-reports/2026-05-08-codex-hook-trust-state.md`
  - `.ai/regression-reports/2026-05-08-hooks-parity-looop-rtk-caveman.md`
  - `.ai/regression-reports/2026-05-18-opencode-preflight-opt-in.md`

## Final Conclusion

The startup failure was not a broken `codegraph` install; it was an inherited bare-command MCP leaking into an isolated Codex session whose child process PATH could not see the NVM binary. MMS now resolves inherited MCP commands to real-HOME absolute paths or drops them, and Codex Caveman hook generation preserves trusted compact hook order where possible. This should prevent the repeated `codegraph` startup warning and reduce recurring `/hooks` trust prompts across MMS-managed Codex sessions.
