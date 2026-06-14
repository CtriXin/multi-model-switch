# OpenCode Hook-Fit Spike Phase 1 Evidence

Date: 2026-06-14
Operator: Codex
Repo root: `/Users/xin/auto-skills/CtriXin-repo/multi-model-switch`
OpenCode version: `1.15.13`
Scope: Phase 1 two-kill-switch gate only

## Kill-Switch Status

- kill-switch A: `experimental.session.compacting` restore packet -> `partial`
- kill-switch B: bounded subagent + custom-tool boundary negative tests -> `not_run`
- fail-fast stop triggered: `yes`
- stop reason: compaction hook could be triggered by legacy summarize, but Phase 1 could not prove restore packet persistence; v2 compact endpoint returned 503.
- proceed to non-kill-switch surfaces: `no`

## Phase-1 Summary Table

| Check | Official mechanism | Goal | Verdict | Kill-switch | Blocking issue | Evidence path |
| --- | --- | --- | --- | --- | --- | --- |
| restore packet | `experimental.session.compacting` | compaction restore viability | partial | A | yes | `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-compact/`, `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-summarize-provider/` |
| subagent negative | permissions/subagent dispatch | reject full-state payload | not_run | B | not assessed | not run due fail-fast stop |
| custom-tool negative | custom tool bridge | no direct canonical-state access | not_run | B | not assessed | not run due fail-fast stop |

## 1. `experimental.session.compacting`

- goal: Verify whether OpenCode can inject a minimal restore packet during compaction and preserve it after compaction.
- official mechanism tested: session-local plugin returning `experimental.session.compacting`; OpenCode HTTP API `/api/session/{sessionID}/compact`; legacy `/session/{sessionID}/summarize`.
- why this mechanism matters to the lifecycle surface: this is the proposed continuity restore-packet hook for long OpenCode sessions.
- setup:
  - all runs used isolated `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`, `OPENCODE_CONFIG`, and `OPENCODE_CONFIG_DIR` under `opencode-local/spikes/opencode-hook-fit/artifacts/`.
  - no writes were made to global `~/.config/opencode/`.
  - plugin file was session-local under each run's `xdg-config/opencode/plugins/phase1-probe.ts`.
- config or code path under test:
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-compact/xdg-config/opencode/plugins/phase1-probe.ts`
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-summarize-provider/xdg-config/opencode/plugins/phase1-probe.ts`
- observed trigger timing:
  - plugin load was observed in trace/logs.
  - v2 compact endpoint did not trigger compaction; it returned 503 `V2 session compact is not available yet`.
  - legacy summarize with a local fake OpenAI-compatible provider did trigger `experimental.session.compacting` before the compaction model call.
- observed payload shape:
  - hook input observed: `{"sessionID":"ses_..."}`.
  - no richer payload was observed during Phase 1.
- mutation/control surface available:
  - hook can return a string.
  - returned string was not proven to persist into the compacted context or post-compaction messages.
- fits current need: `partial`
- blocker level: `major`
- kill-switch relevance: `A`
- hard-stop touched: `yes`
- hard-stop detail: Phase 1 pass requires restore packet survival after real compaction; this was not proven.
- boundary concerns:
  - `experimental.session.compacting` is experimental.
  - v2 compact API exists in OpenAPI but is unavailable in this OpenCode build/runtime.
  - legacy summarize triggers the hook, but evidence does not prove restore packet persistence.
- evidence paths:
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-compact/compact.body`: `{"_tag":"ServiceUnavailableError","message":"V2 session compact is not available yet","service":"v2.session.compact"}`
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-compact/compact.headers`: HTTP `503 Service Unavailable`
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-summarize-provider/trace.jsonl`: hook triggered with `kind: "hook.compacting"`
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-summarize-provider/fake/requests.jsonl`: fake provider received a compaction model request
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-summarize-provider/messages.json`: summarize completed with fake summary text, not a proven restore packet
- verdict: `partial`
- follow-up:
  - Do not treat compaction restore as stable contract truth yet.
  - Next attempt should either find the intended OpenCode path that persists the hook return, or downgrade continuity to external session-close/pickup artifacts independent of compaction.

## 2. Subagent Full-State Negative Test

- goal: Verify full-state subagent dispatch can be rejected, blocked, or fail-closed.
- official mechanism tested: not run.
- why this mechanism matters to the lifecycle surface: it is kill-switch B for bounded dispatch.
- setup: not run because kill-switch A produced a major partial/blocking result.
- config or code path under test: not run.
- observed trigger timing: not run.
- observed payload shape: not run.
- mutation/control surface available: not run.
- fits current need: `no evidence`
- blocker level: `not assessed`
- kill-switch relevance: `B`
- hard-stop touched: `no`
- hard-stop detail: fail-fast stopped before this check.
- boundary concerns: still unproven.
- evidence paths: not run.
- verdict: `not_run`
- follow-up: run only if compaction continuity is narrowed or accepted with caveats.

## 3. Custom Tool Boundary Negative Test

- goal: Verify custom tool path avoids direct canonical-state file access.
- official mechanism tested: not run.
- why this mechanism matters to the lifecycle surface: it is kill-switch B for state bridge authority.
- setup: not run because kill-switch A produced a major partial/blocking result.
- config or code path under test: not run.
- observed trigger timing: not run.
- observed payload shape: not run.
- mutation/control surface available: not run.
- fits current need: `no evidence`
- blocker level: `not assessed`
- kill-switch relevance: `B`
- hard-stop touched: `no`
- hard-stop detail: fail-fast stopped before this check.
- boundary concerns: still unproven.
- evidence paths: not run.
- verdict: `not_run`
- follow-up: run only if compaction continuity is narrowed or accepted with caveats.

## Hard-Stop Log

### Hard-stop incident 1

- surface: `experimental.session.compacting`
- attempted action: prove restore packet survives a real compaction cycle
- forbidden boundary touched: none; the hard stop is an evidence failure, not a safety violation
- was the action blocked: yes, by insufficient OpenCode runtime support/evidence
- evidence paths:
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-compact/compact.body`
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-summarize-provider/trace.jsonl`
  - `opencode-local/spikes/opencode-hook-fit/artifacts/phase1-summarize-provider/messages.json`
- impact on spike verdict: Phase 1 cannot pass as written.
- follow-up: narrow continuity strategy or rerun against an OpenCode build/path that supports durable compaction restore.

## Phase-1 Gate Decision

- phase-1 verdict: `partial`
- kill-switch A final verdict: `partial`
- kill-switch B final verdict: `not_run`
- fail-fast stop triggered: `yes`
- if yes, at which check: kill-switch A, after v2 compact 503 and legacy summarize hook-return persistence remained unproven
- blocking findings:
  - v2 compact endpoint returned 503 `V2 session compact is not available yet`.
  - legacy summarize triggered `experimental.session.compacting`, but did not prove the returned restore packet survived post-compaction.
- acceptable caveats:
  - The hook can be loaded session-locally and can fire in a compaction-like legacy summarize path.
  - This is enough to keep researching the surface, but not enough to promote compaction restore to contract truth.
- recommended next step:
  - revise frozen memo before implementation
  - narrow continuity design to allow external close/pickup artifacts independent of compaction, or rerun compaction against a newer/specific OpenCode build that supports v2 compact
