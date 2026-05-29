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
- Follow-up hardening: MMS gateway Codex launches now keep the per-PID `MMS_SESSION_HOME` for wrappers/tmp files but point `CODEX_HOME` at stable `~/.config/mms/codex-gateway/.codex`, so Codex sees the same `hooks.json` trust key across isolated launches instead of treating every PID as a brand-new hook source.

## 2026-05-27 No-Popup Contract

Repeated review prompts recurred because old per-PID isolated sessions contained stale `hooks.state` entries for MMS-managed `scmp_hook.py` hooks. During gateway config regeneration those stale sibling entries could overwrite the current real-home trust, so Codex showed `modified` even though the canonical `~/.codex/hooks.json` hook was already trusted.

This is now a hard MMS contract:

- `CODEX_HOME` for MMS gateway Codex must remain stable at `~/.config/mms/codex-gateway/.codex`.
- `MMS_SESSION_HOME` may remain per-PID for wrappers/tmp/session packet state, but it must not become the trust identity for Codex hooks.
- In runtime `bypass` mode, MMS Codex must append both `--dangerously-bypass-approvals-and-sandbox` and `--dangerously-bypass-hook-trust`; removing the second flag reintroduces startup review popups.
- Trust imported from real `~/.codex/hooks.json` is authoritative for matching hooks. Sibling `codex-gateway/s/<pid>/.codex/config.toml` entries may seed missing trust only; they must not override real-home trust for the same command/fingerprint.
- Do not treat an old per-PID session config as the durable source of truth for hook trust. The durable source is the stable gateway `.codex/config.toml`, refreshed from real-home trust with sibling sessions as fallback.
- Codex upgrades can change hook hash normalization. MMS must refresh stable gateway hook trust from the current Codex `app-server` `hooks/list` `currentHash` before launch.
- Real `~/.codex/config.toml` may only be auto-refreshed for MMS-managed hook trust hashes, so app-server children that use real `CODEX_HOME` do not reintroduce the prompt. Do not auto-trust arbitrary project/user hooks.
- A user approval in one isolated MMS/Codex session must be durable. If the same MMS-managed hook prompts again in a later isolated session, treat it as a launcher trust write-back regression, not as expected Codex behavior.

## Recurrence Playbook

When a user reports `Hooks need review` again, do not start by asking them to approve it again. First prove which trust identity is active.

1. Check active Codex processes:
   - CLI command must include `--dangerously-bypass-approvals-and-sandbox` and `--dangerously-bypass-hook-trust`.
   - CLI env must use `CODEX_HOME=/Users/xin/.config/mms/codex-gateway/.codex`.
   - `MMS_SESSION_HOME` may be per-PID under `~/.config/mms/codex-gateway/s/<pid>`.
2. Check app-server children:
   - Some Codex app-server/node_repl children may use `CODEX_HOME=/Users/xin/.codex`.
   - That is why MMS also refreshes only MMS-managed hook trust in real `~/.codex/config.toml`.
3. Run Codex `app-server` `hooks/list` against both homes:
   - gateway `~/.config/mms/codex-gateway/.codex`
   - real `~/.codex`
   - Healthy result is `0` hooks with `trustStatus` `untrusted` or `modified`.
4. If hashes drift after a Codex upgrade:
   - refresh from current `hooks/list` `currentHash`, not from old copied `trusted_hash`.
   - gateway refresh may cover all generated target hooks.
   - real-home refresh must remain scoped to MMS-managed hook commands only.
5. If one isolated session approval is not reused:
   - inspect `_sync_codex_hook_trust_back`, `_write_codex_hook_trust_cache`, `_append_codex_session_hook_trust_states`, and `_refresh_codex_current_hook_trust_cache`.
   - the fix must persist trust to stable gateway `.codex/config.toml` before the next launch.

Regression coverage:

- `tests/test_codex_hook_trust_contract.py`
- `tests/test_codex_reasoning_effort_launch.py::test_launch_codex_bypass_mode_skips_hook_review_prompt`
- Codex hook trust tests in `tests/test_claude_hardening_regressions.py`

## Safety Rules Preserved

- No direct write to real `~/.claude.json` is required.
- After the Codex 0.134 upgrade, the only allowed real `~/.codex/config.toml` write is a scoped MMS-managed hook trust hash refresh from current Codex `hooks/list`; no auth, account, model, or provider state is copied from real HOME.
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
- Local projection confirmed Codex `SessionStart` order keeps Map/Caveman stable and no longer inherits Looop/bugloop hooks by default. Later hook-noise hardening made CodeGraph auto-register opt-in instead of a default Claude session hook.

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
